# Phase 2 — GitHub Actions 云端心跳（电脑关机也能每天出报）

把 keyless 源的抓取+投递搬到 GitHub Actions 的免费定时任务上，**PC 关机/休眠也能每天 07:30 收到简报**。成本 **$0/月**（私有仓库每月 2000 免费分钟，日报每次 1–3 分钟）。

## 工作原理
- `.github/workflows/feed.yml`：每天 23:30 UTC（= 07:30 Asia/Shanghai）+ 可手动触发。
- 跑 `python daily_brief.py`，用 **Actions Secrets** 注入 key/token。
- 云端用**独立的** `feed/config.json` + `feed/state.json`（与本机的 `config.json`/`state.json` 分开，互不干扰）。每次跑完把 `feed/state.json` commit 回仓库做跨天去重。

## 一次性设置（5 步）

**1. 建一个空的私有仓库**
GitHub → New repository → 勾 **Private** → 不要加 README → Create。

**2. 把本项目推上去**（在 `daily-brief/` 目录里）
```bash
git init
git add .
git commit -m "DailyBrief: Slice-1 + Phase 2"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```
`.gitignore` 已确保 `.env` / 本机 `config.json` / `state.json` **不会**被推上去（密钥安全）。

**3. 加 3 个 Secret**
仓库 → Settings → Secrets and variables → Actions → New repository secret，加：
| Name | Value |
|---|---|
| `LLM_API_KEY` | 你的 LLM key（DeepSeek） |
| `TELEGRAM_BOT_TOKEN` | 你 bot 的 token（@BotFather 获取）—— **只填在 GitHub Secrets，绝不要写进本文件** |
| `TELEGRAM_CHAT_ID` | 你的 chat id（获取方式见仓库根的 `.env.example`） |

（`LLM_BASE_URL` 已在 workflow 里写死，无需加。）

**4. 手动测一次**
仓库 → Actions 标签 → 左侧 “Daily Brief” → **Run workflow**。看绿勾 + Telegram 收到简报即成功。

**5. 关掉本机的定时任务，避免重复投递**
云端成为主心跳后，本机那条会和它各自维护去重状态、导致一天收两份：
```powershell
schtasks /Change /TN DailyBrief /DISABLE   # 停用（保留，随时可恢复）
# 或 schtasks /Delete /TN DailyBrief /F     # 直接删除
```
本机仍可随时手动出报：`python daily_brief.py`。

## 改设置
- **时间**：改 `feed.yml` 里的 cron（UTC）。07:30 CST = `30 23 * * *`；想 08:00 CST 就 `0 0 * * *`。
- **语言/数量/源**：云端改 `feed/config.json` 和 `sources.yaml`，commit + push 即生效。

## 注意事项（诚实版）
- **Reddit 在云端大概率抓不到**：GitHub 的数据中心 IP 会被 Reddit 403/429。其它源（RSS/官方/YouTube）正常。想要 Reddit，就保留本机心跳专门跑它（Slice-2 会把这条理顺）。
- **GitHub 定时不精准**：高峰期可能晚 5–15 分钟，属正常。
- **60 天无活动会自动停用定时**：机器人每天 commit `feed/state.json` 算活动，会自我续命，不用管。
