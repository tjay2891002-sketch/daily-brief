#!/usr/bin/env python3
"""DailyBrief Slice-0 entrypoint.

Flow: load config + sources + state -> fetch each source (per-source isolation)
-> window/dedup/cap -> Agnes summarize -> render -> deliver -> advance state
(only on successful delivery).

Examples:
    python daily_brief.py --backfill 3 --no-state --dry-run   # first smoke test
    python daily_brief.py                                     # real daily run
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import yaml

from dailybrief import adapters  # noqa: F401  (registers adapters on import)
from dailybrief.adapters import base
from dailybrief.config import load_config
from dailybrief.dedup import merge_near_duplicates
from dailybrief.deliver import deliver
from dailybrief.render import render_brief
from dailybrief.state import filter_unseen, load_state, mark_seen, now_iso, save_state
from dailybrief.summarize import summarize_items

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("dailybrief")


def load_sources(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [s for s in (data.get("sources") or []) if s.get("enabled", True)]


def within_window(iso: str, hours: int) -> bool:
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso) >= datetime.now(timezone.utc) - timedelta(hours=hours)
    except Exception:
        return False


def fetch_all(sources: list[dict]) -> list:
    items = []
    for s in sources:
        if s.get("runner", "actions") == "agent":
            log.info("skip runner=agent source (login-wall, deferred to Slice-2): %s", s.get("id"))
            continue
        adapter = base.get_adapter(s.get("type"))
        if not adapter:
            log.warning("no adapter for type=%r (source %s)", s.get("type"), s.get("id"))
            continue
        try:
            got = adapter(s)
            log.info("fetched %d from %s", len(got), s.get("id"))
            items.extend(got)
        except Exception as e:  # one bad source never breaks the run
            log.warning("source failed %s: %s", s.get("id"), e)
    return items


def select(items: list, cfg: dict, backfill: int, use_state: bool, state: dict, merge: bool = True) -> list:
    # 1. recency window (or backfill: latest N per source ignoring the window)
    if backfill:
        by_src: dict[str, list] = {}
        for it in sorted(items, key=lambda x: x.published_at or "", reverse=True):
            bucket = by_src.setdefault(it.source_id, [])
            if len(bucket) < backfill:
                bucket.append(it)
        items = [it for bucket in by_src.values() for it in bucket]
    else:
        hours = cfg.get("lookback_hours", 36)
        items = [it for it in items if within_window(it.published_at, hours)]

    # 2. dedup (vs persistent state, or just within-batch when --no-state)
    if use_state:
        items = filter_unseen(items, state)
    else:
        seen, uniq = set(), []
        for it in items:
            if it.dedup_key in seen:
                continue
            seen.add(it.dedup_key)
            uniq.append(it)
        items = uniq

    # 2b. near-duplicate merge (approximate layer): collapse the same story from
    # multiple sources into one item, attaching the others as "also seen".
    if merge:
        before = len(items)
        items = merge_near_duplicates(items, cfg.get("dedup", {}).get("near_dup_threshold", 0.62))
        if len(items) != before:
            log.info("near-dup merge: %d -> %d items", before, len(items))

    # 3. exclude-keyword filter
    excl = [k.lower() for k in cfg.get("profile", {}).get("exclude_keywords", []) if k]
    if excl:
        items = [it for it in items
                 if not any(k in (it.title + " " + it.body).lower() for k in excl)]

    # 4. sort newest-first, cap per source, cap total
    items.sort(key=lambda x: x.published_at or "", reverse=True)
    vol = cfg.get("volume", {})
    per = vol.get("max_items_per_source", 5)
    count: dict[str, int] = {}
    capped = []
    for it in items:
        c = count.get(it.source_id, 0)
        if c >= per:
            continue
        count[it.source_id] = c + 1
        capped.append(it)
    items = capped[: vol.get("max_items_total", 20)]

    # 5. mark lead stories
    lead_n = vol.get("lead_count", 3)
    for i, it in enumerate(items):
        it.weight = "lead" if i < lead_n else "normal"
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="DailyBrief Slice-0 — daily industry news digest")
    ap.add_argument("--dry-run", action="store_true", help="print only; do not deliver to the channel")
    ap.add_argument("--no-state", action="store_true", help="ignore the seen-set and do not persist state")
    ap.add_argument("--backfill", type=int, default=0, metavar="N",
                    help="ignore the time window; take the latest N items per source (good for first test)")
    ap.add_argument("--max-total", type=int, help="override volume.max_items_total")
    ap.add_argument("--no-merge", action="store_true", help="disable near-duplicate title merging")
    args = ap.parse_args()

    # Windows consoles default to a legacy code page (e.g. cp936/GBK) that cannot
    # encode emoji or many non-CJK chars; force UTF-8 so print()/logging never crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    cfg = load_config(PROJECT_DIR)
    if args.max_total:
        cfg.setdefault("volume", {})["max_items_total"] = args.max_total

    sources = load_sources(os.path.join(PROJECT_DIR, "sources.yaml"))
    log.info("loaded %d enabled source(s)", len(sources))
    state_path = os.getenv("DAILYBRIEF_STATE") or os.path.join(PROJECT_DIR, "state.json")
    state = load_state(state_path)

    items = fetch_all(sources)
    items = select(items, cfg, args.backfill, use_state=not args.no_state, state=state, merge=not args.no_merge)

    if not items:
        zh = str(cfg.get("language", "en")).startswith("zh")
        msg = "今天没有新的行业更新，明天见！" if zh else "No new industry updates today. Check back tomorrow!"
        log.info("no new items after filtering")
        deliver(msg, cfg, dry_run=args.dry_run)
        return 0

    log.info("summarizing %d item(s)...", len(items))
    summarize_items(items, cfg, os.path.join(PROJECT_DIR, "prompts"))
    text = render_brief(items, cfg, now_iso())
    ok = deliver(text, cfg, dry_run=args.dry_run)

    if ok and not args.no_state and not args.dry_run:
        mark_seen(items, state)
        save_state(state_path, state)
        log.info("delivered; state advanced (%d keys tracked)", len(state.get("seen", {})))
    elif not ok:
        log.error("delivery failed; state NOT advanced (will retry these items next run)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
