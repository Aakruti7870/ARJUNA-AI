from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .config import ProviderConfig, Settings
from .providers import OpenAICompatibleProvider, ProviderAttempt, ProviderError


@dataclass
class FailureState:
    failed_at: float
    reason: str


class ModelRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._failures: dict[str, FailureState] = {}
        self._lock = asyncio.Lock()

    def _in_cooldown(self, provider: str) -> bool:
        failure = self._failures.get(provider)
        if not failure:
            return False
        return (time.time() - failure.failed_at) < self.settings.provider_failure_cooldown_seconds

    def candidates(self, *, provider: str | None, free_only: bool) -> list[ProviderConfig]:
        candidates = [p for p in self.settings.providers if p.configured]
        if provider:
            candidates = [p for p in candidates if p.name == provider]
        if free_only:
            candidates = [p for p in candidates if p.free_eligible]
        candidates.sort(key=lambda p: p.priority)
        active = [p for p in candidates if not self._in_cooldown(p.name)]
        return active or candidates

    async def route(self, payload: dict[str, Any], *, provider: str | None, free_only: bool, model: str) -> ProviderAttempt:
        candidates = self.candidates(provider=provider, free_only=free_only)
        if not candidates:
            mode = "free-eligible" if free_only else "configured"
            raise RuntimeError(f"No {mode} providers are available. Configure provider keys/models first.")

        errors: list[str] = []
        for candidate in candidates:
            selected_model = candidate.default_model if model == "auto" else model
            client = OpenAICompatibleProvider(candidate, self.settings)
            try:
                attempt = await client.chat(payload, selected_model)
                async with self._lock:
                    self._failures.pop(candidate.name, None)
                return attempt
            except ProviderError as exc:
                async with self._lock:
                    self._failures[candidate.name] = FailureState(time.time(), str(exc))
                errors.append(f"{candidate.name}: {str(exc)[:240]}")

        raise RuntimeError("All candidate providers failed: " + " | ".join(errors))

    def public_status(self) -> list[dict[str, Any]]:
        output = []
        for p in sorted(self.settings.providers, key=lambda item: item.priority):
            failure = self._failures.get(p.name)
            output.append(
                {
                    "name": p.name,
                    "configured": p.configured,
                    "enabled": p.enabled,
                    "freeEligible": p.free_eligible,
                    "defaultModel": p.default_model or None,
                    "priority": p.priority,
                    "cooldown": self._in_cooldown(p.name),
                    "lastError": failure.reason[:240] if failure else None,
                }
            )
        return output
