from __future__ import annotations

import hashlib
import json
import re
from typing import Any

FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\s*\n(?P<body>[\s\S]*?)```", re.MULTILINE)


def _extract_fenced(content: str) -> tuple[str, str | None]:
    matches = list(FENCE_RE.finditer(content))
    if not matches:
        return content, None
    preferred = next((m for m in matches if (m.group("lang") or "").lower() in {"html", "htm", "json", "md", "markdown"}), matches[0])
    return preferred.group("body").strip(), (preferred.group("lang") or "").lower() or None


def _detect_kind(content: str, hint: str = "auto") -> str:
    hint = (hint or "auto").lower()
    if hint in {"html", "markdown", "json", "text"}:
        return hint

    stripped = content.strip()
    if not stripped:
        return "text"
    try:
        json.loads(stripped)
        return "json"
    except Exception:
        pass

    if re.search(r"<!doctype\s+html|<html\b|<body\b|<(?:div|section|main|article|header|footer|form|button|input|style)\b", stripped, re.I):
        return "html"
    if re.search(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s+)|\[[^\]]+\]\([^\)]+\)|\*\*[^*]+\*\*", stripped, re.M):
        return "markdown"
    return "text"


def _count(pattern: str, content: str, flags: int = re.I) -> int:
    return len(re.findall(pattern, content, flags))


def analyze_preview(content: str, hint: str = "auto") -> dict[str, Any]:
    extracted, fence_lang = _extract_fenced(content)
    kind = _detect_kind(extracted, hint if hint != "auto" else (fence_lang or "auto"))
    text = extracted.strip()

    risks: list[dict[str, Any]] = []

    def add_risk(code: str, label: str, pattern: str, weight: int, flags: int = re.I) -> None:
        hits = _count(pattern, text, flags)
        if hits:
            risks.append({"code": code, "label": label, "count": hits, "weight": weight})

    add_risk("script", "Script execution", r"<script\b|\beval\s*\(|\bnew\s+Function\s*\(", 32)
    add_risk("events", "Inline event handlers", r"\son[a-z]+\s*=", 24)
    add_risk("javascript-url", "javascript: URL", r"javascript\s*:", 28)
    add_risk("active-embed", "Active embedded content", r"<(?:iframe|object|embed)\b", 24)
    add_risk("network-code", "Network-capable code", r"\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\s*\(", 18)
    add_risk("form", "Form submission surface", r"<form\b", 10)
    add_risk("storage", "Browser storage access", r"\b(?:localStorage|sessionStorage|indexedDB)\b", 10)
    add_risk("remote-resource", "Remote resource reference", r"(?:src|href)\s*=\s*[\"']https?://|url\(\s*[\"']?https?://|@import\s+(?:url\()?\s*[\"']?https?://", 8)

    risk_score = min(100, sum(min(item["count"], 3) * item["weight"] for item in risks))
    risk_level = "high" if risk_score >= 55 else "medium" if risk_score >= 20 else "low"

    lines = text.count("\n") + (1 if text else 0)
    words = len(re.findall(r"\S+", text))
    chars = len(text)
    structure = {
        "lines": lines,
        "words": words,
        "characters": chars,
        "headings": _count(r"<h[1-6]\b|^#{1,6}\s+", text, re.I | re.M),
        "links": _count(r"<a\b|\[[^\]]+\]\([^\)]+\)", text),
        "images": _count(r"<img\b|!\[[^\]]*\]\([^\)]+\)", text),
        "forms": _count(r"<form\b", text),
        "buttons": _count(r"<button\b", text),
        "inputs": _count(r"<(?:input|select|textarea)\b", text),
    }

    insights: list[str] = []
    if not text:
        insights.append("No preview content detected.")
    if kind == "html" and not re.search(r"<meta[^>]+name=[\"']viewport[\"']", text, re.I):
        insights.append("HTML has no viewport meta tag; mobile rendering may differ from production.")
    if kind == "html" and structure["forms"] and structure["inputs"] == 0:
        insights.append("A form exists without detected input controls.")
    if kind == "html" and structure["buttons"] and not re.search(r"<button[^>]+type=", text, re.I):
        insights.append("Buttons without explicit type were detected; inside forms they default to submit.")
    if structure["images"] and not re.search(r"<img[^>]+alt=|!\[[^\]]+\]", text, re.I):
        insights.append("Image content may be missing accessible alternative text.")
    if kind == "json":
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                insights.append(f"Valid JSON object with {len(parsed)} top-level keys.")
            elif isinstance(parsed, list):
                insights.append(f"Valid JSON array with {len(parsed)} items.")
        except Exception as exc:
            insights.append(f"JSON parse failed: {str(exc)[:120]}")
    if kind == "markdown" and structure["headings"] == 0 and words > 120:
        insights.append("Long markdown has no headings; structure may be hard to scan.")
    if risks:
        insights.append("Safe preview mode should remain enabled because active or external content was detected.")
    elif kind == "html":
        insights.append("No obvious active-content risks detected by the static scanner.")

    completeness = 100
    if not text:
        completeness = 0
    else:
        if words < 8:
            completeness -= 20
        if kind == "html" and not re.search(r"<(?:main|section|article|body)\b", text, re.I):
            completeness -= 10
        if kind == "markdown" and structure["headings"] == 0:
            completeness -= 8
        if kind == "json":
            try:
                json.loads(text)
            except Exception:
                completeness -= 35
    completeness = max(0, completeness)

    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {
        "kind": kind,
        "fenceLanguage": fence_lang,
        "content": extracted,
        "fingerprint": fingerprint,
        "riskScore": risk_score,
        "riskLevel": risk_level,
        "risks": risks,
        "structure": structure,
        "completenessScore": completeness,
        "insights": insights,
        "stored": False,
        "execution": "none",
    }
