"""Delivery: Telegram (default) + stdout (always echoed).

Telegram is sent as plain text (no parse_mode) to dodge MarkdownV2 escaping,
chunked to stay under the 4096-char per-message limit.
"""
import logging
import os

import httpx

log = logging.getLogger("dailybrief.deliver")

TELEGRAM_LIMIT = 4000  # < 4096 hard limit, leaves headroom


def chunk_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    parts: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > limit:
            if cur:
                parts.append(cur)
                cur = ""
            if len(para) > limit:  # a single huge paragraph: hard-split
                for i in range(0, len(para), limit):
                    parts.append(para[i:i + limit])
            else:
                cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


def deliver_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot deliver to Telegram.")
        return False
    transport = httpx.HTTPTransport(local_address="0.0.0.0")
    ok = True
    with httpx.Client(transport=transport, timeout=30) as c:
        for chunk in chunk_text(text):
            r = c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            )
            if r.status_code != 200:
                log.error("Telegram send failed (%s): %s", r.status_code, r.text[:300])
                ok = False
    return ok


def deliver(text: str, cfg: dict, dry_run: bool = False) -> bool:
    """Echo to stdout always; deliver to the configured channel unless dry-run."""
    print("\n" + text + "\n")
    if dry_run:
        log.info("dry-run: skipping channel delivery.")
        return True
    method = cfg.get("delivery", {}).get("method", "stdout")
    if method == "telegram":
        return deliver_telegram(text)
    if method == "stdout":
        return True
    log.warning("unknown delivery method %r — echoed to stdout only.", method)
    return True
