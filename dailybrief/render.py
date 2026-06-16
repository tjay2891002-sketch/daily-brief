"""Assemble items into one brief. Plain text with inline URLs so the same
output works for Telegram (no MarkdownV2 escaping needed) and stdout."""
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py<3.9 fallback
    ZoneInfo = None


def _local(iso: str, tz: str):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if ZoneInfo and tz:
            dt = dt.astimezone(ZoneInfo(tz))
        return dt
    except Exception:
        return None


def _fmt_time(iso: str, tz: str) -> str:
    dt = _local(iso, tz)
    return dt.strftime("%m-%d %H:%M") if dt else ""


def render_brief(items, cfg, run_iso: str) -> str:
    tz = cfg.get("timezone", "UTC")
    lang = str(cfg.get("language", "en"))
    zh = lang.startswith("zh")
    industry = cfg.get("profile", {}).get("industry", "").strip()

    today = _local(run_iso, tz)
    date_str = today.strftime("%Y-%m-%d") if today else ""
    label = cfg.get("_heading")
    if zh:
        head = f"📰 {label or ('每日' + industry + '简报')} · {date_str}"
        sub = f"{len(items)} 条更新"
    else:
        head = f"📰 {label or ('Daily ' + industry + ' Brief')} · {date_str}"
        sub = f"{len(items)} updates"

    lines = [head, sub, ""]
    ordered = ([it for it in items if it.weight == "lead"]
               + [it for it in items if it.weight != "lead"])
    for i, it in enumerate(ordered, 1):
        when = _fmt_time(it.published_at, tz)
        meta = it.source_name or it.source_id
        if when:
            meta = f"{meta} · {when}"
        summary = (it.summary or it.body or "").strip()
        lines.append(f"{i}. {it.title}")
        if summary:
            lines.append(summary)
        lines.append(meta)
        lines.append(it.url)
        for a in (it.raw_meta.get("also_seen") or [])[:2]:
            label = "另见" if zh else "also"
            lines.append(f"  ↳ {label}: {a['name']} — {a['url']}")
        lines.append("")
    return "\n".join(lines).strip()
