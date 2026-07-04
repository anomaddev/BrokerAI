from __future__ import annotations

from brokerai.config.settings import Settings
from brokerai.core.orchestrator import Orchestrator


def test_resolved_bot_names_auto_injects_secretary_pipeline_bots():
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.settings = Settings(enabled_bots="researcher")

    names = orchestrator._resolved_bot_names()

    assert names == ["researcher", "secretary", "broker"]


def test_resolved_bot_names_preserves_explicit_order():
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.settings = Settings(enabled_bots="secretary,broker,researcher")

    names = orchestrator._resolved_bot_names()

    assert names == ["secretary", "broker", "researcher"]
