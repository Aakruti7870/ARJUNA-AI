from __future__ import annotations

import html
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

from .config import ProviderConfig, Settings
from .providers import OpenAICompatibleProvider, ProviderError
from .session_auth import SessionData


@dataclass(frozen=True)
class ProviderMeta:
    name: str
    label: str
    base_url: str
    priority: int
    free_eligible: bool
    capabilities: dict[str, int]


PROVIDER_CATALOG: dict[str, ProviderMeta] = {
    "nvidia": ProviderMeta(
        "nvidia", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", 10, True,
        {"coding": 92, "reasoning": 92, "vision": 80, "fast": 78, "general": 90},
    ),
    "gemini": ProviderMeta(
        "gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", 20, True,
        {"coding": 90, "reasoning": 92, "vision": 96, "fast": 82, "general": 92},
    ),
    "groq": ProviderMeta(
        "groq", "Groq", "https://api.groq.com/openai/v1", 30, True,
        {"coding": 84, "reasoning": 82, "vision": 55, "fast": 99, "general": 84},
    ),
    "openrouter": ProviderMeta(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", 40, False,
        {"coding": 92, "reasoning": 94, "vision": 90, "fast": 88, "general": 94},
    ),
    "openai": ProviderMeta(
        "openai", "OpenAI", "https://api.openai.com/v1", 50, False,
        {"coding": 96, "reasoning": 97, "vision": 94, "fast": 88, "general": 96},
    ),
    "mistral": ProviderMeta(
        "mistral", "Mistral AI", "https://api.mistral.ai/v1", 60, False,
        {"coding": 90, "reasoning": 88, "vision": 72, "fast": 86, "general": 89},
    ),
    "together": ProviderMeta(
        "together", "Together AI", "https://api.together.xyz/v1", 70, False,
        {"coding": 88, "reasoning": 88, "vision": 78, "fast": 90, "general": 88},
    ),
    "kimi": ProviderMeta(
        "kimi", "Kimi / Moonshot", "https://api.moonshot.ai/v1", 80, False,
        {"coding": 92, "reasoning": 96, "vision": 72, "fast": 80, "general": 93},
    ),
}


def catalog_payload(session: SessionData | None = None) -> list[dict[str, Any]]:
    connected = session.providers if session else {}
    return [
        {
            "provider": meta.name,
            "label": meta.label,
            "connected": meta.name in connected,
            "model": connected[meta.name].default_model if meta.name in connected else "",
            "free_eligible": connected[meta.name].free_eligible if meta.name in connected else meta.free_eligible,
            "capabilities": meta.capabilities,
        }
        for meta in PROVIDER_CATALOG.values()
    ]


def provider_config(provider: str, api_key: str, model: str, free_eligible: bool | None = None) -> ProviderConfig:
    name = provider.strip().lower()
    meta = PROVIDER_CATALOG.get(name)
    if not meta:
        raise ValueError("Unsupported provider")
    return ProviderConfig(
        name=name,
        base_url=meta.base_url,
        api_key=api_key.strip(),
        default_model=model.strip(),
        priority=meta.priority,
        free_eligible=meta.free_eligible if free_eligible is None else free_eligible,
        enabled=True,
    )


def classify_task(prompt: str) -> str:
    text = prompt.lower()
    if any(word in text for word in ("screenshot", "image", "photo", "vision", "look at", "ui reference")):
        return "vision"
    if any(word in text for word in ("build", "app", "website", "dashboard", "component", "code", "api", "frontend", "backend", "html", "css")):
        return "coding"
    if any(word in text for word in ("fast", "quick", "short answer", "summarize quickly")):
        return "fast"
    if any(word in text for word in ("reason", "analyze", "plan", "strategy", "compare", "architecture", "research")):
        return "reasoning"
    return "general"


def rank_routes(session: SessionData, prompt: str, free_only: bool) -> list[dict[str, Any]]:
    task = classify_task(prompt)
    routes: list[dict[str, Any]] = []
    for config in session.providers.values():
        meta = PROVIDER_CATALOG.get(config.name)
        if not meta or not config.configured:
            continue
        if free_only and not config.free_eligible:
            continue
        capability = meta.capabilities.get(task, meta.capabilities.get("general", 70))
        score = float(capability)
        if config.free_eligible:
            score += 3.0
        score -= min(config.priority, 100) / 25.0
        routes.append(
            {
                "provider": config.name,
                "label": meta.label,
                "model": config.default_model,
                "task": task,
                "score": round(max(0.0, min(score, 100.0)), 1),
                "free_eligible": config.free_eligible,
            }
        )
    routes.sort(key=lambda route: route["score"], reverse=True)
    return routes


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return json.dumps(data, ensure_ascii=False)
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _parse_build_result(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    safe = html.escape(raw[:12000])
    return {
        "title": "ARJUNA AI Result",
        "summary": "The selected model returned a text result instead of structured preview JSON.",
        "html": (
            "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><style>body{font-family:system-ui;padding:32px;"
            "background:#fff;color:#111;line-height:1.6}pre{white-space:pre-wrap}</style></head>"
            f"<body><h1>ARJUNA AI</h1><pre>{safe}</pre></body></html>"
        ),
        "notes": ["Fallback preview generated from model text output."],
    }


def _system_prompt(task: str) -> str:
    return f"""You are ARJUNA AI's autonomous build engine. The detected task type is {task}.
Return exactly one JSON object and no markdown fences. The object must contain:
- title: concise project/result title
- summary: short explanation
- html: a complete standalone HTML document for the live preview
- notes: an array of short implementation notes

For coding/build requests, produce a polished responsive working UI in the html field with embedded CSS and only minimal inline JavaScript when necessary. Do not load remote JavaScript, do not make network requests, and do not include secrets. For non-UI requests, create a clean readable HTML report. The result must be safe to render in a sandboxed iframe."""


async def execute_build(
    session: SessionData,
    settings: Settings,
    prompt: str,
    free_only: bool,
) -> dict[str, Any]:
    routes = rank_routes(session, prompt, free_only)
    if not routes:
        raise RuntimeError("No eligible connected AI provider is available")

    failures: list[str] = []
    task = routes[0]["task"]
    request_payload = {
        "messages": [
            {"role": "system", "content": _system_prompt(task)},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 8192,
    }

    for route in routes:
        config = session.providers[route["provider"]]
        provider = OpenAICompatibleProvider(config, settings)
        try:
            attempt = await provider.chat(request_payload, config.default_model)
        except ProviderError as exc:
            failures.append(f"{config.name}:{exc.status_code or 'network'}")
            continue

        raw_text = _extract_text(attempt.response)
        result = _parse_build_result(raw_text)
        preview_html = str(result.get("html") or "")[:250000]
        preview_id = secrets.token_urlsafe(24)
        session.previews[preview_id] = preview_html
        while len(session.previews) > 20:
            session.previews.pop(next(iter(session.previews)))

        return {
            "provider": attempt.provider,
            "model": attempt.model,
            "latency_ms": attempt.latency_ms,
            "task": task,
            "score": route["score"],
            "recommended_routes": routes[:4],
            "fallbacks_before_success": failures,
            "title": str(result.get("title") or "ARJUNA AI Result")[:200],
            "summary": str(result.get("summary") or "")[:4000],
            "notes": result.get("notes") if isinstance(result.get("notes"), list) else [],
            "html": preview_html,
            "preview_id": preview_id,
        }

    raise RuntimeError("All connected AI providers failed: " + ", ".join(failures))
