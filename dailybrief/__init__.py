"""DailyBrief — open-source-list daily industry news digest (Slice-0 MVP).

Slice-0 scope: keyless RSS + YouTube channel-RSS -> exact dedup -> Agnes
summarize -> Telegram. No CDP, no clustering, no translation. All Python
(per design doc section 9.1), so Phase 2 (GitHub Actions) and Phase 3
(FastAPI/Pulse) reuse the SAME adapter + pipeline code.
"""

__version__ = "0.1.0"
