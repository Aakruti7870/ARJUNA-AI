from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

from sqlalchemy import DateTime, Integer, MetaData, String, Table, Column, create_engine, func, select, update
from sqlalchemy.engine import Engine


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Storage:
    def __init__(self, database_url: str, hash_secret: str):
        if database_url.startswith("sqlite:///./"):
            db_path = Path(database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.hash_secret = hash_secret.encode("utf-8")
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
            Column("model", String(200), nullable=False),
            Column("tokens", Integer, nullable=True),
            Column("latency_ms", Integer, nullable=False),
            Column("status", String(20), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, index=True),
        )
        self.meta.create_all(self.engine)

    def _digest(self, raw: str) -> str:
        return hmac.new(self.hash_secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_api_key(self, name: str) -> tuple[dict[str, Any], str]:
        raw = "arjuna_live_" + secrets.token_urlsafe(32)
        row = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "prefix": raw[:18],
            "key_hash": self._digest(raw),
            "created_at": utcnow(),
            "last_used_at": None,
            "revoked_at": None,
        }
        with self.engine.begin() as conn:
            conn.execute(self.api_keys.insert().values(**row))
        public = {k: row[k] for k in ("id", "name", "prefix", "created_at", "last_used_at", "revoked_at")}
        return public, raw

    def list_api_keys(self) -> list[dict[str, Any]]:
        stmt = select(
            self.api_keys.c.id, self.api_keys.c.name, self.api_keys.c.prefix,
            self.api_keys.c.created_at, self.api_keys.c.last_used_at, self.api_keys.c.revoked_at,
        ).order_by(self.api_keys.c.created_at.desc())
        with self.engine.begin() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def verify_api_key(self, raw: str) -> dict[str, Any] | None:
        digest = self._digest(raw)
        stmt = select(self.api_keys).where(self.api_keys.c.key_hash == digest, self.api_keys.c.revoked_at.is_(None))
        with self.engine.begin() as conn:
            row = conn.execute(stmt).fetchone()
            if not row:
                return None
            conn.execute(update(self.api_keys).where(self.api_keys.c.id == row.id).values(last_used_at=utcnow()))
            return dict(row._mapping)

    def revoke_api_key(self, key_id: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                update(self.api_keys)
                .where(self.api_keys.c.id == key_id, self.api_keys.c.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            return result.rowcount > 0

    def record_usage(self, *, api_key_id: str | None, provider: str, model: str,
                     tokens: int | None, latency_ms: int, status: str = "ok") -> None:
        with self.engine.begin() as conn:
            conn.execute(self.usage.insert().values(
                id=str(uuid.uuid4()), api_key_id=api_key_id, provider=provider, model=model,
                tokens=tokens, latency_ms=latency_ms, status=status, created_at=utcnow(),
            ))

    def recent_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        stmt = select(self.usage).order_by(self.usage.c.created_at.desc()).limit(limit)
        with self.engine.begin() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def dashboard_stats(self) -> dict[str, int]:
        now = utcnow()
        day_ago = now.timestamp() - 86400
        cutoff = datetime.fromtimestamp(day_ago, tz=timezone.utc)
        with self.engine.begin() as conn:
            active_keys = conn.execute(
                select(func.count()).select_from(self.api_keys).where(self.api_keys.c.revoked_at.is_(None))
            ).scalar_one()
            requests_24h = conn.execute(
                select(func.count()).select_from(self.usage).where(self.usage.c.created_at >= cutoff)
            ).scalar_one()
            tokens_24h = conn.execute(
                select(func.coalesce(func.sum(self.usage.c.tokens), 0)).where(self.usage.c.created_at >= cutoff)
            ).scalar_one()
        return {"activeKeys": int(active_keys), "requests24h": int(requests_24h), "tokens24h": int(tokens_24h or 0)}
