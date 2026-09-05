from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import ProviderConfig, Settings


@dataclass
class ProviderAttempt:
    provider: str
    model: str
    latency_ms: int
    response: dict[str, Any]


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig, settings: Settings):
        self.config = config
        self.settings = settings

    async def chat(self, payload: dict[str, Any], model: str) -> ProviderAttempt:
        body = {k: v for k, v in payload.items() if v is not None and k not in {"provider", "free_only"}}
        body["model"] = model
        body["stream"] = False
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "arjuna-ai/0.2",
        }
        if self.config.name == "openrouter":
            headers["HTTP-Referer"] = self.settings.public_origin
            headers["X-Title"] = self.settings.app_name
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(f"{self.config.base_url}/chat/completions", headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(self.config.name, f"Network error: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(self.config.name, response.text[:1000], response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(self.config.name, "Provider returned invalid JSON") from exc
        return ProviderAttempt(provider=self.config.name, model=model, latency_ms=latency_ms, response=data)
