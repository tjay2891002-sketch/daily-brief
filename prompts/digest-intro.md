# Digest framing (reserved for Slice-1+)

Slice-0 assembles the brief deterministically in render.py (no LLM framing), so
this file is not yet wired in. It documents the intended overall tone for when
an LLM assembles the digest intro in a later slice:

- Open with one sentence naming the single most important thing today.
- Group by theme when there are clear clusters; otherwise newest-first.
- Keep it skimmable: every item is a headline + 2–3 sentence summary + source link.
- Never invent a "theme of the day" that the items don't support.
