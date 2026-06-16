"""Summarize each item via the Agnes chat API (OpenAI-compatible).

Mirrors the merch-canvas Agnes client: POST {base}/v1/chat/completions,
Bearer auth, model agnes-2.0-flash, IPv4 transport. The key is read from the
environment only. If the key is missing or a call fails, we degrade to a body
excerpt so the brief is still produced.
"""
import concurrent.futures
import logging
import os

import httpx

log = logging.getLogger("dailybrief.summarize")

DEFAULT_PROMPT = (
    "You only remix the fetched text. Never fabricate; stay faithful to the source. "
    "Summarize the item for a busy industry professional's daily brief in 2-3 sentences: "
    "lead with what is new and why it matters, keep key names/numbers/product names, "
    "no preamble, no 'this article discusses'. Do not include the URL."
)


def load_prompt(prompts_dir: str) -> str:
    path = os.path.join(prompts_dir, "summarize.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or DEFAULT_PROMPT
    except OSError:
        return DEFAULT_PROMPT


def _summarize_one(client, item, prompt, model, lang, max_chars, key, base_url) -> str:
    body = (item.body or "")[:max_chars]
    user = (
        f"Title: {item.title}\n"
        f"Source: {item.source_name}\n"
        f"Content:\n{body if body else '(no body text; summarize from the title)'}\n\n"
        f"Write the summary in {lang}."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
        "max_tokens": 400,
        "temperature": 0.3,
    }
    resp = client.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def summarize_items(items, cfg, prompts_dir, max_workers: int = 4):
    key = os.getenv("AGNES_API_KEY")
    base_url = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com")
    s = cfg.get("summarizer", {})
    model = s.get("model", "agnes-2.0-flash")
    lang = s.get("language") or cfg.get("language", "en")
    max_chars = s.get("max_chars", 2000)

    if not key:
        log.warning("AGNES_API_KEY not set — using body excerpts instead of LLM summaries.")
        for it in items:
            it.summary = (it.body or it.title)[:280]
        return items

    prompt = load_prompt(prompts_dir)
    transport = httpx.HTTPTransport(local_address="0.0.0.0")
    with httpx.Client(transport=transport) as client:
        def worker(it):
            try:
                it.summary = _summarize_one(client, it, prompt, model, lang, max_chars, key, base_url)
            except Exception as e:  # never let one item kill the run
                log.warning("summarize failed for %s: %s", it.url, e)
                it.summary = (it.body or it.title)[:280]
            return it

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(worker, items))
    return items
