"""Config + secrets loading.

Preferences come from config.json (non-secret, committable). Secrets
(LLM_API_KEY, TELEGRAM_*) come ONLY from the environment / .env — never
hardcoded in source (design doc section 9.3).
"""
import json
import os

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv optional; env vars still work without it
    load_dotenv = None

DEFAULTS = {
    "profile": {
        "industry": "AI / 科技",
        "interests": ["AI", "LLM", "agents", "生成式设计", "创业"],
        "exclude_keywords": [],
    },
    "language": "zh",
    "timezone": "Asia/Shanghai",
    "lookback_hours": 36,
    "volume": {"max_items_total": 20, "max_items_per_source": 5, "lead_count": 3},
    "dedup": {"near_dup_threshold": 0.62},
    "delivery": {"method": "telegram"},
    "summarizer": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "max_chars": 2000,
        "language": "zh",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(project_dir: str) -> dict:
    """Load .env then merge config.json over built-in DEFAULTS.

    Search order for config.json: <project_dir>/config.json, then
    ~/.daily-brief/config.json. First hit wins."""
    if load_dotenv:
        load_dotenv(os.path.join(project_dir, ".env"))

    search = []
    if os.getenv("DAILYBRIEF_CONFIG"):           # explicit override (used by CI)
        search.append(os.getenv("DAILYBRIEF_CONFIG"))
    search += [
        os.path.join(project_dir, "config.json"),
        os.path.expanduser("~/.daily-brief/config.json"),
    ]
    cfg = dict(DEFAULTS)
    for path in search:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                cfg = _deep_merge(DEFAULTS, json.load(f))
            break
    return cfg
