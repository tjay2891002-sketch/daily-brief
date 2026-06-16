"""Agent inbox: items the web-access (CDP) fetch step deposits for login-wall
sources (X / 小红书 / 公众号).

This decouples non-deterministic browser automation (driven by Claude Code via
the web-access skill) from the deterministic pipeline: the agent writes a JSON
file of NewsItem-shaped dicts; the pipeline reads it like any other source.

Format (either is accepted):
    {"items": [ {source_id, source_type, title, url, published_at, ...}, ... ]}
    [ {source_id, ...}, ... ]
"""
import json
import logging

from .models import NewsItem

log = logging.getLogger("dailybrief.inbox")


def load_inbox(path: str) -> dict:
    """Return {source_id: [NewsItem, ...]} from the inbox file. Missing or
    invalid file -> {} (the run simply has no agent items)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return {}
    raw = data.get("items", []) if isinstance(data, dict) else data
    out: dict[str, list] = {}
    for d in raw or []:
        try:
            it = NewsItem.from_dict(d)
        except Exception:
            continue
        if not it.title or not it.url:
            continue
        out.setdefault(it.source_id, []).append(it)
    if out:
        log.info("inbox loaded: %d source(s), %d item(s) from %s",
                 len(out), sum(len(v) for v in out.values()), path)
    return out
