"""Near-duplicate detection — the 'approximate' layer of the three-layer dedup
model (exact -> approximate -> semantic).

Exact dedup (canonical URL / content hash) runs first in state.py. Semantic
dedup (embeddings) is deferred to Phase 3. Here we catch the same story reported
by multiple sources whose URLs differ but whose titles are close, via title
normalization + Jaccard token similarity + union-find clustering. O(n^2) pairwise
is fine at digest scale (tens to low hundreds of items pre-cap).
"""
import re
import unicodedata

# Editorial prefixes/tags to strip before comparing.
_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\[[^\]]{1,20}\]"                      # [AINews] [D] [P] [R] [N] [Discussion]
    r"|show hn:|ask hn:|tell hn:"           # HN
    r"|psa:|tl;?dr:|breaking:|update:|opinion:|analysis:|exclusive:|video:"
    r")\s*",
    re.IGNORECASE,
)
# Trailing " - Site" / " | Site" / " — Site" site-name suffix.
_SUFFIX_RE = re.compile(r"\s*[|\-–—]\s*[^|\-–—]{1,40}$")
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
         "are", "with", "how", "why", "what", "new", "says", "will", "be",
         "at", "as", "by", "from", "its", "this", "that"}


def _strip_emoji_symbols(s: str) -> str:
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N") or ch.isspace():
            out.append(ch)
        elif cat[0] == "P":
            out.append(" ")          # punctuation -> word boundary
        # symbols / emoji dropped
    return "".join(out)


def normalize_title(title: str) -> str:
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title).strip()
    prev = None
    while prev != s:                  # peel stacked prefixes e.g. "[D] [P] ..."
        prev = s
        s = _PREFIX_RE.sub("", s)
    s = _SUFFIX_RE.sub("", s)
    s = _strip_emoji_symbols(s).lower()
    return re.sub(r"\s+", " ", s).strip()


def title_tokens(normalized: str) -> set:
    """Latin titles -> content words + bigrams. CJK-heavy titles -> char bigrams
    (word shingles are too sparse for short CJK headlines)."""
    if not normalized:
        return set()
    if len(_CJK_RE.findall(normalized)) >= 4:
        chars = [c for c in normalized if not c.isspace()]
        return {a + b for a, b in zip(chars, chars[1:])} or set(chars)
    words = [w for w in normalized.split() if w not in _STOP and len(w) > 1]
    if not words:
        words = normalized.split()
    toks = set(words)
    toks |= {f"{a}_{b}" for a, b in zip(words, words[1:])}
    return toks


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _better_rep(a, b) -> bool:
    """Is item `a` a better cluster representative than `b`?
    Prefer higher weight, then more recent, then richer body."""
    rank = {"lead": 0, "normal": 1, "brief": 2}
    wa, wb = rank.get(a.weight, 1), rank.get(b.weight, 1)
    if wa != wb:
        return wa < wb
    pa, pb = a.published_at or "", b.published_at or ""
    if pa != pb:
        return pa > pb
    return len(a.body or "") >= len(b.body or "")


def merge_near_duplicates(items, threshold: float = 0.62):
    """Cluster items by title similarity; return one representative per cluster.
    The representative gains raw_meta['also_seen'] (other sources, for rendering)
    and raw_meta['merged_dedup_keys'] (so state marks them all seen)."""
    n = len(items)
    if n < 2:
        return list(items)
    toks = [title_tokens(normalize_title(it.title)) for it in items]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        if not toks[i]:
            continue
        for j in range(i + 1, n):
            if toks[j] and jaccard(toks[i], toks[j]) >= threshold:
                parent[find(j)] = find(i)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    out = []
    for idxs in clusters.values():
        members = [items[i] for i in idxs]
        rep = members[0]
        for m in members[1:]:
            if _better_rep(m, rep):
                rep = m
        others = [m for m in members if m is not rep]
        if others:
            seen_urls = {rep.url}
            also = []
            for m in others:
                if m.url not in seen_urls:
                    also.append({"name": m.source_name or m.source_id, "url": m.url})
                    seen_urls.add(m.url)
            rep.raw_meta["also_seen"] = also
            rep.raw_meta["merged_dedup_keys"] = [m.dedup_key for m in others]
        out.append(rep)
    return out
