"""Cross-run dedup state.

state.json = { "seen": {sha1: first_seen_iso}, "last_run": iso }. The watermark
is only advanced AFTER a successful delivery (atomic temp+replace write), so a
crash never skips items that were never shown (design doc invariant).
"""
import json
import os
import tempfile
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("seen", {})
            return data
    except (FileNotFoundError, ValueError):
        return {"seen": {}, "last_run": None}


def save_state(path: str, state: dict) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # atomic on Windows + POSIX
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def filter_unseen(items, state):
    """Drop items already in state['seen'] and de-dup within the batch."""
    seen = state.get("seen", {})
    batch, out = set(), []
    for it in items:
        k = it.dedup_key
        if k in seen or k in batch:
            continue
        batch.add(k)
        out.append(it)
    return out


def mark_seen(items, state):
    """Record items as seen and advance last_run. Bounds the seen set to the
    most recent 5000 keys to keep state.json small."""
    seen = state.setdefault("seen", {})
    ts = now_iso()
    for it in items:
        seen[it.dedup_key] = ts
        # also mark items that were merged into this one (near-dup layer),
        # so none of them resurface tomorrow.
        for k in it.raw_meta.get("merged_dedup_keys", []):
            seen[k] = ts
    state["last_run"] = ts
    if len(seen) > 5000:
        kept = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:5000]
        state["seen"] = dict(kept)
    return state
