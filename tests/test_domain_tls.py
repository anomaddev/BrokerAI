"""Tests for public domain / TLS settings helpers and API."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from brokerai.web.app import app
from brokerai.web.domain_tls import apply_domain_tls, read_domain_settings, valid_hostname


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("broker.example.com", True),
        ("supabase.justinackermann.com", True),
        ("localhost", False),
        ("", False),
        ("-bad.example.com", False),
        ("broker", False),
    ],
)
def test_valid_hostname(value: str, ok: bool) -> None:
    assert valid_hostname(value) is ok


def test_read_domain_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "BROKERAI_DOMAIN=broker.example.com\n"
        "BROKERAI_SUPABASE_DOMAIN=supabase.example.com\n"
        "BROKERAI_SUPABASE_URL=https://supabase.example.com\n"
    )
    monkeypatch.setattr("brokerai.web.domain_tls.config_file_path", lambda: env)
    monkeypatch.setattr("brokerai.config.env_file.config_file_path", lambda: env)

    assert read_domain_settings() == {
        "domain": "broker.example.com",
        "supabase_domain": "supabase.example.com",
        "supabase_url": "https://supabase.example.com",
    }


@pytest.mark.asyncio
async def test_apply_domain_tls_dev_writes_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("BROKERAI_SECRET_KEY=test\n")
    monkeypatch.setattr("brokerai.web.domain_tls.config_file_path", lambda: env)
    monkeypatch.setattr("brokerai.config.env_file.config_file_path", lambda: env)
    monkeypatch.setattr("brokerai.web.domain_tls.config_file_writable", lambda: True)
    monkeypatch.setattr("brokerai.config.env_file.config_file_writable", lambda: True)
    monkeypatch.setattr("brokerai.web.domain_tls.is_dev_install", lambda _s=None: True)

    ok, message = await apply_domain_tls(
        domain="broker.example.com",
        supabase_domain="supabase.example.com",
    )
    assert ok is True
    text = env.read_text()
    assert "BROKERAI_DOMAIN=broker.example.com" in text
    assert "BROKERAI_SUPABASE_DOMAIN=supabase.example.com" in text
    assert "BROKERAI_SUPABASE_URL=https://supabase.example.com" in text
    assert "Caddy" in message or "dev" in message.lower() or "Saved" in message


@pytest.mark.asyncio
async def test_domain_settings_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("BROKERAI_DOMAIN=old.example.com\n")
    monkeypatch.setattr("brokerai.web.domain_tls.config_file_path", lambda: env)
    monkeypatch.setattr("brokerai.config.env_file.config_file_path", lambda: env)
    monkeypatch.setattr("brokerai.web.domain_tls.config_file_writable", lambda: True)
    monkeypatch.setattr("brokerai.config.env_file.config_file_writable", lambda: True)
    monkeypatch.setattr("brokerai.web.domain_tls.is_dev_install", lambda _s=None: True)
    monkeypatch.setattr("brokerai.web.routes.settings.is_dev_install", lambda _s=None: True)

    async def _noop_backup(**_kwargs):
        return None

    monkeypatch.setattr("brokerai.web.routes.settings.auto_backup_before", _noop_backup)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Auth: use test dependency override if present; otherwise skip via cookie setup.
        from brokerai.web.routes import auth as auth_routes

        app.dependency_overrides[auth_routes.require_auth] = lambda: "admin"
        try:
            get_res = await client.get("/api/settings/domain")
            assert get_res.status_code == 200
            assert get_res.json()["domain"] == "old.example.com"

            apply_res = await client.post(
                "/api/settings/domain/apply",
                json={
                    "domain": "broker.example.com",
                    "supabase_domain": "supabase.example.com",
                },
            )
            assert apply_res.status_code == 200, apply_res.text
            body = apply_res.json()
            assert body["domain"] == "broker.example.com"
            assert body["supabase_domain"] == "supabase.example.com"
            assert body["status"] == "applied"
        finally:
            app.dependency_overrides.pop(auth_routes.require_auth, None)
