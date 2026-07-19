from __future__ import annotations

from pathlib import Path

import pytest

from brokerai.bots.researcher.report_store import (
    FilesystemReportStore,
    migrate_local_reports_to_storage,
    reset_report_store,
)


@pytest.fixture(autouse=True)
def _reset_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "")
    from brokerai.config.settings import get_settings

    get_settings.cache_clear()
    reset_report_store()
    yield
    reset_report_store()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_filesystem_store_roundtrip(tmp_path: Path) -> None:
    store = FilesystemReportStore()
    await store.ensure()
    key = "2026_29/2026-07-18-daily.md"
    await store.write_text(key, "# hello\n")
    assert await store.exists(key)
    assert await store.read_text(key) == "# hello\n"
    keys = await store.list_keys()
    assert key in keys
    assert await store.create_signed_url(key) is None
    await store.delete(key)
    assert not await store.exists(key)


@pytest.mark.asyncio
async def test_migrate_noop_without_storage() -> None:
    store = FilesystemReportStore()
    result = await migrate_local_reports_to_storage(store)
    assert result == {"uploaded": 0, "failed": 0, "archived": 0}
