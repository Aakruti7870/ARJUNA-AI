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


class BaseProvider:
    def __init__(self, config: ProviderConfig, settings: Settings):
        self.config = config
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "arjuna-ai/0.4",
        }

    def _error(self, response: httpx.Response) -> ProviderError:
        # Provider bodies are deliberately not propagated: they can contain request data.
        return ProviderError(self.config.name, "Provider request failed", response.status_code)


class OpenAICompatibleProvider(BaseProvider):
    async def chat(self, payload: dict[str, Any], model: str) -> ProviderAttempt:
        body = {"model": model, "messages": payload["messages"], "stream": False}
        for field in ("temperature", "max_tokens"):
            if payload.get(field) is not None:
                body[field] = payload[field]

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self.config.base_url}/chat/completions", headers=self.headers, json=body
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.config.name, "Provider network error") from exc
        if response.status_code >= 400:
            raise self._error(response)
        return ProviderAttempt(
            self.config.name,
            model,
            int((time.perf_counter() - started) * 1000),
            response.json(),
        )


class OpenAIProvider(BaseProvider):
    """Native OpenAI Responses API adapter; never uses Chat Completions."""

    async def models(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.get(f"{self.config.base_url}/models", headers=self.headers)
        except httpx.HTTPError as exc:
            raise ProviderError("openai", "OpenAI network error") from exc
        if response.status_code >= 400:
            raise self._error(response)
        data = response.json().get("data", [])
        return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]

    async def chat(self, payload: dict[str, Any], model: str) -> ProviderAttempt:
        body: dict[str, Any] = {"model": model, "input": payload["messages"]}
        if payload.get("max_tokens") is not None:
            body["max_output_tokens"] = payload["max_tokens"]
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self.config.base_url}/responses", headers=self.headers, json=body
                )
        except httpx.HTTPError as exc:
            raise ProviderError("openai", "OpenAI network error") from exc
        if response.status_code >= 400:
            raise self._error(response)
        data = response.json()
        text = data.get("output_text") or _responses_text(data)
        # Keep the application's provider-neutral internal contract.
        normalized = {
            "id": data.get("id", ""),
            "object": "chat.completion",
            "model": data.get("model", model),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
            "usage": data.get("usage", {}),
        }
        return ProviderAttempt(
            "openai", model, int((time.perf_counter() - started) * 1000), normalized
        )

    async def validate(self, model: str) -> None:
        await self.chat(
            {"messages": [{"role": "user", "content": "Reply exactly OK"}], "max_tokens": 16},
            model,
        )


def _responses_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "".join(parts)


def provider_for(config: ProviderConfig, settings: Settings) -> BaseProvider:
    if config.name == "openai":
        return OpenAIProvider(config, settings)
    return OpenAICompatibleProvider(config, settings)
