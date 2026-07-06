from functools import lru_cache
from pathlib import Path
from typing import Literal
import re

from pydantic_settings import BaseSettings, SettingsConfigDict

from brokerai.config.env_file import sync_update_env_from_file

UpdateTrack = Literal["branch", "release", "latest-release", "next-major"]
AuthMode = Literal["builtin", "oidc"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEV_ENV = _REPO_ROOT / ".env"
_PROD_ENV = Path("/etc/brokerai/config.env")


def _settings_env_files() -> tuple[str, ...]:
    files: list[str] = []
    if _DEV_ENV.exists():
        files.append(str(_DEV_ENV))
    if _PROD_ENV.exists():
        files.append(str(_PROD_ENV))
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BROKERAI_",
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "change-me"
    auth_mode: AuthMode = "builtin"
    web_port: int = 1989
    log_level: str = "INFO"
    enabled_bots: str = "secretary,broker,researcher"
    auto_update: bool = True
    update_track: UpdateTrack = "branch"
    branch: str = "main"
    release: str = ""
    repo: str = "https://github.com/anomaddev/BrokerAI"
    data_dir: Path = Path("/var/lib/brokerai/data")
    log_dir: Path = Path("/var/log/brokerai")
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "brokerai"
    session_cookie_name: str = "brokerai_session"
    session_max_age: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool | None = None
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_post_logout_redirect_uri: str = ""
    oidc_logout_url: str = ""
    oidc_allowed_sub: str = ""
    oidc_scopes: str = "openid profile email"
    research_search_concurrency: int = 6
    research_analysis_concurrency: int = 4
    ai_confirmation_enabled: bool = False
    candle_sync_chunk_size: int = 5000
    candle_sync_concurrency: int = 4
    candle_default_timeframes: str = "M15"
    pipeline_concurrency: int = 10
    oanda_fetch_concurrency: int = 8
    oanda_max_requests_per_second: int = 90
    oanda_max_new_connections_per_second: int = 2
    oanda_client_max_age_seconds: int = 3600
    oanda_cursor_stale_threshold_seconds: int = 3600
    oanda_exposure_check_interval_seconds: int = 3600
    broker_events_bulk_batch_size: int = 500
    broker_events_retention_enabled: bool = True
    broker_events_low_value_retention_days: int = 90
    analysis_concurrency: int = 10
    secretary_tick_interval_seconds: int = 5
    broker_sync_interval_seconds: int = 30
    trade_sync_interval_seconds: int = 300
    oanda_account_sync_interval_seconds: int = 60
    pipeline_candle_cache_ttl_seconds: int = 60

    @property
    def auth_dir(self) -> Path:
        return self.data_dir / "auth"

    @property
    def enabled_bot_names(self) -> list[str]:
        return [name.strip() for name in self.enabled_bots.split(",") if name.strip()]

    @property
    def update_pin_display(self) -> str:
        if self.update_track == "branch":
            return f"branch:{self.branch}"
        if self.update_track == "release":
            tag = self.release or "unset"
            return f"release:{tag.lstrip('v')}"
        if self.update_track == "next-major":
            ref = self._installed_lock_ref()
            if ref:
                match = re.match(r"^v?(\d+)", ref)
                if match:
                    return f"next-major:{match.group(1)}.x"
            return "next-major"
        return "latest-release"

    def _installed_lock_ref(self) -> str:
        prod = Path("/opt/BrokerAI_version.txt")
        path = prod if prod.exists() else self.data_dir / "version.lock"
        if not path.exists():
            return ""
        raw = path.read_text().strip()
        if not raw or "=" not in raw:
            return ""
        for line in raw.splitlines():
            if line.startswith("ref="):
                return line.split("=", 1)[1].strip()
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    sync_update_env_from_file()
    get_settings.cache_clear()
    return get_settings()


def validate_startup_settings(settings: Settings | None = None) -> None:
    """Refuse startup in production when critical settings are unsafe."""
    settings = settings or get_settings()
    if settings.secret_key == "change-me" and _PROD_ENV.exists():
        raise RuntimeError(
            "BROKERAI_SECRET_KEY must be set to a secure value in production "
            "(/etc/brokerai/config.env)"
        )
    if settings.auth_mode == "oidc":
        missing = [
            name
            for name, value in (
                ("BROKERAI_OIDC_ISSUER", settings.oidc_issuer),
                ("BROKERAI_OIDC_CLIENT_ID", settings.oidc_client_id),
                ("BROKERAI_OIDC_CLIENT_SECRET", settings.oidc_client_secret),
            )
            if not str(value).strip()
        ]
        if missing:
            raise RuntimeError(
                "OIDC auth mode requires: " + ", ".join(missing)
            )
