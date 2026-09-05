from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, func, select, update
from sqlalchemy.engine import Engine

from .config import ProviderConfig


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


class Storage:
    def __init__(self, database_url: str, hash_secret: str, vault_secret: str | None = None):
        if database_url.startswith("sqlite:///./"):
            db_path = Path(database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.hash_secret = hash_secret.encode("utf-8")
        derived = hashlib.sha256((vault_secret or hash_secret).encode("utf-8")).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(derived))
        self.meta = MetaData()
        self.api_keys = Table(
            "api_keys", self.meta,
            Column("id", String(36), primary_key=True),
            Column("name", String(120), nullable=False),
            Column("prefix", String(32), nullable=False, index=True),
            Column("key_hash", String(64), nullable=False, unique=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("last_used_at", DateTime(timezone=True), nullable=True),
            Column("revoked_at", DateTime(timezone=True), nullable=True),
        )
        self.usage = Table(
            "usage_events", self.meta,
            Column("id", String(36), primary_key=True),
            Column("api_key_id", String(36), nullable=True, index=True),
            Column("provider", String(50), nullable=False),
            Column("model", String(300), nullable=False),
            Column("tokens", Integer, nullable=True),
            Column("latency_ms", Integer, nullable=False),
            Column("status", String(20), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, index=True),
        )
        self.provider_overrides = Table(
            "provider_overrides", self.meta,
            Column("name", String(50), primary_key=True),
            Column("base_url", String(1000), nullable=False),
            Column("api_key_ciphertext", Text, nullable=True),
            Column("default_model", String(300), nullable=False),
            Column("priority", Integer, nullable=False),
            Column("free_eligible", Boolean, nullable=False),
            Column("enabled", Boolean, nullable=False),
            Column("allowed_models", Text, nullable=False),
            Column("free_models", Text, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.growth_connectors = Table(
            "growth_connectors", self.meta,
            Column("platform", String(60), primary_key=True),
            Column("account_label", String(200), nullable=False),
            Column("account_id", String(300), nullable=False),
            Column("credentials_ciphertext", Text, nullable=True),
            Column("config_json", Text, nullable=False),
            Column("enabled", Boolean, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.leads = Table(
            "growth_leads", self.meta,
            Column("id", String(36), primary_key=True),
            Column("source", String(100), nullable=False, index=True),
            Column("name", String(200), nullable=False),
            Column("email", String(320), nullable=True, index=True),
            Column("phone", String(80), nullable=True, index=True),
            Column("company", String(200), nullable=True),
            Column("message", Text, nullable=True),
            Column("status", String(50), nullable=False, index=True),
            Column("score", Integer, nullable=False, index=True),
            Column("score_reasons", Text, nullable=False),
            Column("next_action", String(80), nullable=False),
            Column("owner", String(200), nullable=True),
            Column("tags_json", Text, nullable=False),
            Column("notes", Text, nullable=True),
            Column("metadata_json", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, index=True),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.campaigns = Table(
            "growth_campaigns", self.meta,
            Column("id", String(36), primary_key=True),
            Column("name", String(200), nullable=False),
            Column("platform", String(60), nullable=False, index=True),
            Column("objective", String(100), nullable=False),
            Column("status", String(50), nullable=False, index=True),
            Column("budget_daily", Float, nullable=True),
            Column("currency", String(8), nullable=False),
            Column("audience_json", Text, nullable=False),
            Column("creative_json", Text, nullable=False),
            Column("metadata_json", Text, nullable=False),
            Column("external_id", String(300), nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.proposals = Table(
            "growth_proposals", self.meta,
            Column("id", String(36), primary_key=True),
            Column("lead_id", String(36), nullable=True, index=True),
            Column("title", String(250), nullable=False),
            Column("body", Text, nullable=False),
            Column("amount", Float, nullable=True),
            Column("currency", String(8), nullable=False),
            Column("status", String(50), nullable=False, index=True),
            Column("share_prefix", String(20), nullable=False),
            Column("share_hash", String(64), nullable=False, unique=True),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.automations = Table(
            "growth_automations", self.meta,
            Column("id", String(36), primary_key=True),
            Column("name", String(200), nullable=False),
            Column("trigger_event", String(100), nullable=False, index=True),
            Column("condition_json", Text, nullable=False),
            Column("actions_json", Text, nullable=False),
            Column("enabled", Boolean, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.automation_runs = Table(
            "growth_automation_runs", self.meta,
            Column("id", String(36), primary_key=True),
            Column("automation_id", String(36), nullable=True, index=True),
            Column("event_type", String(100), nullable=False, index=True),
            Column("status", String(30), nullable=False),
            Column("result_json", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, index=True),
        )
        self.outbox = Table(
            "growth_outbox", self.meta,
            Column("id", String(36), primary_key=True),
            Column("kind", String(60), nullable=False),
            Column("channel", String(60), nullable=False, index=True),
            Column("recipient", String(500), nullable=True),
            Column("payload_json", Text, nullable=False),
            Column("status", String(30), nullable=False, index=True),
            Column("scheduled_for", DateTime(timezone=True), nullable=False, index=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.meta.create_all(self.engine)

    def _digest(self, raw: str) -> str:
        return hmac.new(self.hash_secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def _encrypt(self, raw: str) -> str:
        return self.cipher.encrypt(raw.encode("utf-8")).decode("ascii")

    def _decrypt(self, ciphertext: str | None) -> str:
        if not ciphertext:
            return ""
        try:
            return self.cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Provider vault secret does not match stored credentials") from exc

    def create_api_key(self, name: str) -> tuple[dict[str, Any], str]:
        raw = "arjuna_live_" + secrets.token_urlsafe(32)
        row = {"id": str(uuid.uuid4()), "name": name.strip(), "prefix": raw[:18], "key_hash": self._digest(raw),
               "created_at": utcnow(), "last_used_at": None, "revoked_at": None}
        with self.engine.begin() as conn: conn.execute(self.api_keys.insert().values(**row))
        return {k: row[k] for k in ("id", "name", "prefix", "created_at", "last_used_at", "revoked_at")}, raw

    def list_api_keys(self) -> list[dict[str, Any]]:
        stmt = select(self.api_keys.c.id, self.api_keys.c.name, self.api_keys.c.prefix, self.api_keys.c.created_at,
                      self.api_keys.c.last_used_at, self.api_keys.c.revoked_at).order_by(self.api_keys.c.created_at.desc())
        with self.engine.begin() as conn: return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def verify_api_key(self, raw: str) -> dict[str, Any] | None:
        digest = self._digest(raw)
        stmt = select(self.api_keys).where(self.api_keys.c.key_hash == digest, self.api_keys.c.revoked_at.is_(None))
        with self.engine.begin() as conn:
            row = conn.execute(stmt).fetchone()
            if not row: return None
            conn.execute(update(self.api_keys).where(self.api_keys.c.id == row.id).values(last_used_at=utcnow()))
            return dict(row._mapping)

    def revoke_api_key(self, key_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(update(self.api_keys).where(self.api_keys.c.id == key_id, self.api_keys.c.revoked_at.is_(None)).values(revoked_at=utcnow()))
            return result.rowcount > 0

    def upsert_provider(self, *, name: str, base_url: str, default_model: str, priority: int, free_eligible: bool,
                        enabled: bool, allowed_models: list[str], free_models: list[str], api_key: str | None) -> None:
        normalized_allowed = sorted({m.strip() for m in allowed_models if m.strip()})
        normalized_free = sorted({m.strip() for m in free_models if m.strip()})
        with self.engine.begin() as conn:
            existing = conn.execute(select(self.provider_overrides).where(self.provider_overrides.c.name == name)).fetchone()
            ciphertext = existing.api_key_ciphertext if existing else None
            if api_key is not None and api_key.strip(): ciphertext = self._encrypt(api_key.strip())
            values = {"name": name, "base_url": base_url.rstrip("/"), "api_key_ciphertext": ciphertext,
                      "default_model": default_model.strip(), "priority": priority, "free_eligible": free_eligible,
                      "enabled": enabled, "allowed_models": _json(normalized_allowed), "free_models": _json(normalized_free), "updated_at": utcnow()}
            if existing: conn.execute(update(self.provider_overrides).where(self.provider_overrides.c.name == name).values(**values))
            else: conn.execute(self.provider_overrides.insert().values(**values))

    def delete_provider_override(self, name: str) -> bool:
        with self.engine.begin() as conn: return conn.execute(self.provider_overrides.delete().where(self.provider_overrides.c.name == name)).rowcount > 0

    def provider_override_names(self) -> set[str]:
        with self.engine.begin() as conn: return {row.name for row in conn.execute(select(self.provider_overrides.c.name)).fetchall()}

    def effective_providers(self, base: Iterable[ProviderConfig]) -> tuple[ProviderConfig, ...]:
        base_map = {p.name: p for p in base}
        with self.engine.begin() as conn: rows = [dict(r._mapping) for r in conn.execute(select(self.provider_overrides)).fetchall()]
        for row in rows:
            current = base_map.get(row["name"])
            api_key = self._decrypt(row["api_key_ciphertext"]) or (current.api_key if current else "")
            base_map[row["name"]] = ProviderConfig(name=row["name"], base_url=row["base_url"], api_key=api_key,
                default_model=row["default_model"], priority=int(row["priority"]), free_eligible=bool(row["free_eligible"]),
                enabled=bool(row["enabled"]), allowed_models=tuple(_loads(row["allowed_models"], [])), free_models=tuple(_loads(row["free_models"], [])))
        return tuple(base_map.values())

    def record_usage(self, *, api_key_id: str | None, provider: str, model: str, tokens: int | None, latency_ms: int, status: str = "ok") -> None:
        with self.engine.begin() as conn:
            conn.execute(self.usage.insert().values(id=str(uuid.uuid4()), api_key_id=api_key_id, provider=provider, model=model,
                                                   tokens=tokens, latency_ms=latency_ms, status=status, created_at=utcnow()))

    def recent_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.begin() as conn: return [dict(r._mapping) for r in conn.execute(select(self.usage).order_by(self.usage.c.created_at.desc()).limit(limit)).fetchall()]

    # Growth OS
    def upsert_growth_connector(self, *, platform: str, account_label: str, account_id: str,
                                credentials: dict[str, str] | None, config: dict[str, Any], enabled: bool) -> None:
        with self.engine.begin() as conn:
            existing = conn.execute(select(self.growth_connectors).where(self.growth_connectors.c.platform == platform)).fetchone()
            ciphertext = existing.credentials_ciphertext if existing else None
            if credentials is not None: ciphertext = self._encrypt(_json(credentials))
            values = {"platform": platform, "account_label": account_label.strip(), "account_id": account_id.strip(),
                      "credentials_ciphertext": ciphertext, "config_json": _json(config), "enabled": enabled, "updated_at": utcnow()}
            if existing: conn.execute(update(self.growth_connectors).where(self.growth_connectors.c.platform == platform).values(**values))
            else: conn.execute(self.growth_connectors.insert().values(**values))

    def list_growth_connectors(self) -> list[dict[str, Any]]:
        with self.engine.begin() as conn: rows = conn.execute(select(self.growth_connectors).order_by(self.growth_connectors.c.platform)).fetchall()
        return [{"platform": r.platform, "account_label": r.account_label, "account_id": r.account_id, "configured": bool(r.credentials_ciphertext),
                 "config": _loads(r.config_json, {}), "enabled": bool(r.enabled), "updated_at": r.updated_at} for r in rows]

    def delete_growth_connector(self, platform: str) -> bool:
        with self.engine.begin() as conn: return conn.execute(self.growth_connectors.delete().where(self.growth_connectors.c.platform == platform)).rowcount > 0

    def create_lead(self, lead: dict[str, Any], *, score: int, score_reasons: list[str], next_action: str) -> dict[str, Any]:
        now = utcnow(); row = {"id": str(uuid.uuid4()), "source": lead.get("source") or "manual", "name": lead["name"].strip(),
            "email": (lead.get("email") or "").strip() or None, "phone": (lead.get("phone") or "").strip() or None,
            "company": (lead.get("company") or "").strip() or None, "message": lead.get("message"), "status": "new", "score": score,
            "score_reasons": _json(score_reasons), "next_action": next_action, "owner": None, "tags_json": _json(lead.get("tags") or []),
            "notes": None, "metadata_json": _json(lead.get("metadata") or {}), "created_at": now, "updated_at": now}
        with self.engine.begin() as conn: conn.execute(self.leads.insert().values(**row))
        return self.get_lead(row["id"]) or row

    def _public_lead(self, row: Any) -> dict[str, Any]:
        d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        d["tags"] = _loads(d.pop("tags_json", "[]"), [])
        d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
        d["score_reasons"] = _loads(d.get("score_reasons"), [])
        return d

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn: row = conn.execute(select(self.leads).where(self.leads.c.id == lead_id)).fetchone()
        return self._public_lead(row) if row else None

    def list_leads(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.engine.begin() as conn: rows = conn.execute(select(self.leads).order_by(self.leads.c.created_at.desc()).limit(limit)).fetchall()
        return [self._public_lead(r) for r in rows]

    def update_lead(self, lead_id: str, *, status: str | None = None, owner: str | None = None,
                    tags: list[str] | None = None, notes: str | None = None) -> dict[str, Any] | None:
        values: dict[str, Any] = {"updated_at": utcnow()}
        if status is not None: values["status"] = status
        if owner is not None: values["owner"] = owner or None
        if tags is not None: values["tags_json"] = _json(tags)
        if notes is not None: values["notes"] = notes
        with self.engine.begin() as conn:
            result = conn.execute(update(self.leads).where(self.leads.c.id == lead_id).values(**values))
            if result.rowcount == 0: return None
        return self.get_lead(lead_id)

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow(); row = {"id": str(uuid.uuid4()), "name": payload["name"], "platform": payload["platform"],
            "objective": payload.get("objective") or "lead_generation", "status": payload.get("status") or "draft",
            "budget_daily": payload.get("budget_daily"), "currency": payload.get("currency") or "INR",
            "audience_json": _json(payload.get("audience") or {}), "creative_json": _json(payload.get("creative") or {}),
            "metadata_json": _json(payload.get("metadata") or {}), "external_id": None, "created_at": now, "updated_at": now}
        with self.engine.begin() as conn: conn.execute(self.campaigns.insert().values(**row))
        row["audience"] = payload.get("audience") or {}; row["creative"] = payload.get("creative") or {}; row["metadata"] = payload.get("metadata") or {}
        row.pop("audience_json"); row.pop("creative_json"); row.pop("metadata_json"); return row

    def list_campaigns(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.engine.begin() as conn: rows = conn.execute(select(self.campaigns).order_by(self.campaigns.c.created_at.desc()).limit(limit)).fetchall()
        out=[]
        for r in rows:
            d=dict(r._mapping); d["audience"]=_loads(d.pop("audience_json"),{}); d["creative"]=_loads(d.pop("creative_json"),{}); d["metadata"]=_loads(d.pop("metadata_json"),{}); out.append(d)
        return out

    def create_proposal(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        raw = "apr_" + secrets.token_urlsafe(24); now = utcnow(); expires = now + timedelta(days=int(payload.get("expires_in_days") or 14))
        row = {"id": str(uuid.uuid4()), "lead_id": payload.get("lead_id"), "title": payload["title"], "body": payload["body"],
            "amount": payload.get("amount"), "currency": payload.get("currency") or "INR", "status": "shared",
            "share_prefix": raw[:12], "share_hash": self._digest(raw), "expires_at": expires, "created_at": now, "updated_at": now}
        with self.engine.begin() as conn: conn.execute(self.proposals.insert().values(**row))
        public = {k:v for k,v in row.items() if k != "share_hash"}; return public, raw

    def list_proposals(self, limit: int = 200) -> list[dict[str, Any]]:
        cols=[c for c in self.proposals.c if c.name != "share_hash"]
        with self.engine.begin() as conn: return [dict(r._mapping) for r in conn.execute(select(*cols).order_by(self.proposals.c.created_at.desc()).limit(limit)).fetchall()]

    def shared_proposal(self, raw: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row=conn.execute(select(self.proposals).where(self.proposals.c.share_hash == self._digest(raw), self.proposals.c.expires_at >= utcnow())).fetchone()
        if not row: return None
        d=dict(row._mapping); d.pop("share_hash",None); return d

    def create_automation(self, payload: dict[str, Any]) -> dict[str, Any]:
        now=utcnow(); row={"id":str(uuid.uuid4()),"name":payload["name"],"trigger_event":payload["trigger_event"],
            "condition_json":_json(payload.get("condition") or {}),"actions_json":_json(payload.get("actions") or []),
            "enabled":bool(payload.get("enabled",True)),"created_at":now,"updated_at":now}
        with self.engine.begin() as conn: conn.execute(self.automations.insert().values(**row))
        return {**row,"condition":payload.get("condition") or {},"actions":payload.get("actions") or []}

    def list_automations(self, trigger_event: str | None = None) -> list[dict[str, Any]]:
        stmt=select(self.automations)
        if trigger_event: stmt=stmt.where(self.automations.c.trigger_event == trigger_event, self.automations.c.enabled.is_(True))
        stmt=stmt.order_by(self.automations.c.created_at.desc())
        with self.engine.begin() as conn: rows=conn.execute(stmt).fetchall()
        out=[]
        for r in rows:
            d=dict(r._mapping); d["condition"]=_loads(d.pop("condition_json"),{}); d["actions"]=_loads(d.pop("actions_json"),[]); out.append(d)
        return out

    def delete_automation(self, automation_id: str) -> bool:
        with self.engine.begin() as conn: return conn.execute(self.automations.delete().where(self.automations.c.id == automation_id)).rowcount > 0

    def record_automation_run(self, automation_id: str | None, event_type: str, status: str, result: dict[str, Any]) -> None:
        with self.engine.begin() as conn: conn.execute(self.automation_runs.insert().values(id=str(uuid.uuid4()), automation_id=automation_id,
            event_type=event_type,status=status,result_json=_json(result),created_at=utcnow()))

    def enqueue_outbox(self, *, kind: str, channel: str, recipient: str | None, payload: dict[str, Any], delay_minutes: int = 0) -> dict[str, Any]:
        row={"id":str(uuid.uuid4()),"kind":kind,"channel":channel,"recipient":recipient,"payload_json":_json(payload),"status":"queued",
             "scheduled_for":utcnow()+timedelta(minutes=max(0,int(delay_minutes))),"created_at":utcnow()}
        with self.engine.begin() as conn: conn.execute(self.outbox.insert().values(**row))
        return {**row,"payload":payload}

    def list_outbox(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.engine.begin() as conn: rows=conn.execute(select(self.outbox).order_by(self.outbox.c.scheduled_for.desc()).limit(limit)).fetchall()
        out=[]
        for r in rows:
            d=dict(r._mapping); d["payload"]=_loads(d.pop("payload_json"),{}); out.append(d)
        return out

    def growth_stats(self) -> dict[str, int]:
        with self.engine.begin() as conn:
            leads=int(conn.execute(select(func.count()).select_from(self.leads)).scalar_one())
            priority=int(conn.execute(select(func.count()).select_from(self.leads).where(self.leads.c.score >= 70)).scalar_one())
            campaigns=int(conn.execute(select(func.count()).select_from(self.campaigns)).scalar_one())
            queued=int(conn.execute(select(func.count()).select_from(self.outbox).where(self.outbox.c.status == "queued")).scalar_one())
        return {"leads":leads,"priorityLeads":priority,"campaigns":campaigns,"queuedActions":queued}

    def dashboard_stats(self) -> dict[str, int]:
        cutoff = datetime.fromtimestamp(utcnow().timestamp() - 86400, tz=timezone.utc)
        with self.engine.begin() as conn:
            active_keys = conn.execute(select(func.count()).select_from(self.api_keys).where(self.api_keys.c.revoked_at.is_(None))).scalar_one()
            requests_24h = conn.execute(select(func.count()).select_from(self.usage).where(self.usage.c.created_at >= cutoff)).scalar_one()
            tokens_24h = conn.execute(select(func.coalesce(func.sum(self.usage.c.tokens), 0)).where(self.usage.c.created_at >= cutoff)).scalar_one()
        return {"activeKeys": int(active_keys), "requests24h": int(requests_24h), "tokens24h": int(tokens_24h or 0)}
