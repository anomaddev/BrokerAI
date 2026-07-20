"""user_profiles.profile_photo_url column sync with AuthStore docs."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from brokerai.auth.pg_profile import load_user_profile, reset_pg_profile_engine, save_user_profile
from brokerai.db.pg.models import UserProfileRow


@pytest.mark.asyncio
async def test_save_user_profile_sets_photo_url_column(sqlite_db):
    reset_pg_profile_engine()

    url = "https://example.supabase.co/storage/v1/object/public/avatars/profile/u1/a.png"
    save_user_profile(
        profile_id="user-1",
        username="admin",
        setup_complete=True,
        doc={
            "username": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "profile_photo": url,
            "market_indicators": {},
        },
    )

    loaded = load_user_profile()
    assert loaded is not None
    assert loaded["profile_photo"] == url

    from brokerai.auth.pg_profile import _get_factory

    factory = _get_factory()
    with factory() as session:
        row = session.scalar(select(UserProfileRow).limit(1))
        assert row is not None
        assert row.profile_photo_url == url

    # Local filename clears the URL column.
    save_user_profile(
        profile_id="user-1",
        username="admin",
        setup_complete=True,
        doc={
            "username": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "profile_photo": "profile.png",
            "market_indicators": {},
        },
    )
    with factory() as session:
        row = session.scalar(select(UserProfileRow).limit(1))
        assert row is not None
        assert row.profile_photo_url is None
