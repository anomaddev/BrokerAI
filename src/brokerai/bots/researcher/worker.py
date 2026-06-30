from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ResearchMode(str, Enum):
    REPORT = "report"
    TRADE_ANALYSIS = "trade_analysis"  # TODO(loop): implement trade_analysis mode


@dataclass(frozen=True)
class ResearchRequest:
    mode: ResearchMode = ResearchMode.REPORT
    asset_class: str | None = None
    symbols: tuple[str, ...] = ()
    scheduled_kind: str | None = None  # daily, weekly_brief, weekly_debrief
