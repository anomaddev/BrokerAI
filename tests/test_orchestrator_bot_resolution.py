from __future__ import annotations

from brokerai.config.settings import Settings
from brokerai.core.orchestrator import Orchestrator


def test_resolved_bot_names_auto_injects_secretary_pipeline_bots():
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.settings = Settings(
        enabled_bots="researcher",
        use_secretary_pipeline=True,
    )

    names = orchestrator._resolved_bot_names(use_secretary=True)

    assert names == ["researcher", "secretary", "broker"]


def test_resolved_bot_names_legacy_mode_unchanged():
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.settings = Settings(
        enabled_bots="data_manager,data_analyzer,researcher",
        use_secretary_pipeline=False,
    )

    names = orchestrator._resolved_bot_names(use_secretary=False)

    assert names == ["data_manager", "data_analyzer", "researcher"]
