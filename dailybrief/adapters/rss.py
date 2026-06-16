"""RSS / Atom / blog-feed adapter. Keyless, runs anywhere (runner=actions)."""
from .base import http_get, parse_feed, register


@register("rss")
@register("blog")
@register("atom")
def fetch_rss(source: dict):
    content = http_get(source["ref"])
    return parse_feed(content, source, "rss")
