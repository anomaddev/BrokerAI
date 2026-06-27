from __future__ import annotations

# API-level reasoning depth for daily report LLM calls (Grok, OpenAI-compatible).
DAILY_REPORT_REASONING_EFFORT = "high"

REASONING_EFFORT_OPTIONS = frozenset({"none", "low", "medium", "high"})
