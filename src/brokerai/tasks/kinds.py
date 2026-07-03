from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ResearchKind = Literal[
    "research_daily",
    "research_daily_rerun",
    "research_weekly_brief",
    "research_weekly_debrief",
]

TaskKind = Literal[
    ResearchKind,
    "data_fetch",
    "trade_execute",
    "trade_sync",
    "broker_sync",
]

TaskStatus = Literal["running", "success", "failed", "skipped", "cancelled"]

RESEARCH_KINDS: frozenset[str] = frozenset(
    {
        "research_daily",
        "research_weekly_brief",
        "research_weekly_debrief",
        "research_daily_rerun",
    }
)


@dataclass(frozen=True)
class TaskKindSpec:
    label: str
    cancellable: bool
    exclusive_kinds: frozenset[str]


TASK_KINDS: dict[str, TaskKindSpec] = {
    "research_daily": TaskKindSpec(
        label="Daily research report",
        cancellable=True,
        exclusive_kinds=RESEARCH_KINDS,
    ),
    "research_daily_rerun": TaskKindSpec(
        label="Daily research report",
        cancellable=True,
        exclusive_kinds=RESEARCH_KINDS,
    ),
    "research_weekly_brief": TaskKindSpec(
        label="Weekly research brief",
        cancellable=True,
        exclusive_kinds=RESEARCH_KINDS,
    ),
    "research_weekly_debrief": TaskKindSpec(
        label="Weekly research debrief",
        cancellable=True,
        exclusive_kinds=RESEARCH_KINDS,
    ),
    "data_fetch": TaskKindSpec(
        label="Fetch market data",
        cancellable=True,
        exclusive_kinds=frozenset({"data_fetch"}),
    ),
    "trade_execute": TaskKindSpec(
        label="Execute trade",
        cancellable=True,
        exclusive_kinds=frozenset({"trade_execute"}),
    ),
    "trade_sync": TaskKindSpec(
        label="Sync broker state",
        cancellable=True,
        exclusive_kinds=frozenset({"trade_sync", "broker_sync"}),
    ),
    "broker_sync": TaskKindSpec(
        label="Sync broker state",
        cancellable=True,
        exclusive_kinds=frozenset({"trade_sync", "broker_sync"}),
    ),
}


def task_kind_spec(kind: str) -> TaskKindSpec | None:
    return TASK_KINDS.get(kind)
