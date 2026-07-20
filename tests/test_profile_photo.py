"""Profile photo validation, URL helpers, and local save/migrate behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from brokerai.auth.profile_photo import (
    LocalProfilePhotoBackend,
    clear_profile_photos,
    detect_image_ext,
    is_remote_photo_url,
    resolve_profile_photo_path,
    resolve_profile_photo_url,
    save_profile_photo,
    save_profile_photo_local,
    storage_object_key_from_public_url,
    validate_profile_photo_bytes,
)


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_detect_image_ext_png() -> None:
    assert detect_image_ext(PNG_1X1) == ".png"


def test_validate_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_profile_photo_bytes(b"")


def test_validate_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="JPEG"):
        validate_profile_photo_bytes(b"not-an-image")


def test_is_remote_photo_url() -> None:
    assert is_remote_photo_url("https://example.com/a.png")
    assert is_remote_photo_url("http://127.0.0.1:8000/storage/v1/object/public/avatars/x.png")
    assert not is_remote_photo_url("profile.png")
    assert not is_remote_photo_url(None)


def test_storage_object_key_from_public_url() -> None:
    url = "http://127.0.0.1:8000/storage/v1/object/public/avatars/profile/u1/abc.png?t=1"
    assert storage_object_key_from_public_url(url) == "profile/u1/abc.png"
    assert storage_object_key_from_public_url("profile.png") is None


def test_save_and_resolve_local(tmp_path: Path) -> None:
    name = save_profile_photo_local(tmp_path, PNG_1X1)
    assert name == "profile.png"
    path = resolve_profile_photo_path(tmp_path, name)
    assert path is not None and path.read_bytes() == PNG_1X1
    assert resolve_profile_photo_url(stored=name, auth_dir=tmp_path) == "/api/auth/profile-photo"
    clear_profile_photos(tmp_path)
    assert resolve_profile_photo_path(tmp_path, name) is None


@pytest.mark.asyncio
async def test_local_backend_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from brokerai.auth import profile_photo as mod

    monkeypatch.setattr(mod, "_backend", LocalProfilePhotoBackend())
    stored = await save_profile_photo(tmp_path, PNG_1X1, profile_id="local:admin")
    assert stored == "profile.png"
    assert (tmp_path / stored).is_file()


def test_resolve_remote_url(tmp_path: Path) -> None:
    url = "https://cdn.example/avatars/profile.png"
    assert resolve_profile_photo_url(stored=url, auth_dir=tmp_path) == url
