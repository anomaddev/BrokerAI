from functools import lru_cache
from pathlib import Path
from typing import Literal
import re

from pydantic_settings import BaseSettings, SettingsConfigDict

from brokerai.config.env_file import sync_update_env_from_file

UpdateTrack = Literal["branch", "release", "latest-release", "next-major"]

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
    web_port: int = 1989
    log_level: str = "INFO"
    enabled_bots: str = "brokers,researcher,data_manager,data_analyzer,executor"
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
