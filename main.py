# -*- coding: utf-8 -*-
"""
============================================================
 Canvas 课程日程 ➔ 微信「游戏化日课」提醒机器人
 文件：main.py
============================================================
 它做四件事：
   1. 从 Canvas 的日历订阅链接(.ics) 下载你的全部日程
   2. 挑出未来 7 天内要交的作业/考试，自动分成「主线任务 / 每日日常」
   3. 计算倒计时，拼装成 RPG 游戏风格的「日课卡片」
   4. 通过 Server酱 或 WxPusher 推送到你的微信

 所有敏感信息都从「环境变量」读取，绝不写死在代码里。
============================================================
"""

import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import escape

import requests
from icalendar import Calendar

try:
    from zoneinfo import ZoneInfo
except ImportError:          # 兼容极老版本的 Python
    ZoneInfo = None


# ------------------------------------------------------------
# 0. 小工具函数
# ------------------------------------------------------------
try:
    # 保证在 Windows 本地运行时也能正常打印 emoji
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    """带时间戳的日志，方便在 GitHub Actions 的日志里排查问题"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def env(name, default=""):
    """读取环境变量并去掉首尾空格"""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip()


def env_bool(name, default=True):
    v = env(name, "").lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def env_int(name, default):
    try:
        return int(env(name, "") or default)
    except ValueError:
        return default


def env_float(name, default):
    try:
        return float(env(name, "") or default)
    except ValueError:
        return default


# ------------------------------------------------------------
# 1. 读取配置（全部来自 GitHub Secrets，见部署教程第三步）
# ------------------------------------------------------------
CANVAS_ICS_URL     = env("CANVAS_ICS_URL")        # 必填：Canvas 日历订阅链接
SERVERCHAN_SENDKEY = env("SERVERCHAN_SENDKEY")    # 选填：Server酱 Turbo 的 SendKey
WXPUSHER_APP_TOKEN = env("WXPUSHER_APP_TOKEN")    # 选填：WxPusher 的 APP_TOKEN
WXPUSHER_UIDS      = env("WXPUSHER_UIDS")         # 选填：WxPusher 的 UID，多个用英文逗号隔开

TZ_NAME          = env("TZ_NAME", "Asia/Shanghai") or "Asia/Shanghai"  # 你的时区
LOOKAHEAD_DAYS   = env_int("LOOKAHEAD_DAYS", 7)      # 向后看多少天
MAIN_QUEST_HOURS = env_float("MAIN_QUEST_HOURS", 72)  # 多少小时内算「主线」（72 小时 = 3 天）
SEND_WHEN_EMPTY  = env_bool("SEND_WHEN_EMPTY", True)  # 没任务时是否也发一条

# 想屏蔽的日程关键词（例如课表、答疑时间），用英文逗号分隔，不区分大小写
IGNORE_KEYWORDS = [
    k.strip().lower()
    for k in env("IGNORE_KEYWORDS", "office hours,officehour,答疑").split(",")
    if k.strip()
]

# 目标时区
if ZoneInfo is not None:
    try:
        TARGET_TZ = ZoneInfo(TZ_NAME)
    except Exception:
        log(f"⚠️ 无法识别时区「{TZ_NAME}」，已改用 UTC+8")
        TARGET_TZ = timezone(timedelta(hours=8))
else:
    TARGET_TZ = timezone(timedelta(hours=8))


# ------------------------------------------------------------
# 2. 任务类型识别（只影响图标和标签，不影响「主线/日常」的判定）
#    判定规则完全按时间：3 天内 = 主线 Boss；4~7 天 = 每日日常
# ------------------------------------------------------------
KEYWORD_STYLES = [
    (["exam", "midterm", "final", "test", "quiz", "考试", "期中", "期末", "测验", "小测"], "👹", "考试"),
    (["project", "presentation", "essay", "paper", "report", "thesis",
      "项目", "论文", "报告", "演讲", "答辩"], "🐲", "大作业"),
    (["lab", "worksheet", "练习", "实验"], "🧪", "实验/练习"),
    (["discussion", "forum", "讨论", "回帖"], "💬", "讨论"),
    (["reading", "阅读", "读书", "章节"], "📖", "阅读"),
]


def type_icon(text):
    """根据任务标题猜测它是什么类型的任务，返回 (图标, 标签)"""
    low = text.lower()
    for keywords, icon, label in KEYWORD_STYLES:
        for kw in keywords:
            if kw in low:
                return icon, label
    return "📌", "任务"


def fmt_countdown(delta):
    """把时间差格式化成「1 天 4 小时」这种人类友好的倒计时"""
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes <= 0:
        return "已过期"
    days, rest = divmod(total_minutes, 1440)
    hours, minutes = divmod(rest, 60)
    if days > 0:
        return f"{days} 天 {hours} 小时"
    if hours > 0:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


COURSE_RE = re.compile(r"^\s*\[(.+?)\]\s*(.*)$")


def split_course(summary):
    """Canvas 的日程标题通常长这样：[课程名] 作业名，这里把它拆开"""
    m = COURSE_RE.match(summary)
    if m:
        course = m.group(1).strip()
        name = m.group(2).strip() or course
        return course, name
    return "", summary


# ------------------------------------------------------------
# 3. 下载并解析 Canvas 的 .ics 日历
# ------------------------------------------------------------
def normalize_ics_url(url):
    """Canvas 给出的链接可能以 webcal:// 开头，浏览器能识别但程序不能，这里统一转成 https://"""
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    return url


def fetch_ics(url, retries=3, timeout=30):
    """下载 .ics 内容，失败会自动重试 3 次；仍失败则返回 None（不会让程序崩溃）"""
    headers = {"User-Agent": "CanvasDailyQuestBot/1.0 (+https://github.com)"}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                log(f"✅ 成功下载 Canvas 日历（{len(resp.content)} 字节）")
                return resp.content
            log(f"⚠️ 第 {attempt} 次请求返回状态码 {resp.status_code}，稍后重试…")
        except Exception as e:
            log(f"⚠️ 第 {attempt} 次请求出错：{e}")
        time.sleep(3)
    return None


def to_aware(value):
    """把 .ics 里的时间统一转换成「带时区的 datetime」"""
    if isinstance(value, datetime):                 # 注意：datetime 要在 date 之前判断
        if value.tzinfo is None:
            return value.replace(tzinfo=TARGET_TZ)  # 没有时区信息就当作本地时间
        return value.astimezone(TARGET_TZ)
    if isinstance(value, date):                     # 全天事件（只有日期没有时刻）
        return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=TARGET_TZ)
    return None


def parse_events(raw_bytes):
    """把 .ics 文本解析成一条条日程（自动去重、跳过坏数据）"""
    try:
        calendar = Calendar.from_ical(raw_bytes)
    except Exception as e:
        log(f"❌ .ics 文件解析失败：{e}")
        return []

    events, seen = [], set()
    for component in calendar.walk("VEVENT"):
        try:
            summary = str(component.get("SUMMARY", "")).strip()
            if not summary:
                continue
            raw_due = component.get("DTEND") or component.get("DTSTART")
            if raw_due is None:
                continue
            due = to_aware(getattr(raw_due, "dt", None))
            if due is None:
                continue
            key = (summary, due.isoformat())
            if key in seen:            # Canvas 有时会重复推送同一条
                continue
            seen.add(key)
            events.append({"summary": summary, "due": due})
        except Exception as e:
            log(f"⚠️ 跳过一条无法解析的日程：{e}")
    log(f"📅 共解析出 {len(events)} 条原始日程")
    return events


# ------------------------------------------------------------
# 4. 筛选 + 分类，生成「任务列表」
# ------------------------------------------------------------
def build_tasks(events, now):
    tasks, overdue = [], 0
    for ev in events:
        summary = ev["summary"]
        if any(kw in summary.lower() for kw in IGNORE_KEYWORDS):
            continue                                # 被用户屏蔽的关键词，直接跳过
        delta = ev["due"] - now
        if delta.total_seconds() < 0:
            if delta >= timedelta(days=-14):        # 近两周内过期的，记一笔
                overdue += 1
            continue                                # 早就过期的不再提醒
        if delta > timedelta(days=LOOKAHEAD_DAYS):  # 太远的不提醒
            continue

        hours = delta.total_seconds() / 3600.0
        kind = "main" if hours <= MAIN_QUEST_HOURS else "daily"
        course, name = split_course(summary)
        icon, label = type_icon(summary)
        tasks.append({
            "course": course,
            "name": name,
            "icon": icon,
            "label": label,
            "due": ev["due"],
            "delta": delta,
            "kind": kind,
            "exp": 50 if kind == "main" else 20,    # 主线经验多，日常经验少
        })
    tasks.sort(key=lambda t: t["due"])
    return tasks, overdue


# ------------------------------------------------------------
# 5. 渲染成「游戏日课卡片」
# ------------------------------------------------------------
def render_markdown(tasks, overdue, now):
    """给 Server酱 用的 Markdown 版本"""
    main_quests = [t for t in tasks if t["kind"] == "main"]
    daily_quests = [t for t in tasks if t["kind"] == "daily"]
    total_exp = sum(t["exp"] for t in tasks)
    level = total_exp // 100 + 1

    L = []
    L.append(f"# ⚔️ 冒险者日志 · {now.strftime('%Y-%m-%d')}")
    L.append("")
    if tasks:
        L.append(f"> 🏰 任务大厅已刷新！今日共有 **{len(tasks)}** 项待办，"
                 f"预计可获 **EXP +{total_exp}**（当前等级 **Lv.{level}**）")
    else:
        L.append("> 🏖️ **今日无任务！** 尽情摸鱼吧，冒险者。")
    L.append("")

    if main_quests:
        L.append(f"## ⚔️ 主线任务 · Boss 战（{int(MAIN_QUEST_HOURS // 24)} 天内）")
        L.append("")
        for t in main_quests:
            L.append(f"**{t['icon']} 【{t['label']}】{t['name']}**")
            L.append("")
            if t["course"]:
                L.append(f"- 🏫 课程：{t['course']}")
            L.append(f"- ⏰ 截止：{t['due'].strftime('%m-%d %H:%M')}　**还剩 {fmt_countdown(t['delta'])}**")
            L.append(f"- 🎁 奖励：EXP +{t['exp']} ｜ 金币 +{t['exp'] * 2}")
            L.append("")

    if daily_quests:
        L.append("## 📜 每日日常（4 ~ 7 天内）")
        L.append("")
        for t in daily_quests:
            L.append(f"**{t['icon']} 【{t['label']}】{t['name']}**")
            L.append("")
            if t["course"]:
                L.append(f"- 🏫 课程：{t['course']}")
            L.append(f"- ⏰ 截止：{t['due'].strftime('%m-%d %H:%M')}　还剩 {fmt_countdown(t['delta'])}")
            L.append(f"- 🎁 奖励：EXP +{t['exp']}")
            L.append("")

    L.append("## 🏆 状态简报")
    L.append("")
    L.append(f"- ⚔️ 主线任务：**{len(main_quests)}** 项")
    L.append(f"- 📜 每日日常：**{len(daily_quests)}** 项")
    if overdue:
        L.append(f"- 💀 已过期（近两周）：**{overdue}** 项，尽快找老师补交！")
    L.append(f"- ✨ 预计总经验：**EXP +{total_exp}**（等级 **Lv.{level}**）")
    L.append("")
    L.append("---")
    L.append("> 🤖 由 GitHub Actions 自动生成 · 每天 08:00 / 20:00 自动刷新")
    return "\n".join(L)


def render_html(tasks, overdue, now):
    """给 WxPusher 用的 HTML 版本（微信里显示更漂亮）"""
    main_quests = [t for t in tasks if t["kind"] == "main"]
    daily_quests = [t for t in tasks if t["kind"] == "daily"]
    total_exp = sum(t["exp"] for t in tasks)
    level = total_exp // 100 + 1

    def task_card(t, color):
        html = (f'<div style="margin:8px 0;padding:10px 12px;border-left:4px solid {color};'
                f'background:#f7f8fa;border-radius:6px;">'
                f'<div style="font-size:15px;font-weight:bold;color:#222;">'
                f'{t["icon"]} 【{escape(t["label"])}】{escape(t["name"])}</div>')
        if t["course"]:
            html += f'<div style="font-size:12px;color:#888;margin-top:2px;">🏫 {escape(t["course"])}</div>'
        html += (f'<div style="font-size:13px;color:#c0392b;margin-top:4px;">'
                 f'⏰ 截止 {t["due"].strftime("%m-%d %H:%M")} · 还剩 {fmt_countdown(t["delta"])}</div>'
                 f'<div style="font-size:12px;color:#27ae60;margin-top:2px;">'
                 f'🎁 EXP +{t["exp"]} ｜ 金币 +{t["exp"] * 2}</div></div>')
        return html

    H = ['<div style="font-family:-apple-system,\'PingFang SC\',sans-serif;font-size:14px;color:#333;">']
    H.append(f'<div style="font-size:17px;font-weight:bold;color:#1a1a1a;margin-bottom:6px;">'
             f'⚔️ 冒险者日志 · {now.strftime("%Y-%m-%d")}</div>')
    if tasks:
        H.append(f'<div style="color:#555;margin-bottom:8px;">🏰 任务大厅已刷新！今日共 '
                 f'<b>{len(tasks)}</b> 项待办，预计可获 <b>EXP +{total_exp}</b>'
                 f'（当前等级 <b>Lv.{level}</b>）</div>')
    else:
        H.append('<div style="color:#555;margin-bottom:8px;">🏖️ <b>今日无任务！</b>尽情摸鱼吧，冒险者。</div>')

    if main_quests:
        H.append('<div style="font-size:15px;font-weight:bold;color:#c0392b;margin:12px 0 6px;">'
                 '⚔️ 主线任务 · Boss 战</div>')
        for t in main_quests:
            H.append(task_card(t, "#c0392b"))

    if daily_quests:
        H.append('<div style="font-size:15px;font-weight:bold;color:#2980b9;margin:12px 0 6px;">'
                 '📜 每日日常</div>')
        for t in daily_quests:
            H.append(task_card(t, "#2980b9"))

    H.append('<div style="font-size:15px;font-weight:bold;margin:14px 0 6px;">🏆 状态简报</div>')
    H.append(f'<div style="line-height:1.9;">⚔️ 主线任务：<b>{len(main_quests)}</b> 项<br>'
             f'📜 每日日常：<b>{len(daily_quests)}</b> 项<br>')
    if overdue:
        H.append(f'💀 已过期（近两周）：<b>{overdue}</b> 项<br>')
    H.append(f'✨ 预计总经验：<b>EXP +{total_exp}</b>（等级 <b>Lv.{level}</b>）</div>')
    H.append('<div style="color:#999;font-size:12px;margin-top:12px;">'
             '🤖 由 GitHub Actions 自动生成 · 每天 08:00 / 20:00 自动刷新</div>')
    H.append("</div>")
    return "".join(H)


# ------------------------------------------------------------
# 6. 推送到微信
# ------------------------------------------------------------
def push_serverchan(title, markdown_text):
    """Server酱 Turbo 推送；成功返回 True"""
    url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    log("📤 正在通过 Server酱 推送到微信…")
    resp = requests.post(url, data={"title": title, "desp": markdown_text}, timeout=30)
    data = resp.json()
    if data.get("code") == 0:
        log("✅ Server酱 推送成功")
        return True
    log(f"❌ Server酱 推送失败：{data}")
    return False


def push_wxpusher(title, html_text):
    """WxPusher 推送；成功返回 True"""
    url = "https://wxpusher.zjiecode.com/api/send/message"
    payload = {
        "appToken": WXPUSHER_APP_TOKEN,
        "content": html_text,
        "summary": title[:99],       # 微信里的副标题，最长 100 字
        "contentType": 2,            # 1=纯文本 2=HTML 3=Markdown
        "uids": [u.strip() for u in WXPUSHER_UIDS.split(",") if u.strip()],
    }
    log("📤 正在通过 WxPusher 推送到微信…")
    resp = requests.post(url, json=payload, timeout=30)
    data = resp.json()
    if data.get("code") == 1000:
        log("✅ WxPusher 推送成功")
        return True
    log(f"❌ WxPusher 推送失败：{data}")
    return False


def push_all(title, markdown_text, html_text):
    """把消息发到所有已配置的渠道"""
    ok = False
    if SERVERCHAN_SENDKEY:
        try:
            ok = push_serverchan(title, markdown_text) or ok
        except Exception as e:
            log(f"❌ Server酱 异常：{e}")
    if WXPUSHER_APP_TOKEN and WXPUSHER_UIDS:
        try:
            ok = push_wxpusher(title, html_text) or ok
        except Exception as e:
            log(f"❌ WxPusher 异常：{e}")
    return ok


def build_title(tasks):
    main_count = len([t for t in tasks if t["kind"] == "main"])
    if not tasks:
        return "🏖️ 今日无日课，安心摸鱼"
    if main_count:
        return f"⚔️ 日课刷新：{len(tasks)} 项待办（{main_count} 个 Boss）"
    return f"📜 日课刷新：{len(tasks)} 项待办"


# ------------------------------------------------------------
# 7. 主流程
# ------------------------------------------------------------
def main():
    log("========== Canvas 日课提醒 开始 ==========")

    # --- 配置检查（失败时给出明确的人话提示）---
    if not CANVAS_ICS_URL:
        log("❌ 没有找到 CANVAS_ICS_URL，请到 GitHub 仓库 Secrets 里添加它")
        sys.exit(1)
    if not SERVERCHAN_SENDKEY and not (WXPUSHER_APP_TOKEN and WXPUSHER_UIDS):
        log("❌ 没有配置任何微信推送渠道（SERVERCHAN_SENDKEY 或 WXPUSHER_APP_TOKEN + WXPUSHER_UIDS）")
        sys.exit(1)

    # --- 下载日历 ---
    raw = fetch_ics(normalize_ics_url(CANVAS_ICS_URL))
    if raw is None:
        log("❌ 连续 3 次都没能下载到 Canvas 日历，本次放弃（可能是网络波动，下次会自动重试）")
        sys.exit(1)

    # --- 解析 + 分类 ---
    now = datetime.now(TARGET_TZ)
    events = parse_events(raw)
    tasks, overdue = build_tasks(events, now)
    log(f"🎯 未来 {LOOKAHEAD_DAYS} 天内有 {len(tasks)} 项任务，另有 {overdue} 项已过期")

    # --- 无任务时的处理 ---
    if not tasks and not SEND_WHEN_EMPTY:
        log("😴 今天没有任务，且已关闭「空提醒」，本次不发送")
        sys.exit(0)

    # --- 渲染 + 推送 ---
    title = build_title(tasks)
    markdown_text = render_markdown(tasks, overdue, now)
    html_text = render_html(tasks, overdue, now)

    if push_all(title, markdown_text, html_text):
        log("🎉 全部完成，请查看微信")
        sys.exit(0)
    log("😢 消息没能发出去，请检查 Key 是否填对、Server酱 额度是否用完")
    sys.exit(1)


if __name__ == "__main__":
    # 最外层兜底异常处理：即使出了意外，也会打印清晰原因，方便你复制给我排查
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        log(f"❌ 程序运行出错：{exc}")
        traceback.print_exc()
        sys.exit(1)
