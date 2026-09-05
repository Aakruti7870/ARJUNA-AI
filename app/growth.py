from __future__ import annotations

import re
from typing import Any


def _entry(label: str, category: str, channels: list[str], capabilities: list[str], auth: str, kind: str = "integration") -> dict[str, Any]:
    return {
        "label": label,
        "category": category,
        "kind": kind,
        "channels": channels,
        "capabilities": capabilities,
        "auth": auth,
    }


# ARJUNA uses one extensible connector registry instead of pretending every external
# product is live by default. Any item below can be configured globally; actual
# actions stay subject to the provider's official API, scopes and account approval.
PLATFORM_CATALOG: dict[str, dict[str, Any]] = {
    # Advertising / social / messaging
    "meta_ads": _entry("Meta Ads", "Advertising", ["Facebook", "Instagram"], ["ads", "lead_ads", "audiences", "insights", "webhooks"], "OAuth / system user token"),
    "instagram": _entry("Instagram", "Social", ["Instagram"], ["publishing", "comments", "messages", "insights", "webhooks"], "Meta OAuth"),
    "whatsapp_business": _entry("WhatsApp Business", "Messaging", ["WhatsApp"], ["messages", "templates", "webhooks", "lead_followup"], "Meta Cloud API token"),
    "google_ads": _entry("Google Ads", "Advertising", ["Search", "Display", "YouTube"], ["ads", "keywords", "audiences", "conversions", "insights"], "Google OAuth + developer token"),
    "youtube": _entry("YouTube", "Social", ["YouTube"], ["publishing", "analytics", "comments"], "Google OAuth"),
    "linkedin_ads": _entry("LinkedIn", "Advertising", ["LinkedIn"], ["ads", "lead_forms", "publishing", "insights"], "LinkedIn OAuth"),
    "tiktok_ads": _entry("TikTok", "Advertising", ["TikTok"], ["ads", "lead_ads", "audiences", "insights"], "TikTok OAuth / access token"),
    "x_ads": _entry("X", "Social", ["X"], ["ads", "publishing", "analytics"], "OAuth"),
    "telegram": _entry("Telegram", "Messaging", ["Telegram"], ["messages", "bots", "webhooks", "lead_followup"], "Bot token"),
    "discord": _entry("Discord", "Messaging", ["Discord"], ["bots", "messages", "webhooks", "community"], "Bot token / OAuth"),
    "slack": _entry("Slack", "Collaboration", ["Slack"], ["messages", "channels", "files", "events", "workflow"], "Slack OAuth"),
    "microsoft_teams": _entry("Microsoft Teams", "Collaboration", ["Teams"], ["messages", "channels", "meetings", "files", "events"], "Microsoft OAuth"),
    "email": _entry("Email", "Messaging", ["Email"], ["campaigns", "transactional", "lead_followup"], "SMTP or provider API"),

    # Google Workspace
    "gmail": _entry("Gmail", "Google Workspace", ["Gmail"], ["search", "read", "draft", "send", "labels"], "Google OAuth"),
    "google_calendar": _entry("Google Calendar", "Google Workspace", ["Calendar"], ["events", "availability", "create", "update"], "Google OAuth"),
    "google_drive": _entry("Google Drive", "Google Workspace", ["Drive"], ["files", "search", "read", "upload"], "Google OAuth"),
    "google_contacts": _entry("Google Contacts", "Google Workspace", ["Contacts"], ["people", "lookup", "directory"], "Google OAuth"),
    "google_sheets": _entry("Google Sheets", "Google Workspace", ["Sheets"], ["read", "write", "append", "tables"], "Google OAuth"),

    # Microsoft 365
    "outlook": _entry("Outlook", "Microsoft 365", ["Mail"], ["search", "read", "draft", "send"], "Microsoft OAuth"),
    "microsoft_calendar": _entry("Microsoft Calendar", "Microsoft 365", ["Calendar"], ["events", "availability", "create", "update"], "Microsoft OAuth"),
    "onedrive": _entry("OneDrive", "Microsoft 365", ["OneDrive"], ["files", "search", "read", "upload"], "Microsoft OAuth"),
    "sharepoint": _entry("SharePoint", "Microsoft 365", ["SharePoint"], ["sites", "files", "lists", "search"], "Microsoft OAuth"),

    # Development / project management
    "github": _entry("GitHub", "Developer", ["GitHub"], ["repositories", "issues", "pull_requests", "actions", "code"], "GitHub App / OAuth token"),
    "gitlab": _entry("GitLab", "Developer", ["GitLab"], ["repositories", "issues", "merge_requests", "pipelines"], "OAuth / access token"),
    "bitbucket": _entry("Bitbucket", "Developer", ["Bitbucket"], ["repositories", "pull_requests", "pipelines"], "OAuth / access token"),
    "jira": _entry("Jira", "Project Management", ["Jira"], ["issues", "projects", "search", "workflow"], "Atlassian OAuth"),
    "linear": _entry("Linear", "Project Management", ["Linear"], ["issues", "projects", "cycles", "workflow"], "OAuth / API key"),
    "asana": _entry("Asana", "Project Management", ["Asana"], ["tasks", "projects", "comments", "workflow"], "OAuth"),
    "trello": _entry("Trello", "Project Management", ["Trello"], ["boards", "cards", "lists", "automation"], "OAuth / token"),

    # Knowledge / files
    "notion": _entry("Notion", "Knowledge", ["Notion"], ["pages", "databases", "search", "write"], "Notion integration token / OAuth"),
    "confluence": _entry("Confluence", "Knowledge", ["Confluence"], ["pages", "spaces", "search", "write"], "Atlassian OAuth"),
    "dropbox": _entry("Dropbox", "Files", ["Dropbox"], ["files", "search", "read", "upload", "sharing"], "Dropbox OAuth"),
    "box": _entry("Box", "Files", ["Box"], ["files", "search", "read", "upload", "sharing"], "Box OAuth"),

    # CRM / support / sales
    "salesforce": _entry("Salesforce", "CRM", ["Salesforce"], ["leads", "contacts", "accounts", "opportunities", "workflow"], "Salesforce OAuth"),
    "hubspot": _entry("HubSpot", "CRM", ["HubSpot"], ["contacts", "companies", "deals", "tickets", "marketing"], "HubSpot OAuth / private app token"),
    "zoho_crm": _entry("Zoho CRM", "CRM", ["Zoho"], ["leads", "contacts", "deals", "workflow"], "Zoho OAuth"),
    "freshdesk": _entry("Freshdesk", "Support", ["Freshdesk"], ["tickets", "contacts", "agents", "automation"], "API key / OAuth"),
    "zendesk": _entry("Zendesk", "Support", ["Zendesk"], ["tickets", "users", "search", "automation"], "OAuth / API token"),

    # Commerce / payments
    "stripe": _entry("Stripe", "Payments", ["Stripe"], ["customers", "payments", "invoices", "subscriptions", "webhooks"], "Restricted API key / OAuth"),
    "shopify": _entry("Shopify", "Commerce", ["Shopify"], ["products", "orders", "customers", "inventory", "webhooks"], "Shopify OAuth"),
    "woocommerce": _entry("WooCommerce", "Commerce", ["WooCommerce"], ["products", "orders", "customers", "inventory"], "REST API keys"),

    # Automation platforms
    "zapier": _entry("Zapier", "Automation", ["Zapier"], ["triggers", "actions", "webhooks", "workflows"], "OAuth / webhook"),
    "make": _entry("Make", "Automation", ["Make"], ["scenarios", "webhooks", "workflows"], "API token / webhook"),
    "n8n": _entry("n8n", "Automation", ["n8n"], ["workflows", "webhooks", "executions"], "API key / webhook"),
    "pipedream": _entry("Pipedream", "Automation", ["Pipedream"], ["workflows", "events", "webhooks"], "OAuth / API key"),

    # Data
    "postgresql": _entry("PostgreSQL", "Database", ["PostgreSQL"], ["query", "schema", "read", "write"], "Connection URL / service credentials"),
    "mysql": _entry("MySQL", "Database", ["MySQL"], ["query", "schema", "read", "write"], "Connection URL / service credentials"),
    "mongodb": _entry("MongoDB", "Database", ["MongoDB"], ["query", "collections", "read", "write"], "Connection URL / service credentials"),
    "supabase": _entry("Supabase", "Database", ["Supabase"], ["database", "auth", "storage", "functions"], "Project URL + service role / OAuth"),
    "firebase": _entry("Firebase", "Database", ["Firebase"], ["firestore", "auth", "storage", "functions"], "Service account / OAuth"),

    # MCP and custom plugin surfaces
    "mcp_streamable_http": _entry("MCP · Streamable HTTP", "MCP", ["Remote MCP"], ["tools", "resources", "prompts", "capability_discovery"], "MCP endpoint + optional bearer/OAuth", kind="mcp"),
    "mcp_sse": _entry("MCP · SSE", "MCP", ["Remote MCP"], ["tools", "resources", "prompts", "legacy_sse"], "MCP SSE endpoint + optional bearer/OAuth", kind="mcp"),
    "mcp_stdio": _entry("MCP · stdio", "MCP", ["Local / worker"], ["tools", "resources", "prompts", "local_process"], "Command + environment; local/worker deployment only", kind="mcp"),
    "plugin_openapi": _entry("OpenAPI Plugin", "Plugins", ["REST API"], ["openapi", "tools", "actions", "schema_discovery"], "OpenAPI URL + auth config", kind="plugin"),
    "plugin_custom": _entry("Custom ARJUNA Plugin", "Plugins", ["Custom"], ["manifest", "tools", "actions", "events"], "Plugin manifest + encrypted credentials", kind="plugin"),
    "webhook": _entry("Generic Webhook", "Custom", ["Custom"], ["inbound", "outbound", "automation"], "Shared secret / bearer token"),
    "rest_api": _entry("Generic REST API", "Custom", ["REST"], ["requests", "actions", "webhooks"], "API key / OAuth / bearer token"),
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
