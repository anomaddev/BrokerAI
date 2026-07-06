"""Cost ledger category constants."""

from __future__ import annotations

LLM = "llm"
DATA_API = "data_api"
HOSTING = "hosting"

ALL_CATEGORIES = frozenset({LLM, DATA_API, HOSTING})
