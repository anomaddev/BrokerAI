from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BROKERAI_",
        env_file="/etc/brokerai/config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "change-me"
    web_port: int = 8080
    log_level: str = "INFO"
    enabled_bots: str = "research,execution,analysis"
    data_dir: Path = Path("/var/lib/brokerai/data")
    log_dir: Path = Path("/var/log/brokerai")

    @property
    def enabled_bot_names(self) -> list[str]:
        return [name.strip() for name in self.enabled_bots.split(",") if name.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
