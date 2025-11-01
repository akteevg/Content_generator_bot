"""Thin client for interacting with the GigaChat API."""

from __future__ import annotations

import base64
import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import requests
import urllib3


logger = logging.getLogger(__name__)


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


@dataclass
class GigaChatConfig:
    client_id: str
    client_secret: str
    scope: str = "GIGACHAT_API_PERS"
    model: str = "GigaChat"
    timeout: float = 60.0
    verify_ssl: bool | str = False  # Значение по умолчанию, если параметр не передан в GigaChatConfig. В продакшене задаётся через GIGACHAT_VERIFY_SSL в .env


class GigaChatError(RuntimeError):
    """Raised when the API returns an error response."""


class GigaChatClient:
    def __init__(self, config: GigaChatConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[dt.datetime] = None

    def _token_is_valid(self) -> bool:
        if not self._access_token or not self._token_expires_at:
            return False
        return dt.datetime.utcnow() < self._token_expires_at - dt.timedelta(seconds=30)

    def _build_basic_auth(self) -> str:
        raw = f"{self._config.client_id}:{self._config.client_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("utf-8")

    def _refresh_token(self) -> None:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": f"Basic {self._build_basic_auth()}",
            "RqUID": str(uuid.uuid4()),
        }
        data = {"scope": self._config.scope}

        response = self._session.post(
            TOKEN_URL,
            headers=headers,
            data=data,
            timeout=self._config.timeout,
            verify=self._config.verify_ssl,
        )
        if response.status_code != 200:
            raise GigaChatError(
                f"Failed to obtain access token: {response.status_code} {response.text}"
            )

        payload = response.json()
        self._access_token = payload.get("access_token")
        if not self._access_token:
            raise GigaChatError("Malformed token response from GigaChat")

        expires_at = payload.get("expires_at")
        expires_in = payload.get("expires_in")

        if isinstance(expires_at, str):
            try:
                parsed = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                self._token_expires_at = (
                    parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
                )
                return
            except ValueError:
                logger.warning("Не удалось разобрать expires_at='%s'", expires_at)

        if isinstance(expires_at, (int, float)):
            value = float(expires_at)
            # Если число похоже на Unix-время (секунды или миллисекунды с 1970 года)
            if value > 1e11:  # вероятно миллисекунды
                value = value / 1000.0
            if value > 1e9:  # секунды с эпохи
                self._token_expires_at = dt.datetime.utcfromtimestamp(value)
            else:  # интервал в секундах
                self._token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=value)
            return

        if expires_in is not None:
            try:
                seconds = float(expires_in)
            except (TypeError, ValueError):
                seconds = 55 * 60
            self._token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=seconds)
            return

        self._token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=55 * 60)

    def _ensure_token(self) -> None:
        if not self._token_is_valid():
            self._refresh_token()

    def generate_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        self._ensure_token()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
        }
        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        response = self._session.post(
            CHAT_URL,
            headers=headers,
            json=body,
            timeout=self._config.timeout,
            verify=self._config.verify_ssl,
        )

        if response.status_code != 200:
            raise GigaChatError(
                f"GigaChat generation failed: {response.status_code} {response.text}"
            )

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise GigaChatError("Unexpected response format from GigaChat") from exc
        return content.strip()

