# ⚔️ Canvas 日课提醒 · Canvas Daily Quest

> 把 Canvas 上的作业和考试，变成一张**每天早上自动送到手机**的「游戏日课」清单。
> 像手游一样：主线任务是 Boss 战、有倒计时、能打勾、有经验值和连胜天数。

💰 完全免费 ｜ ☁️ 无需服务器 ｜ 💻 电脑不用开机 ｜ 📱 微信 / Telegram 都能收

---

## ✨ 功能特性

- 🔄 **自动读取**：从 Canvas 的日历订阅（`.ics`）抓取作业、考试、讨论日程
- ⏰ **定时推送**：每天北京时间 **08:00 / 20:00** 自动发送（由 GitHub Actions 免费执行）
- ⚔️ **游戏化分类**：3 天内到期 = 「主线任务 · Boss 战」；4~7 天 = 「每日日常」
- ⏳ **智能倒计时**：`还剩 1 天 4 小时`、`还剩 35 分钟`
- 📊 **状态简报**：今日共几项待办、预计可得多少经验
- 🖱️ **按钮互动**（Telegram 版）：卡片上直接点 `✅完成` / `⏰延后`，进度条、EXP、连胜实时更新
- 💸 **零成本**：GitHub Actions + Server酱 + Cloudflare Workers 全部免费档额度即可

---

## 📸 效果预览

> 建议自行截图后放到 `screenshots/` 目录，替换下面两行。

| 微信推送 | Telegram 卡片（可点按钮） |
| :---: | :---: |
| ![wechat](screenshots/wechat.png) | ![telegram](screenshots/telegram.png) |

Telegram 卡片长这样：

```
⚔️ 冒险者日志 · 2026-09-24
🏰 今日日课  3/8  ███░░░░░░░ 37%
✨ EXP 250 · 🔥 连胜 4 天

⚔️ 主线任务 · Boss 战
✅ 👹 期中测验
⬜ 🐲 数据结构 Lab3
　　截止 09-26 23:59 · 还剩 1 天 4 小时
📜 每日日常
⬜ 📖 英语阅读 pp.120
　　截止 09-28 21:00 · 还剩 3 天 21 小时

[⬜ 数据结构 Lab3] [⏰ 延后]
[⬜ 英语阅读 pp.120] [⏰ 延后]
[🔄 刷新卡片]
```

---
[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/itsjerryduck/canvas-wechat-assist)

## 🧭 两种用法，任选其一

| | **路线 A：只微信** | **路线 B：完整版** |
| :--- | :---: | :---: |
| 能收到日课提醒 | ✅ | ✅ |
| 能在卡片上打勾互动 | ❌ | ✅ |
| 需要科学上网 | ❌ 不需要 | ✅ 需要（Telegram 的要求） |
| 需要 Cloudflare 账号 | ❌ | ✅（免费） |
| 配置时间 | 约 10 分钟 | 约 40 分钟 |

> 💡 如果你在国内且没有梯子，**直接走路线 A**，完全够用。

---

## 🏗 工作原理

```
        ┌──────────────────────────────┐
        │   GitHub Actions（免费定时器）  │
        │   每天 08:00 / 20:00 自动运行   │
        └──────────────┬───────────────┘
                       │  ① 下载 Canvas 的 .ics 日历
                       ▼
        ┌──────────────────────────────┐
        │        main.py / 解析分类       │
        │  分出「主线任务 / 每日日常」     │
        └───────┬──────────────┬────────┘
                │              │
     ② 微信推送 │              │ ③ 发给 Cloudflare Worker
                ▼              ▼
        ┌────────────┐  ┌──────────────────────┐
        │  Server酱   │  │  Worker（免费接线员）   │
        │  → 你的微信  │  │  发卡片到 Telegram     │
        └────────────┘  └──────────┬───────────┘
                                   │ ④ 你点「✅完成」
                                   ▼
                          ┌──────────────────┐
                          │  Cloudflare KV    │
                          │  存进度 / EXP / 连胜 │
                          └──────────────────┘
```

---

## 🚀 路线 A：只微信（约 10 分钟）

### 1️⃣ 复制这个项目
点页面右上角的 **Use this template** → **Create a new repository**（或者 **Fork**），生成一份自己的副本。

> ⚠️ 一定要是**你自己的副本**，因为 Secrets 是每个仓库独立的。

### 2️⃣ 拿到 Canvas 日历订阅链接
1. 登录 Canvas → 左侧 **Calendar（日历）**
2. 点右下角 **Calendar Feed**（日历订阅）
3. 复制弹窗里的链接，形如：
   ```
   webcal://your-school.instructure.com/feeds/calendars/user_xxxxxxxx.ics
   ```
   > 不用手动改 `webcal://`，代码会自动转成 `https://`
4. 🔐 这串链接含你的个人令牌，**不要公开分享**

### 3️⃣ 拿到微信推送 Key（Server酱）
1. 打开官方站点 **https://sct.ftqq.com**
2. 微信扫码登录，关注提示的公众号
3. 在 **SendKey** 页面复制那串 `SCT` 开头的密钥

> ⚠️ 请认准官方域名 `sct.ftqq.com`，不要在其他镜像站输入账号信息。

### 4️⃣ 配置 Secrets
仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Secret |
| :--- | :--- |
| `CANVAS_ICS_URL` | 第 2 步复制的 Canvas 链接 |
| `SERVERCHAN_SENDKEY` | 第 3 步拿到的 SendKey |

> 🔎 名字**必须一字不差**（全大写 + 下划线）。

### 5️⃣ 手动测试一次
**Actions** → 左侧 **Canvas 日课提醒** → **Run workflow** → 绿色 **Run workflow** → 等 30 秒刷新 → 点进记录看日志。

日志末尾出现下面这些就成功了：

```
✅ 成功下载 Canvas 日历（xxxxx 字节）
🎯 未来 7 天内有 x 项任务
✅ Server酱 推送成功
🎉 全部完成，请查看微信
```

### ✅ 完成
以后每天 **08:00 / 20:00** 会自动推送，你也可以随时在 Actions 页面点 **Run workflow** 手动补发。

---

## 🚀 路线 B：完整版（微信 + Telegram 按钮卡片）

在**完成路线 A 之后**，再补下面 6 步。

### 1️⃣ 建一个 Telegram 机器人
1. Telegram 里搜索 **@BotFather**（认准带蓝色认证勾的官方账号）
2. 发送 `/newbot`
3. 依次填「机器人名字」（随便）和「用户名」（**必须以 `bot` 结尾**，如 `my_quest_bot`）
4. 记下它返回的 **Token**：
   ```
   7712345678:AAH9kQx7Zv3mNpQr2sT5uW8xY1zA4bC6dE0fG
   ```

> 🔐 Token 是机器人的钥匙，**绝不要公开**。

### 2️⃣ 拿到你的 chat_id
1. 打开你新建的机器人对话（BotFather 会给你 `t.me/xxx_bot` 链接），点 **START**，随便发一句 `hi`
2. 浏览器打开（**需要梯子**）：
   ```
   https://api.telegram.org/bot<你的TOKEN>/getUpdates
   ```
3. 在返回内容里找到：
   ```json
   "chat":{"id":123456789,...}
   ```
   那个数字就是 **chat_id**

> ❓ 如果返回 `"result":[]`，说明机器人没收到消息，回去再发一条即可。
> ❓ 如果报 `409 Conflict ... webhook is active`，先打开 `.../deleteWebhook` 再查。

### 3️⃣ 部署 Cloudflare Worker（免费接线员）
1. 注册 **https://dash.cloudflare.com**
2. 左侧 **Compute** → **Workers & Pages** → **Create** → 选 **Hello World** → 起个名字（如 `canvas-quest-bot`）→ **Deploy**
3. 点 **Edit code**，把内容**全部删掉**，粘贴本仓库 **`worker/worker.js`** 的全部代码 → **Deploy**
4. 记下你的 Worker 网址：
   ```
   https://<worker名字>.<你的子域>.workers.dev
   ```

### 4️⃣ 建 KV 存储并存 3 个配置
1. 左侧 **Storage & databases** → **KV** → **Create instance** → 名字填 `QUEST_KV`
2. 进入这个 KV → **KV Pairs** → 添加 3 条：

   | Key | Value |
   | :--- | :--- |
   | `BOT_TOKEN` | 你的机器人 Token |
   | `CHAT_ID` | 你的 chat_id |
   | `PUSH_KEY` | **你自己编的一串乱码**，如 `q7Zm3Kp9Lx2V4tRb` |

3. 回到 Worker → **Settings** → **Bindings** → **Add binding** → 类型选 **KV Namespace**
   * **变量名（Variable name）**：`QUEST_KV` ← 必须叫这个
   * **命名空间**：选你刚建的 `QUEST_KV`

> ⚠️ **`PUSH_KEY` 请记在备忘录里**，下面两处都要用，且必须完全一致。
> ⚠️ 部分新版 Cloudflare 界面**没有"环境变量"入口**，所以本项目统一把配置放在 KV 里。

### 5️⃣ 设置 Webhook（把 Telegram 和 Worker 连起来）
浏览器打开（替换 `<BOT_TOKEN>` 和 `<PUSH_KEY>`，不要有空格换行）：

```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<你的worker网址>/telegram?key=<PUSH_KEY>
```

返回 `{"ok":true,"result":true,"description":"Webhook was set"}` 即成功。

自检（应无 `last_error_message`）：
```
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

### 6️⃣ 再加 2 个 GitHub Secrets 并测试
**Settings → Secrets and variables → Actions**，新增：

| Name | Secret |
| :--- | :--- |
| `QUEST_WORKER_URL` | `https://<你的worker网址>`（**只到 workers.dev 为止，不要加 `/push`**） |
| `QUEST_WORKER_KEY` | 你的 `PUSH_KEY` |

然后 **Actions → Canvas 日课提醒 → Run workflow**，日志出现下面这行就成功了：

```
✅ Telegram 卡片已发送（x 项任务）
```

去 Telegram 点一下按钮试试：`✅完成`、`⏰延后`、`↩️撤销`、`🔄刷新卡片`。

---

## ⚙️ 可选配置项

在 `.github/workflows/reminder.yml` 的 `env` 里调整：

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `TZ_NAME` | `Asia/Shanghai` | 时区 |
| `LOOKAHEAD_DAYS` | `7` | 向后看多少天 |
| `MAIN_QUEST_HOURS` | `72` | 多少小时内算「主线 Boss 战」（72 = 3 天） |
| `SEND_WHEN_EMPTY` | `true` | 没任务时是否也发一条微信 |
| `IGNORE_KEYWORDS` | `office hours,...` | 要屏蔽的日程关键词，英文逗号分隔 |

修改推送时间：改 `cron`（**是 UTC 时间，北京时间 − 8 小时**）：

| 北京时间 | cron 写法 |
| :--- | :--- |
| 早上 08:00 | `0 0 * * *` |
| 晚上 20:00 | `0 12 * * *` |
| 早上 07:00 | `0 23 * * *`（前一天 UTC） |
| 中午 12:00 | `0 4 * * *` |

---

## 📁 项目结构

```
.
├── main.py                        # 核心：解析 Canvas .ics → 排版 → 推送到微信
├── telegram_push.py               # 把任务清单 JSON 发给 Cloudflare Worker
├── requirements.txt               # Python 依赖
├── worker/
│   ├── worker.js                  # Cloudflare Worker：发 Telegram 卡片 + 处理按钮
│   └── wrangler.jsonc             # Worker 配置（KV 绑定声明）
└── .github/workflows/reminder.yml # 定时任务配置（cron + Secrets 注入）
```

---

## ❓ 常见问题

<details>
<summary><b>日志报 <code>没有找到 CANVAS_ICS_URL</code></b></summary>

Secrets 名字拼错了。回到 **Settings → Actions** 检查，必须**完全一致**：全大写、下划线、无空格。
</details>

<details>
<summary><b>日志报 <code>Could not open requirements file</code></b></summary>

仓库根目录缺少 `requirements.txt`（或文件名有隐藏空格/大小写错误）。删掉重建一个，内容为：
```
requests>=2.31.0
icalendar>=5.0.11
tzdata>=2024.1
```
</details>

<details>
<summary><b>日志显示推送成功，但微信没收到</b></summary>

1. 你是否**关注了** Server酱 / 方糖公众号？没关注收不到。
2. SendKey 是否复制完整。
3. 免费额度是否用完（去官网看剩余条数）。
4. 微信可能把它折叠进「服务通知」，往下翻翻。
</details>

<details>
<summary><b>定时任务跑了一段时间后突然不跑了</b></summary>

GitHub 规定：**公开仓库连续 60 天无任何提交活动，会自动暂停定时任务**。
去 **Actions** 页面点 **Enable workflow** 即可恢复。
</details>

<details>
<summary><b>到了 8 点却延迟很久才收到</b></summary>

GitHub 的定时任务在高峰期会排队，延迟几分钟到几十分钟属正常现象。
</details>

<details>
<summary><b>Cloudflare 里找不到"环境变量"入口</b></summary>

新版 Cloudflare 的部分账号界面把入口藏起来了。本项目已支持**从 KV 读取配置**，直接把 `BOT_TOKEN` / `CHAT_ID` / `PUSH_KEY` 作为 KV 条目添加即可。
</details>

<details>
<summary><b>Telegram 报错 <code>key 不正确</code></b></summary>

`PUSH_KEY` 在 3 个地方必须完全一致：① KV 条目 `PUSH_KEY`；② Webhook URL 里的 `?key=`；③ GitHub Secret `QUEST_WORKER_KEY`。
</details>

<details>
<summary><b>Telegram 卡片收到了，但点按钮没反应</b></summary>

Webhook 没设对。重新打开那条 `setWebhook` 链接，确认返回 `"ok":true`；
再用 `getWebhookInfo` 检查有没有 `last_error_message`。
</details>

---

## 🔒 安全与隐私

- 所有敏感信息（Canvas 链接、SendKey、Bot Token、PUSH_KEY）**都不在代码里**，而是存在
  **GitHub Secrets**（加密）和 **Cloudflare KV** 中。
- `PUSH_KEY` 是你自编的门禁口令，用来防止别人乱调用你的 Worker 接口。
- 建议不要公开分享带 Token 的截图（尤其是浏览器地址栏）。
- 本项目不收集、不上传你的任何数据到第三方服务器（只在 GitHub / Cloudflare / Server酱 之间流转）。

---

## 🗺 Roadmap

- [ ] 用 Canvas API 自动检测「已提交」，完成即反馈经验值
- [ ] 等级与称号系统（Lv.3 学徒冒险者 → Lv.7 深渊猎手）
- [ ] 周日晚生成「本周战报」
- [ ] 支持飞书 / 钉钉 / Discord 卡片按钮
- [ ] 一键部署到 Cloudflare 的按钮

---

## 📄 License

[MIT](LICENSE) — 随便用、随便改，欢迎提 Issue 和 PR。
