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
    def __init__(self, settings: Settings, provider_loader=None):
        self.settings = settings
        self._provider_loader = provider_loader or (lambda: settings.providers)
        self._failures: dict[str, FailureState] = {}
        self._lock = asyncio.Lock()

    def _in_cooldown(self, provider: str) -> bool:
        failure = self._failures.get(provider)
        if not failure:
            return False
        return (time.time() - failure.failed_at) < self.settings.provider_failure_cooldown_seconds

    def _model_allowed(self, candidate: ProviderConfig, model: str, free_only: bool) -> bool:
        selected = candidate.default_model if model == "auto" else model
        if candidate.allowed_models and selected not in candidate.allowed_models:
            return False
        if not free_only:
            return True
        if not candidate.free_eligible:
            return False
        if candidate.free_models:
            return selected in candidate.free_models
        # Without an explicit free-model allowlist, only the provider's configured
        # default model may be used in free-only mode. This prevents a caller from
        # switching a free-eligible provider to an arbitrary paid model.
        return selected == candidate.default_model

    def candidates(self, *, provider: str | None, free_only: bool, model: str = "auto") -> list[ProviderConfig]:
        candidates = [p for p in self._provider_loader() if p.configured]
        if provider:
            candidates = [p for p in candidates if p.name == provider]
        candidates = [p for p in candidates if self._model_allowed(p, model, free_only)]
        candidates.sort(key=lambda p: p.priority)
        active = [p for p in candidates if not self._in_cooldown(p.name)]
        return active or candidates

    async def route(self, payload: dict[str, Any], *, provider: str | None, free_only: bool, model: str) -> ProviderAttempt:
        if not free_only and not self.settings.allow_paid_routes:
            raise RuntimeError("Paid routing is disabled by operator policy.")
        candidates = self.candidates(provider=provider, free_only=free_only, model=model)
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
        for p in sorted(self._provider_loader(), key=lambda item: item.priority):
            failure = self._failures.get(p.name)
            output.append(
                {
                    "name": p.name,
                    "configured": p.configured,
                    "enabled": p.enabled,
                    "freeEligible": p.free_eligible,
                    "defaultModel": p.default_model or None,
                    "baseUrl": p.base_url,
                    "allowedModels": list(p.allowed_models),
                    "freeModels": list(p.free_models),
                    "priority": p.priority,
                    "cooldown": self._in_cooldown(p.name),
                    "lastError": failure.reason[:240] if failure else None,
                }
            )
        return output

    async def clear_failure(self, provider: str) -> None:
        async with self._lock:
            self._failures.pop(provider, None)
