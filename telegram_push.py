# -*- coding: utf-8 -*-
"""
把今日任务清单发给 Cloudflare 接线员，由它发到 Telegram（带按钮的卡片）
文件：telegram_push.py
"""

import hashlib
import sys
from datetime import datetime

import requests

import main  # 复用 main.py 里的下载/解析/分类逻辑


# 从环境变量读配置（在 GitHub Secrets 里设置）
WORKER_URL = main.env("QUEST_WORKER_URL").rstrip("/")
if WORKER_URL.endswith("/push"):          # 万一多填了 /push，自动去掉
    WORKER_URL = WORKER_URL[: -len("/push")].rstrip("/")
WORKER_KEY = main.env("QUEST_WORKER_KEY")


def short_id(text):
    """给每条任务算一个短 ID，用来在按钮回调时对应上"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def build_payload(tasks, overdue, now):
    """把任务列表整理成接线员需要的 JSON 格式"""
    items = []
    for t in tasks:
        items.append({
            "id": short_id(t["name"] + "|" + t["due"].isoformat()),
            "name": t["name"],
            "course": t["course"],
            "kind": t["kind"],
            "icon": t["icon"],
            "due_str": t["due"].strftime("%m-%d %H:%M"),
            "left": main.fmt_countdown(t["delta"]),
        })
    return {
        "date": now.strftime("%Y-%m-%d"),
        "overdue": overdue,
        "tasks": items,
    }


def run():
    main.log("========== Telegram 日课卡片 开始 ==========")

    # 配置检查
    if not WORKER_URL or not WORKER_KEY:
        main.log("❌ 没有配置 QUEST_WORKER_URL 或 QUEST_WORKER_KEY，本次跳过")
        sys.exit(1)
    if not main.CANVAS_ICS_URL:
        main.log("❌ 没有配置 CANVAS_ICS_URL")
        sys.exit(1)

    # 下载 + 解析 Canvas 日历
    raw = main.fetch_ics(main.normalize_ics_url(main.CANVAS_ICS_URL))
    if raw is None:
        main.log("❌ 下载 Canvas 日历失败，本次跳过")
        sys.exit(1)

    now = datetime.now(main.TARGET_TZ)
    events = main.parse_events(raw)
    tasks, overdue = main.build_tasks(events, now)
    payload = build_payload(tasks, overdue, now)

    # 发给接线员
    url = f"{WORKER_URL}/push?key={WORKER_KEY}"
    main.log(f"📤 正在把 {len(payload['tasks'])} 项任务发给接线员…")
    try:
        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()
    except Exception as e:
        main.log(f"❌ 请求接线员失败：{e}")
        sys.exit(1)

    if data.get("ok"):
        main.log(f"✅ Telegram 卡片已发送（{data.get('tasks')} 项任务）")
        return
    main.log(f"❌ 接线员返回失败：{data}")
    sys.exit(1)


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        main.log(f"❌ 程序出错：{exc}")
        traceback.print_exc()
        sys.exit(1)
