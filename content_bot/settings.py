"""Configuration helpers for environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


class MissingSettingError(RuntimeError):
    """Raised when a required environment variable is missing."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingSettingError(f"Environment variable '{name}' is required")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gigachat_client_id: str
    gigachat_client_secret: str
    telegram_disable_ssl_verify: bool = False


def get_settings() -> Settings:
    """Load application settings from environment variables."""

    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        gigachat_client_id=_require("GIGACHAT_CLIENT_ID"),
        gigachat_client_secret=_require("GIGACHAT_CLIENT_SECRET"),
        telegram_disable_ssl_verify=_get_bool("TELEGRAM_DISABLE_SSL_VERIFY"),
    )


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

