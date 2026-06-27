from __future__ import annotations

from pathlib import Path

PROFILE_PHOTO_PREFIX = "profile"
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024


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


def clear_profile_photos(auth_dir: Path) -> None:
    for path in auth_dir.glob(f"{PROFILE_PHOTO_PREFIX}.*"):
        if path.is_file():
            path.unlink()


def save_profile_photo(auth_dir: Path, data: bytes) -> str:
    if not data:
        raise ValueError("Profile photo is empty")
    if len(data) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("Profile photo must be 5 MB or smaller")
    ext = detect_image_ext(data)
    if not ext:
        raise ValueError("Profile photo must be JPEG, PNG, WebP, or GIF")
    auth_dir.mkdir(parents=True, exist_ok=True)
    clear_profile_photos(auth_dir)
    filename = f"{PROFILE_PHOTO_PREFIX}{ext}"
    (auth_dir / filename).write_bytes(data)
    return filename


def resolve_profile_photo_path(auth_dir: Path, filename: str | None) -> Path | None:
    if not filename:
        return None
    path = auth_dir / filename
    if (
        path.is_file()
        and path.name.startswith(PROFILE_PHOTO_PREFIX)
        and path.parent.resolve() == auth_dir.resolve()
    ):
        return path
    return None
