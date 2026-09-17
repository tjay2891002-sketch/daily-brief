# DailyBrief — 每日行业资讯简报（Slice-0 MVP）

一个**每日自动刷新、源完全开放**的行业资讯简报系统。Slice-0 是最小可上线切片：
**keyless RSS + YouTube channel-RSS → 精确去重 → DeepSeek 摘要 → Telegram 投递**。
不碰登录墙源、不做聚类/翻译——先把「关掉一切花活也每天送达」的主链跑通。

> 完整设计与后续阶段（Phase 1 登录墙源 / Phase 2 GitHub Actions PC-无关心跳 /
> Phase 3 Pulse 服务）见 [`../docs/daily-news-digest-design.md`](../docs/daily-news-digest-design.md)。

## 它做什么

1. 读 `sources.yaml`（你拥有的源清单）+ `config.json`（偏好）+ `state.json`（去重游标）。
2. 对每个 `runner=actions` 的 keyless 源抓取，归一化成统一的 `NewsItem`（**每条强制带 source URL**）。
3. 按时间窗口过滤 + SHA-1 精确去重 + 每源/总量配额。
4. 用 DeepSeek（`deepseek-chat`）逐条摘要（失败自动降级为摘录，并汇总降级条数）。
5. 组装成纯文本简报，投递到 Telegram（并始终在终端回显）。
6. **投递成功后**才推进 `state.json` 去重游标（崩溃不漏报、不重报）。

## 快速开始

```bash
cd daily-brief
python -m venv .venv && .venv\Scripts\activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env            # 填入 LLM_API_KEY（+ 可选 Telegram）
copy config.example.json config.json

# 首次冒烟测试：忽略时间窗口、不写状态、不投递，只在终端看输出
python daily_brief.py --backfill 3 --no-state --dry-run
```

看到终端打印出带摘要和链接的简报，主链就通了。

### 接 Telegram（真正自动投递）

1. Telegram 里找 `@BotFather` → `/newbot` → 拿 bot token。
2. **给你的新 bot 发一条消息**（必须，否则拿不到 chat_id）。
3. 取 chat_id：
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python -c "import sys,json;print(json.load(sys.stdin)['result'][-1]['message']['chat']['id'])"
   ```
4. 把 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 填进 `.env`，确保 `config.json` 里 `delivery.method` = `telegram`。
5. 正式跑一次：
   ```bash
   python daily_brief.py
   ```

### 每天自动跑（Windows Task Scheduler）

```powershell
$py = (Get-Command python).Source
schtasks /Create /SC DAILY /ST 07:30 /TN DailyBrief `
  /TR "$py `"$PWD\daily_brief.py`"" /F
# 勾「唤醒计算机运行此任务」+「错过后尽快补跑」可缓解合盖错过（任务计划程序 GUI 里设）
schtasks /Query /TN DailyBrief
```

跨平台等价：`crontab -e` → `30 7 * * * cd /path/daily-brief && python daily_brief.py`

## 加 / 改源

编辑 `sources.yaml`，加一行即可。当前支持 `rss` / `blog` / `atom` / `youtube` / `reddit`（全 keyless）：

```yaml
  - id: my-blog
    type: rss
    ref: https://example.com/feed.xml
    name: My Blog
    runner: actions
    weight: normal      # lead | normal | brief
    enabled: true
```

- YouTube 频道支持 `@handle` / 频道 URL / `channel_id=UC...` / `playlist_id=PL...`（`@handle` 会自动解析 channelId）。
- Reddit 用 keyless RSS：`ref` 写子版名（`MachineLearning`）或多版合并（`A+B+C`，**推荐**，1 次请求避免 Reddit 限流）。`.json` API 需 OAuth，默认走 RSS。
- 登录墙源（X / 微信公众号 / 小红书）走 `runner=agent`，属于 Slice-2（需本机浏览器），Slice-0 会自动跳过。

**近重复合并（Slice-1）**：多个源报道同一件事时，按标题归一化 + Jaccard 相似度自动合并成一条，其余源以「↳ 另见」附在下方。阈值见 `config.json` 的 `dedup.near_dup_threshold`（默认 0.62），`--no-merge` 可关闭。

## 命令行参数

| 参数 | 作用 |
|---|---|
| `--dry-run` | 只在终端打印，不投递到 Telegram |
| `--no-state` | 忽略 seen 去重集，也不写 `state.json`（测试用） |
| `--backfill N` | 忽略时间窗口，每源取最新 N 条（首测/补档用） |
| `--max-total N` | 覆盖 `volume.max_items_total` |
| `--no-merge` | 关闭标题近重复合并（调试用） |

## 自定义摘要风格

改 `prompts/summarize.md`（纯英文/中文指令，非代码）。比如想「更短、带 emoji、每条 1 句」，
直接改这个文件即可，下次运行生效。

## 结构

```
daily-brief/
  daily_brief.py          # 入口：fetch → select → summarize → render → deliver → state
  sources.yaml            # 你拥有的源清单（加源 = 加一行）
  config.example.json     # 偏好模板（复制成 config.json）
  .env.example            # 密钥模板（复制成 .env，已 gitignore）
  prompts/summarize.md    # 摘要指令（可改）
  dailybrief/
    models.py             # NewsItem 归一化数据形状（url 强制必填）
    config.py             # 加载 .env + config.json
    state.py              # SHA-1 去重 + 原子写 state.json
    summarize.py          # LLM 摘要（env 取 key，失败降级并汇总）
    dedup.py              # 标题归一化 + Jaccard 近重复合并（Slice-1）
    render.py             # 组装纯文本简报
    deliver.py            # Telegram（4096 分块）+ stdout
    adapters/
      base.py             # 适配器注册表 + 共享 feed 解析 + 5xx/429 重试
      rss.py              # RSS/Atom/blog
      youtube.py          # YouTube channel-RSS（@handle 自动解析）
      reddit.py           # Reddit keyless RSS（多版合并；.json 可选）
```

全程 Python（设计文档 §9.1）：同一套 `adapters/` + `NewsItem` 契约，Phase 2 的 GitHub
Actions 和 Phase 3 的 FastAPI/Pulse 直接复用，无需重写。

## 安全

- 所有密钥只在 `.env`（gitignore）或环境变量里，**绝不进源码**。
- `config.json` / `state.json` 也已 gitignore（可能含偏好/抓取正文）。
