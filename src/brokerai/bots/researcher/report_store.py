"""Report body storage: Supabase Storage when configured, else local filesystem."""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from brokerai.auth.supabase_auth import supabase_configured
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

RESEARCH_REPORTS_BUCKET = "research-reports"
SIGNED_URL_EXPIRES_IN = 3600


class ReportStore(Protocol):
    async def ensure(self) -> None: ...

    async def list_keys(self) -> list[str]: ...

    async def read_text(self, key: str) -> str: ...

    async def write_text(self, key: str, content: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def create_signed_url(
        self, key: str, *, expires_in: int = SIGNED_URL_EXPIRES_IN
    ) -> str | None: ...

    @property
    def uses_storage(self) -> bool: ...


def local_reports_dir() -> Path:
    path = get_settings().data_dir / "research" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrated_reports_root() -> Path:
    path = get_settings().data_dir / "research" / "reports.migrated"
    path.mkdir(parents=True, exist_ok=True)
    return path


class FilesystemReportStore:
    """Local disk store used for tests and when Supabase is not configured."""

    @property
    def uses_storage(self) -> bool:
        return False

    async def ensure(self) -> None:
        local_reports_dir()

    async def list_keys(self) -> list[str]:
        return await asyncio.to_thread(self._list_keys_sync)

    def _list_keys_sync(self) -> list[str]:
        root = local_reports_dir()
        keys: list[str] = []
        for path in root.rglob("*.md"):
            if path.is_file():
                keys.append(str(path.relative_to(root)))
        return sorted(keys, reverse=True)

    async def read_text(self, key: str) -> str:
        path = self._resolve(key)
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    async def write_text(self, key: str, content: str) -> None:
        path = self._resolve(key, must_exist=False)
        await asyncio.to_thread(self._write_sync, path, content)

    def _write_sync(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def exists(self, key: str) -> bool:
        try:
            path = self._resolve(key)
        except FileNotFoundError:
            return False
        return await asyncio.to_thread(path.is_file)

    async def create_signed_url(
        self, key: str, *, expires_in: int = SIGNED_URL_EXPIRES_IN
    ) -> str | None:
        return None

    def _resolve(self, key: str, *, must_exist: bool = True) -> Path:
        root = local_reports_dir().resolve()
        candidate = (root / key.lstrip("/")).resolve()
        if not candidate.is_relative_to(root):
            raise FileNotFoundError(f"Report not found: {key}")
        if must_exist and not candidate.is_file():
            raise FileNotFoundError(f"Report not found: {key}")
        return candidate


class SupabaseStorageReportStore:
    """Private ``research-reports`` bucket via supabase-py (service_role)."""

    def __init__(self) -> None:
        self._client = None
        self._ensured = False

    @property
    def uses_storage(self) -> bool:
        return True

    def _get_client(self):
        if self._client is None:
            from supabase import create_client

            settings = get_settings()
            self._client = create_client(
                settings.supabase_url.rstrip("/"),
                settings.supabase_service_role_key,
            )
        return self._client

    async def ensure(self) -> None:
        if self._ensured:
            return
        await asyncio.to_thread(self._ensure_sync)
        self._ensured = True

    def _ensure_sync(self) -> None:
        client = self._get_client()
        try:
            buckets = client.storage.list_buckets()
            names = {getattr(b, "name", None) or getattr(b, "id", None) for b in buckets}
            if RESEARCH_REPORTS_BUCKET not in names:
                client.storage.create_bucket(
                    RESEARCH_REPORTS_BUCKET,
                    options={
                        "public": False,
                        "allowed_mime_types": ["text/markdown", "text/plain"],
                        "file_size_limit": 5 * 1024 * 1024,
                    },
                )
                logger.info("Created Storage bucket %s", RESEARCH_REPORTS_BUCKET)
        except Exception:
            logger.warning("Failed to ensure Storage bucket %s", RESEARCH_REPORTS_BUCKET, exc_info=True)
            raise

    async def list_keys(self) -> list[str]:
        await self.ensure()
        return await asyncio.to_thread(self._list_keys_sync)

    def _list_keys_sync(self) -> list[str]:
        client = self._get_client()
        bucket = client.storage.from_(RESEARCH_REPORTS_BUCKET)
        keys: list[str] = []

        def walk(prefix: str) -> None:
            items = bucket.list(prefix or "", {"limit": 1000})
            for item in items or []:
                name = item.get("name") if isinstance(item, dict) else None
                if not name:
                    continue
                full = f"{prefix}/{name}" if prefix else name
                # Folders often have id None / empty metadata; files have metadata/size.
                meta = item.get("metadata") if isinstance(item, dict) else None
                if meta is None and not name.endswith(".md"):
                    walk(full)
                elif name.endswith(".md"):
                    keys.append(full)

        walk("")
        return sorted(keys, reverse=True)

    async def read_text(self, key: str) -> str:
        await self.ensure()
        data = await asyncio.to_thread(self._download_sync, key)
        return data.decode("utf-8")

    def _download_sync(self, key: str) -> bytes:
        client = self._get_client()
        try:
            return client.storage.from_(RESEARCH_REPORTS_BUCKET).download(key)
        except Exception as exc:
            raise FileNotFoundError(f"Report not found: {key}") from exc

    async def write_text(self, key: str, content: str) -> None:
        await self.ensure()
        await asyncio.to_thread(self._upload_sync, key, content)

    def _upload_sync(self, key: str, content: str) -> None:
        client = self._get_client()
        raw = content.encode("utf-8")
        bucket = client.storage.from_(RESEARCH_REPORTS_BUCKET)
        options = {"content-type": "text/markdown", "upsert": "true"}
        try:
            bucket.upload(key, raw, file_options=options)
        except Exception:
            # Some clients use update for existing objects.
            bucket.update(key, raw, file_options=options)

    async def delete(self, key: str) -> None:
        await self.ensure()
        await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        client = self._get_client()
        client.storage.from_(RESEARCH_REPORTS_BUCKET).remove([key])

    async def exists(self, key: str) -> bool:
        await self.ensure()
        try:
            await self.read_text(key)
            return True
        except FileNotFoundError:
            return False

    async def create_signed_url(
        self, key: str, *, expires_in: int = SIGNED_URL_EXPIRES_IN
    ) -> str | None:
        await self.ensure()
        return await asyncio.to_thread(self._signed_url_sync, key, expires_in)

    def _signed_url_sync(self, key: str, expires_in: int) -> str | None:
        client = self._get_client()
        result = client.storage.from_(RESEARCH_REPORTS_BUCKET).create_signed_url(
            key, expires_in
        )
        if isinstance(result, dict):
            return result.get("signedURL") or result.get("signedUrl")
        return getattr(result, "signed_url", None) or getattr(result, "signedURL", None)


_store: ReportStore | None = None


def get_report_store() -> ReportStore:
    global _store
    if _store is None:
        if supabase_configured():
            _store = SupabaseStorageReportStore()
        else:
            _store = FilesystemReportStore()
    return _store


def reset_report_store() -> None:
    """Test helper to clear the cached store singleton."""
    global _store
    _store = None


async def migrate_local_reports_to_storage(store: ReportStore | None = None) -> dict[str, int]:
    """Upload local ``data/research/reports`` into Storage and archive the live tree.

    Successfully uploaded files are moved under ``reports.migrated/<utc-stamp>/``.
    Failed uploads remain in the live directory.
    """
    store = store or get_report_store()
    if not store.uses_storage:
        return {"uploaded": 0, "failed": 0, "archived": 0}

    await store.ensure()
    root = local_reports_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = migrated_reports_root() / stamp
    uploaded = 0
    failed = 0
    archived = 0

    local_files = [p for p in root.rglob("*.md") if p.is_file()]
    for path in local_files:
        key = str(path.relative_to(root))
        try:
            content = path.read_text(encoding="utf-8")
            await store.write_text(key, content)
            if not await store.exists(key):
                raise RuntimeError(f"verify failed for {key}")
            dest = archive / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            uploaded += 1
            archived += 1
        except Exception:
            failed += 1
            logger.warning("Failed to migrate report %s", key, exc_info=True)

    # Remove empty directories left behind under the live reports root.
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
            except OSError:
                pass

    logger.info(
        "Research reports migrate complete uploaded=%s failed=%s archived=%s",
        uploaded,
        failed,
        archived,
    )
    return {"uploaded": uploaded, "failed": failed, "archived": archived}
