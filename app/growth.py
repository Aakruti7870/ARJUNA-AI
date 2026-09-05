from __future__ import annotations

import re
from typing import Any

PLATFORM_CATALOG: dict[str, dict[str, Any]] = {
    "meta_ads": {"label": "Meta Ads", "channels": ["Facebook", "Instagram"], "capabilities": ["ads", "lead_ads", "audiences", "insights", "webhooks"], "auth": "OAuth / system user token"},
    "instagram": {"label": "Instagram", "channels": ["Instagram"], "capabilities": ["publishing", "comments", "messages", "insights", "webhooks"], "auth": "Meta OAuth"},
    "whatsapp_business": {"label": "WhatsApp Business", "channels": ["WhatsApp"], "capabilities": ["messages", "templates", "webhooks", "lead_followup"], "auth": "Meta Cloud API token"},
    "google_ads": {"label": "Google Ads", "channels": ["Search", "Display", "YouTube"], "capabilities": ["ads", "keywords", "audiences", "conversions", "insights"], "auth": "Google OAuth + developer token"},
    "youtube": {"label": "YouTube", "channels": ["YouTube"], "capabilities": ["publishing", "analytics", "comments"], "auth": "Google OAuth"},
    "linkedin_ads": {"label": "LinkedIn", "channels": ["LinkedIn"], "capabilities": ["ads", "lead_forms", "publishing", "insights"], "auth": "LinkedIn OAuth"},
    "tiktok_ads": {"label": "TikTok", "channels": ["TikTok"], "capabilities": ["ads", "lead_ads", "audiences", "insights"], "auth": "TikTok OAuth / access token"},
    "x_ads": {"label": "X", "channels": ["X"], "capabilities": ["ads", "publishing", "analytics"], "auth": "OAuth"},
    "telegram": {"label": "Telegram", "channels": ["Telegram"], "capabilities": ["messages", "bots", "webhooks", "lead_followup"], "auth": "Bot token"},
    "email": {"label": "Email", "channels": ["Email"], "capabilities": ["campaigns", "transactional", "lead_followup"], "auth": "SMTP or provider API"},
    "webhook": {"label": "Generic Webhook", "channels": ["Custom"], "capabilities": ["inbound", "outbound", "automation"], "auth": "Shared secret / bearer token"},
}


def catalog() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in PLATFORM_CATALOG.items()]


def normalize_tags(tags: list[str] | None) -> list[str]:
    return sorted({t.strip().lower() for t in (tags or []) if t and t.strip()})[:50]


def score_lead(lead: dict[str, Any]) -> tuple[int, list[str], str]:
    score = 10
    reasons: list[str] = []
    if lead.get("email"):
        score += 12; reasons.append("email provided")
    if lead.get("phone"):
        score += 15; reasons.append("phone provided")
    if lead.get("company"):
        score += 10; reasons.append("company provided")
    message = (lead.get("message") or "").strip()
    if len(message) >= 40:
        score += 8; reasons.append("detailed enquiry")
    if re.search(r"\b(price|pricing|quote|proposal|demo|buy|purchase|urgent|today|call|meeting|budget)\b", message, re.I):
        score += 18; reasons.append("commercial intent detected")
    source = (lead.get("source") or "").lower()
    if any(x in source for x in ("lead", "ad", "referral", "demo")):
        score += 10; reasons.append("high-intent source")
    score = max(0, min(100, score))
    next_action = "contact_now" if score >= 70 else "contact_today" if score >= 45 else "nurture"
    return score, reasons, next_action


def condition_matches(condition: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    if not condition:
        return True
    field = str(condition.get("field") or "").strip()
    op = str(condition.get("op") or "eq").lower()
    expected = condition.get("value")
    actual: Any = payload
    for part in field.split(".") if field else []:
        if not isinstance(actual, dict):
            return False
        actual = actual.get(part)
    if op == "eq": return actual == expected
    if op == "neq": return actual != expected
    if op == "contains": return str(expected).lower() in str(actual or "").lower()
    if op == "in": return actual in (expected or [])
    if op == "gte":
        try: return float(actual) >= float(expected)
        except (TypeError, ValueError): return False
    if op == "lte":
        try: return float(actual) <= float(expected)
        except (TypeError, ValueError): return False
    if op == "exists": return actual not in (None, "", [], {})
    return False


def recommend_automation(lead: dict[str, Any]) -> list[dict[str, Any]]:
    score = int(lead.get("score") or 0)
    actions: list[dict[str, Any]] = []
    if score >= 70:
        actions.extend([
            {"type": "set_lead_status", "value": "priority"},
            {"type": "create_followup", "channel": "whatsapp_business", "priority": "high", "delay_minutes": 0},
            {"type": "create_followup", "channel": "email", "priority": "high", "delay_minutes": 5},
        ])
    elif score >= 45:
        actions.append({"type": "create_followup", "channel": "email", "priority": "normal", "delay_minutes": 60})
    else:
        actions.append({"type": "create_followup", "channel": "email", "priority": "low", "delay_minutes": 1440})
    return actions
