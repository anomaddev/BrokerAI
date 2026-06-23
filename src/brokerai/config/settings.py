from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

UpdateTrack = Literal["branch", "release", "latest-release"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BROKERAI_",
        env_file=(".env", "/etc/brokerai/config.env"),
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
        return "latest-release"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
