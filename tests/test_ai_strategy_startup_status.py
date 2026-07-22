"""Human-readable AI Strategy startup progress helpers."""

from __future__ import annotations

from brokerai.ai_strategy.startup_status import (
    build_startup_event_detail,
    build_startup_event_title,
    build_startup_status_message,
    human_report_label,
)


def test_human_report_labels():
    assert human_report_label("weekly_brief") == "weekly brief"
    assert human_report_label("daily_report") == "daily report"


def test_waiting_on_reports_title_and_message():
    job = {
        "status": "running",
        "phase": "ensuring_reports",
        "pending_reports": ["weekly_brief", "weekly_debrief"],
        "required_reports": ["daily_report", "weekly_brief", "weekly_debrief"],
        "skipped_reports": [],
        "status_message": "Waiting for weekly brief, weekly debrief to finish",
    }
    assert build_startup_event_title(job) == "Startup · waiting on weekly brief"
    assert "Waiting for weekly brief" in build_startup_status_message(job)
    detail = build_startup_event_detail(job)
    assert "Waiting for weekly brief" in detail
    assert "Ready:" not in detail


def test_seeding_and_loop_titles():
    seed = {
        "status": "running",
        "phase": "seeding_digest",
        "last_seed_wait": "budget_exceeded: in_flight",
    }
    assert build_startup_event_title(seed) == "Startup · seeding (waiting on LLM)"
    assert "in_flight" in build_startup_status_message(seed)

    looping = {
        "status": "running",
        "phase": "looping",
        "loop_index": 1,
        "loop_target": 3,
        "current_backtest_run_id": "run-1",
    }
    assert build_startup_event_title(looping) == "Startup · trade 2/3"
    assert "trade loop" in build_startup_status_message(looping).lower()

    explore = {
        "status": "running",
        "phase": "looping",
        "loop_index": 0,
        "loop_target": 3,
        "current_backtest_run_id": "run-0",
    }
    assert build_startup_event_title(explore) == "Startup · explore 1/3"
    assert "explore loop" in build_startup_status_message(explore).lower()


def test_terminal_titles():
    assert build_startup_event_title({"status": "failed", "error": "boom"}) == "Startup failed"
    assert build_startup_status_message({"status": "failed", "error": "boom"}) == "boom"
    assert build_startup_event_title({"status": "completed"}) == "Startup completed"
