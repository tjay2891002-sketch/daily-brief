"""The single normalized data shape every source collapses into.

Invariant (design doc): every NewsItem MUST carry a `url`. Dedup, ranking,
summarization, rendering and the future DB migration all operate on this one
shape, so they are written once and are source-agnostic.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "gclid", "fbclid", "mc_cid", "mc_eid", "ref",
    "ref_src", "ref_url", "cmpid", "spm", "scm", "igshid",
}


def canonical_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase host, drop www., strip tracking
    params, drop fragment, normalize trailing slash. Best-effort; returns the
    trimmed input on any parse error."""
    if not url:
        return ""
    try:
        s = urlsplit(url.strip())
        # Normalize scheme to https: http/https of the same article are the same
        # item for dedup purposes (this value is only used for the dedup key).
        scheme = "https"
        netloc = s.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        kept = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=False)
                if k.lower() not in _TRACKING_PARAMS]
        query = urlencode(sorted(kept))
        path = s.path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return url.strip()


@dataclass
class NewsItem:
    source_id: str
    source_type: str                       # 'rss' | 'youtube' (Slice-0)
    title: str
    url: str                               # REQUIRED — every item is traceable
    published_at: Optional[str] = None     # ISO-8601 UTC
    author: Optional[str] = None
    body: str = ""                         # raw text/description/transcript
    source_name: str = ""
    weight: str = "normal"                 # lead | normal | brief
    summary: Optional[str] = None          # filled by the summarize stage
    raw_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        canon = canonical_url(self.url) or f"{self.source_id}|{self.title}"
        return hashlib.sha1(canon.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NewsItem":
        """Build from a plain dict (e.g. the agent-written inbox); tolerant of
        a few key aliases."""
        return cls(
            source_id=d.get("source_id") or d.get("source") or "",
            source_type=d.get("source_type") or d.get("type") or "agent",
            title=(d.get("title") or "").strip(),
            url=(d.get("url") or "").strip(),
            published_at=d.get("published_at") or d.get("date"),
            author=d.get("author"),
            body=(d.get("body") or d.get("text") or "")[:4000],
            source_name=d.get("source_name") or d.get("name") or "",
            weight=d.get("weight", "normal"),
            raw_meta=d.get("raw_meta") or {},
        )
