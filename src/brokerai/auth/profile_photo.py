"""Profile photo storage: Supabase Storage when configured, else local filesystem.

When Supabase is configured, images are uploaded to a public ``avatars`` bucket and
the public download URL is persisted on ``brokerai.user_profiles.profile_photo_url``
(and mirrored in the profile JSON ``profile_photo`` field for AuthStore).

Without Supabase, photos remain under ``auth_dir`` as ``profile.<ext>`` and the
filename is stored in the profile document (served via ``/api/auth/profile-photo``).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from brokerai.auth.supabase_auth import supabase_configured
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

PROFILE_PHOTO_PREFIX = "profile"
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
AVATARS_BUCKET = "avatars"

_EXT_TO_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def detect_image_ext(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def content_type_for_ext(ext: str) -> str:
    return _EXT_TO_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def validate_profile_photo_bytes(data: bytes) -> str:
    """Validate image bytes and return the file extension (including leading dot).

    Raises:
        ValueError: empty, too large, or unsupported format.
    """
    if not data:
        raise ValueError("Profile photo is empty")
    if len(data) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("Profile photo must be 5 MB or smaller")
    ext = detect_image_ext(data)
    if not ext:
        raise ValueError("Profile photo must be JPEG, PNG, WebP, or GIF")
    return ext


def is_remote_photo_url(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def clear_profile_photos(auth_dir: Path) -> None:
    for path in auth_dir.glob(f"{PROFILE_PHOTO_PREFIX}.*"):
        if path.is_file():
            path.unlink()


def save_profile_photo_local(auth_dir: Path, data: bytes) -> str:
    """Write ``profile.<ext>`` under ``auth_dir`` and return the filename."""
    ext = validate_profile_photo_bytes(data)
    auth_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_photos(auth_dir)
    filename = f"{PROFILE_PHOTO_PREFIX}{ext}"
    (auth_dir / filename).write_bytes(data)
    return filename


def resolve_profile_photo_path(auth_dir: Path, filename: str | None) -> Path | None:
    if not filename or is_remote_photo_url(filename):
        return None
    path = auth_dir / filename
    if (
        path.is_file()
        and path.name.startswith(PROFILE_PHOTO_PREFIX)
        and path.parent.resolve() == auth_dir.resolve()
    ):
        return path
    return None


def storage_object_key_from_public_url(url: str | None) -> str | None:
    """Extract the object key from a Supabase public Storage URL, if recognized."""
    if not url:
        return None
    marker = f"/storage/v1/object/public/{AVATARS_BUCKET}/"
    idx = url.find(marker)
    if idx < 0:
        return None
    key = url[idx + len(marker) :].split("?", 1)[0].strip("/")
    return key or None


class ProfilePhotoBackend(Protocol):
    @property
    def uses_storage(self) -> bool: ...

    async def ensure(self) -> None: ...

    async def upload(self, *, profile_id: str, data: bytes, auth_dir: Path) -> str:
        """Persist photo and return the value to store on the profile (URL or filename)."""

    async def delete(self, *, stored: str | None, auth_dir: Path) -> None: ...


class LocalProfilePhotoBackend:
    @property
    def uses_storage(self) -> bool:
        return False

    async def ensure(self) -> None:
        return None

    async def upload(self, *, profile_id: str, data: bytes, auth_dir: Path) -> str:
        return await asyncio.to_thread(save_profile_photo_local, auth_dir, data)

    async def delete(self, *, stored: str | None, auth_dir: Path) -> None:
        await asyncio.to_thread(clear_profile_photos, auth_dir)


class SupabaseProfilePhotoBackend:
    """Public ``avatars`` bucket via supabase-py (service_role)."""

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
            if AVATARS_BUCKET not in names:
                client.storage.create_bucket(
                    AVATARS_BUCKET,
                    options={
                        "public": True,
                        "allowed_mime_types": list(_EXT_TO_CONTENT_TYPE.values()),
                        "file_size_limit": MAX_PROFILE_PHOTO_BYTES,
                    },
                )
                logger.info("Created Storage bucket %s", AVATARS_BUCKET)
        except Exception:
            logger.warning("Failed to ensure Storage bucket %s", AVATARS_BUCKET, exc_info=True)
            raise

    async def upload(self, *, profile_id: str, data: bytes, auth_dir: Path) -> str:
        await self.ensure()
        return await asyncio.to_thread(self._upload_sync, profile_id, data)

    def _upload_sync(self, profile_id: str, data: bytes) -> str:
        ext = validate_profile_photo_bytes(data)
        # New object key per upload avoids CDN stale content after replace.
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in profile_id) or "local"
        key = f"profile/{safe_id}/{uuid4().hex}{ext}"
        client = self._get_client()
        bucket = client.storage.from_(AVATARS_BUCKET)
        options = {
            "content-type": content_type_for_ext(ext),
            "upsert": "true",
            "cache-control": "3600",
        }
        try:
            bucket.upload(key, data, file_options=options)
        except Exception:
            bucket.update(key, data, file_options=options)
        public_url = bucket.get_public_url(key)
        if isinstance(public_url, dict):
            url = public_url.get("publicUrl") or public_url.get("publicURL") or ""
        else:
            url = str(public_url or "")
        # Some SDK versions append a trailing ``?``; normalize for storage.
        url = url.rstrip("?")
        if not url.startswith("http"):
            base = get_settings().supabase_url.rstrip("/")
            url = f"{base}/storage/v1/object/public/{AVATARS_BUCKET}/{key}"
        return url

    async def delete(self, *, stored: str | None, auth_dir: Path) -> None:
        await self.ensure()
        await asyncio.to_thread(self._delete_sync, stored)
        # Also clear any leftover local files from a pre-migration install.
        await asyncio.to_thread(clear_profile_photos, auth_dir)

    def _delete_sync(self, stored: str | None) -> None:
        self.remove_object_sync(stored)

    def remove_object_sync(self, stored: str | None) -> None:
        key = storage_object_key_from_public_url(stored)
        if not key:
            return
        try:
            self._get_client().storage.from_(AVATARS_BUCKET).remove([key])
        except Exception:
            logger.warning("Failed to remove avatar object %s", key, exc_info=True)


_backend: ProfilePhotoBackend | None = None


def get_profile_photo_backend() -> ProfilePhotoBackend:
    global _backend
    if _backend is None:
        if supabase_configured():
            _backend = SupabaseProfilePhotoBackend()
        else:
            _backend = LocalProfilePhotoBackend()
    return _backend


def reset_profile_photo_backend() -> None:
    """Test helper to clear the cached backend singleton."""
    global _backend
    _backend = None


async def save_profile_photo(
    auth_dir: Path,
    data: bytes,
    *,
    profile_id: str,
    previous: str | None = None,
) -> str:
    """Store a profile photo and return the profile value (public URL or local filename).

    When replacing a Supabase object, the previous object is removed after a successful
    upload so a failed upload never leaves the profile without an image.
    """
    backend = get_profile_photo_backend()
    stored = await backend.upload(profile_id=profile_id, data=data, auth_dir=auth_dir)
    if backend.uses_storage:
        if (
            previous
            and is_remote_photo_url(previous)
            and previous != stored
            and isinstance(backend, SupabaseProfilePhotoBackend)
        ):
            await asyncio.to_thread(backend.remove_object_sync, previous)
        # Drop any leftover local files after a successful remote upload.
        await asyncio.to_thread(clear_profile_photos, auth_dir)
    return stored


async def delete_profile_photo(
    auth_dir: Path,
    *,
    stored: str | None,
) -> None:
    backend = get_profile_photo_backend()
    await backend.delete(stored=stored, auth_dir=auth_dir)


def resolve_profile_photo_url(
    *,
    stored: str | None,
    auth_dir: Path,
) -> str | None:
    """Return a browser-usable photo URL, or ``None`` when no photo is available."""
    if not stored:
        return None
    if is_remote_photo_url(stored):
        return stored
    if resolve_profile_photo_path(auth_dir, stored) is not None:
        return "/api/auth/profile-photo"
    return None


def migrated_photos_root() -> Path:
    path = get_settings().data_dir / "auth" / "profile-photos.migrated"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def migrate_local_profile_photo_to_storage(
    *,
    auth_dir: Path | None = None,
) -> dict[str, int]:
    """Upload a local ``profile.*`` file into Storage and persist the public URL.

    Successfully migrated files are moved under ``auth/profile-photos.migrated/<stamp>/``.
    No-ops when Supabase is not configured or the profile already stores a remote URL.
    """
    backend = get_profile_photo_backend()
    if not backend.uses_storage:
        return {"uploaded": 0, "failed": 0, "archived": 0}

    from brokerai.auth.store import AuthStore

    store = AuthStore()
    user = store.get_user()
    if user is None:
        return {"uploaded": 0, "failed": 0, "archived": 0}
    if is_remote_photo_url(user.profile_photo):
        return {"uploaded": 0, "failed": 0, "archived": 0}

    root = auth_dir or store.auth_dir
    local_path = resolve_profile_photo_path(root, user.profile_photo)
    if local_path is None:
        # Filename missing from profile but a local file may still exist.
        candidates = sorted(root.glob(f"{PROFILE_PHOTO_PREFIX}.*"))
        local_path = candidates[0] if candidates else None
    if local_path is None or not local_path.is_file():
        return {"uploaded": 0, "failed": 0, "archived": 0}

    await backend.ensure()
    uploaded = 0
    failed = 0
    archived = 0
    try:
        data = local_path.read_bytes()
        profile_id = user.oidc_sub or f"local:{user.username}"
        url = await backend.upload(profile_id=profile_id, data=data, auth_dir=root)
        store.set_profile_photo(url)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = migrated_photos_root() / stamp / local_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(local_path), str(dest))
        uploaded = 1
        archived = 1
        logger.info("Migrated local profile photo to Storage url=%s", url)
    except Exception:
        failed = 1
        logger.warning("Failed to migrate local profile photo", exc_info=True)

    return {"uploaded": uploaded, "failed": failed, "archived": archived}


# Back-compat aliases used by older imports/tests.
def save_profile_photo_sync(auth_dir: Path, data: bytes) -> str:
    """Synchronous local-only save (tests / callers without an event loop)."""
    return save_profile_photo_local(auth_dir, data)
