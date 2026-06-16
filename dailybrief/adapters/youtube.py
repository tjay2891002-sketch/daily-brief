"""YouTube channel/playlist adapter via the keyless channel-RSS feed.

Accepts any of: a full feeds/videos.xml URL, a channel_id (UC...), a
playlist_id (PL...), or a channel page / @handle URL (resolved to channelId by
scraping the page once). No API key required.
"""
import re

from .base import http_get, http_get_text, parse_feed, register

_FEED = "https://www.youtube.com/feeds/videos.xml"


def channel_feed_url(ref: str) -> str:
    ref = (ref or "").strip()
    if "feeds/videos.xml" in ref:
        return ref
    m = re.search(r"channel_id=([\w-]+)", ref)
    if m:
        return f"{_FEED}?channel_id={m.group(1)}"
    m = re.search(r"(?:playlist_id=|[?&]list=)([\w-]+)", ref)
    if m:
        return f"{_FEED}?playlist_id={m.group(1)}"
    m = re.search(r"/channel/(UC[\w-]{20,})", ref) or re.fullmatch(r"(UC[\w-]{20,})", ref)
    if m:
        return f"{_FEED}?channel_id={m.group(1)}"
    # @handle or custom channel URL: scrape the page for the canonical channelId.
    page = http_get_text(ref if ref.startswith("http") else f"https://www.youtube.com/{ref.lstrip('/')}")
    m = (re.search(r'"channelId":"(UC[\w-]+)"', page)
         or re.search(r'"externalId":"(UC[\w-]+)"', page)
         or re.search(r'<meta itemprop="(?:identifier|channelId)" content="(UC[\w-]+)">', page))
    if m:
        return f"{_FEED}?channel_id={m.group(1)}"
    raise ValueError(f"could not resolve YouTube channelId for ref: {ref!r}")


@register("youtube")
def fetch_youtube(source: dict):
    url = channel_feed_url(source["ref"])
    content = http_get(url)
    return parse_feed(content, source, "youtube")
