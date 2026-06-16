---
name: daily-brief
description: 抓取 DailyBrief 的登录墙源（X / 小红书 / 微信公众号等 runner=agent 源），用 web-access CDP 浏览器读取登录态内容，写入 agent-inbox.json，再由 DailyBrief 管线生成「登录墙补充」简报。当用户要刷新 DailyBrief 的登录墙源、或运行本机补充简报时使用。
---

# DailyBrief — 登录墙源抓取（Slice-2）

把 `sources.yaml` 里 `runner: agent` 的源（X / 小红书 / 公众号）用真实登录态浏览器抓回来，
写进 `agent-inbox.json`，再由确定性管线去重/摘要/投递成「登录墙补充」简报。

## 流程

### 1. 确认 CDP 可用
**先加载 web-access skill 并遵循其指引**，运行其 `check-deps.mjs`，确保 CDP Proxy 已连上你的浏览器
（Chrome/Edge 需开启 remote debugging）。若未连上，按 web-access 的提示让用户开启后再继续。

### 2. 读取要抓的源
读项目根的 `sources.yaml`，取所有 `enabled: true` 且 `runner: agent` 的条目
（字段：`id, type, ref, name, weight`）。

### 3. 逐源抓取（web-access CDP）
对每个源，按其 `ref`（账号主页/页面 URL）用 CDP 打开后台 tab，提取**最近 24–36 小时**的帖子/文章。
每条产出一个对象：

| 字段 | 说明 |
|---|---|
| `source_id` | 必须与 sources.yaml 的 id 一致（用于归类去重） |
| `source_type` | `x` / `xiaohongshu` / `wechat` |
| `title` | 帖子标题或首句 |
| `url` | 该帖**永久链接**（站内交互自然到达的完整 URL，含必要参数，不要手拼） |
| `published_at` | ISO-8601；拿不到精确时间就用当天日期 |
| `author` / `source_name` | 作者 / 账号名 |
| `body` | 正文文本（截断到约 1500 字） |

纪律（继承 web-access + DailyBrief 铁律）：
- 只取真实可见内容，**绝不编造**；每条**必须有真实 url**。
- 像人一样浏览，避免高频构造 URL 触发风控；**一个源失败就跳过**，不影响其它源。
- 多个源相互独立，可分治给子 agent 并行（各自 `/new` 开 tab、各自 `/close`）。

### 4. 写入 inbox
把所有条目写入项目根 `agent-inbox.json`：
```json
{ "items": [
  {
    "source_id": "x-karpathy",
    "source_type": "x",
    "title": "Some post title or first line",
    "url": "https://x.com/karpathy/status/1234567890",
    "published_at": "2026-06-16T08:00:00+00:00",
    "author": "Andrej Karpathy",
    "source_name": "Andrej Karpathy (X)",
    "body": "Full post text..."
  }
] }
```

### 5. 生成并投递「登录墙补充」简报
用**独立 state**，避免与云端主报重复投递：
```powershell
# 在项目目录下（PowerShell）
$env:DAILYBRIEF_STATE = "agent-state.json"
python daily_brief.py --runner agent --label "登录墙补充"
# 先看不投递：加 --dry-run
```
- `--runner agent`：只处理登录墙源（读 `agent-inbox.json`），不碰 keyless（云端已投）。
- `agent-state.json` 独立去重，与云端 `feed/state.json`、本机 `state.json` 互不干扰。

## 分工总览
- **云端 GitHub Actions**：keyless 主报（PC 关机也跑）。
- **本机（此 skill）**：登录墙补充（需登录态浏览器，PC 开机时跑）。
- 两者源不重叠 → 不会重复投递。
