"""Adapter registry + shared feed parsing.

A source adapter is just `fetch(source: dict) -> list[NewsItem]`, registered by
`type`. New source type = one new adapter file. This is the seam that makes the
source list open-ended.
"""
import calendar
import html
import re
import time
from datetime import datetime, timezone

import feedparser
import httpx

from ..models import NewsItem

USER_AGENT = "Mozilla/5.0 (compatible; DailyBrief/0.1; +https://github.com/daily-brief)"

REGISTRY: dict[str, callable] = {}


def register(source_type: str):
    def deco(fn):
        REGISTRY[source_type] = fn
        return fn
    return deco


def get_adapter(source_type: str):
    return REGISTRY.get(source_type)


def _transport() -> httpx.HTTPTransport:
    # Force IPv4 to avoid IPv6 DNS issues on some systems (same as the
    # merch-canvas Agnes client).
    return httpx.HTTPTransport(local_address="0.0.0.0")


def _get(url: str, timeout: int, user_agent: str | None, retries: int):
    ua = user_agent or USER_AGENT
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(transport=_transport(), timeout=timeout,
                              follow_redirects=True, headers={"User-Agent": ua}) as c:
                r = c.get(url)
                r.raise_for_status()
                return r
        except httpx.HTTPStatusError as e:  # retry transient server errors + rate limits
            last_exc = e
            code = e.response.status_code
            if attempt < retries and (code >= 500 or code == 429):
                if code == 429:
                    time.sleep(3 * (attempt + 1))
                continue
            raise
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < retries:
                continue
            raise
    raise last_exc  # pragma: no cover


def http_get(url: str, timeout: int = 30, user_agent: str | None = None, retries: int = 2) -> bytes:
    return _get(url, timeout, user_agent, retries).content


def http_get_text(url: str, timeout: int = 30, user_agent: str | None = None, retries: int = 2) -> str:
    return _get(url, timeout, user_agent, retries).text


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str, limit: int = 1500) -> str:
    if not s:
        return ""
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _to_iso(struct_time) -> str | None:
    if not struct_time:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc).isoformat()
    except Exception:
        return None


def parse_feed(content: bytes, source: dict, source_type: str) -> list[NewsItem]:
    """Parse RSS/Atom (or YouTube channel-RSS) bytes into NewsItems."""
    d = feedparser.parse(content)
    feed_title = (d.feed.get("title") if getattr(d, "feed", None) else "") or ""
    src_name = source.get("name") or feed_title or source.get("id", "")
    items: list[NewsItem] = []
    for e in d.entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or e.get("id") or "").strip()
        if not title or not link:
            continue
        published = _to_iso(e.get("published_parsed") or e.get("updated_parsed"))
        body = (e.get("summary") or e.get("description")
                or e.get("media_description") or "")
        items.append(NewsItem(
            source_id=source.get("id", src_name),
            source_type=source_type,
            title=title,
            url=link,
            published_at=published,
            author=e.get("author") or src_name,
            body=strip_html(body),
            source_name=src_name,
            weight=source.get("weight", "normal"),
        ))
    return items
