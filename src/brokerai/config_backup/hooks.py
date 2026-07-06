from __future__ import annotations

from brokerai.config_backup.service import ConfigBackupService


async def auto_backup_before(
    *,
    trigger: str,
    summary: str,
    change_label: str | None = None,
) -> None:
    """Capture current configuration before a settings mutation."""
    await ConfigBackupService().auto_backup_before(
        trigger=trigger,
        summary=summary,
        change_label=change_label,
    )
