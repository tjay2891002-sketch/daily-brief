"""Reddit adapter (keyless).

Reddit now 403-blocks its unauthenticated `.json` API for non-OAuth clients
(even with a browser UA), but its `.rss`/Atom feed still works. So this adapter
DEFAULTS to RSS (reliable) and treats `.json` as an opt-in (richer: score,
num_comments, external link) with an automatic RSS fallback when Reddit blocks
it. A real browser User-Agent is required either way.

ref accepts: 'MachineLearning', 'r/MachineLearning', a subreddit URL, or a full
'.rss'/'.json' URL. Add `mode: json` to a source to prefer the JSON API.
Caveat: Reddit may also rate-limit datacenter IPs (some GitHub Actions runners).
"""
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import http_get, parse_feed, register

log = logging.getLogger("dailybrief.reddit")

# Politeness throttle: Reddit rate-limits rapid sequential requests (429).
_THROTTLE_LOCK = threading.Lock()
_MIN_INTERVAL_S = 3.0
_last_call = [0.0]


def _throttle():
    with _THROTTLE_LOCK:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


# Reddit blocks bot-like UAs; a real browser UA works for the keyless RSS feed.
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_JSON_QUERY = "top.json?t=day&limit=25"
_RSS_QUERY = "top/.rss?t=day"


def _subreddit(ref: str) -> str:
    ref = (ref or "").strip()
    m = re.search(r"reddit\.com/(r/\w+)", ref)
    if m:
        return m.group(1)
    return ref if ref.lower().startswith("r/") else f"r/{ref}"


def _wants_json(source: dict) -> bool:
    ref = (source.get("ref") or "").strip()
    return source.get("mode") == "json" or ref.endswith(".json") or ".json?" in ref


def _fetch_json(source: dict):
    ref = source["ref"].strip()
    url = (ref if ref.startswith("http") and ".json" in ref
           else f"https://www.reddit.com/{_subreddit(ref)}/{_JSON_QUERY}")
    _throttle()
    data = json.loads(http_get(url, user_agent=_BROWSER_UA))
    children = (data.get("data") or {}).get("children") or []
    src_name = source.get("name") or source.get("id")
    items = []
    for ch in children:
        d = ch.get("data") or {}
        if d.get("stickied") or d.get("over_18"):
            continue
        title = (d.get("title") or "").strip()
        permalink = d.get("permalink") or ""
        if not title or not permalink:
            continue
        created = d.get("created_utc")
        external = d.get("url") or ""
        if external.startswith("https://www.reddit.com") or external.startswith("/r/"):
            external = ""
        items.append(NewsItem(
            source_id=source.get("id", src_name),
            source_type="reddit",
            title=title,
            url=f"https://www.reddit.com{permalink}",
            published_at=(datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None),
            author=f"u/{d.get('author')}" if d.get("author") else src_name,
            body=(d.get("selftext") or "").strip()[:1500],
            source_name=src_name,
            weight=source.get("weight", "normal"),
            raw_meta={"score": d.get("score"), "num_comments": d.get("num_comments"),
                      "subreddit": d.get("subreddit"), "external_url": external or None},
        ))
    return items


def _fetch_rss(source: dict):
    ref = source["ref"].strip()
    url = (ref if ref.startswith("http") and ".rss" in ref
           else f"https://www.reddit.com/{_subreddit(ref)}/{_RSS_QUERY}")
    _throttle()
    return parse_feed(http_get(url, user_agent=_BROWSER_UA), source, "reddit")


@register("reddit")
def fetch_reddit(source: dict):
    if _wants_json(source):
        try:
            return _fetch_json(source)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (401, 403, 429):
                log.info("reddit .json blocked (%s) for %s — falling back to RSS",
                         code, source.get("id"))
            else:
                raise
    return _fetch_rss(source)
