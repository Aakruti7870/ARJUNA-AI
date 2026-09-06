from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, status

from .config import ProviderConfig, get_settings

_SESSION_TTL_SECONDS = max(900, int(os.getenv("ARJUNA_SESSION_TTL_SECONDS", "43200")))
_EPHEMERAL_SECRET = secrets.token_bytes(32)


@dataclass
class SessionData:
    session_id: str
    display_name: str
    expires_at: int
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    previews: dict[str, str] = field(default_factory=dict)


_sessions: dict[str, SessionData] = {}


def _secret() -> bytes:
    configured = os.getenv("ARJUNA_SESSION_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")

    settings = get_settings()
    if settings.platform_api_keys and settings.platform_api_keys[0] != "dev-local-key":
        return settings.platform_api_keys[0].encode("utf-8")
    return _EPHEMERAL_SECRET


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _clean_expired() -> None:
    now = int(time.time())
    expired = [sid for sid, session in _sessions.items() if session.expires_at <= now]
    for sid in expired:
        _sessions.pop(sid, None)


def create_guest_session(display_name: str) -> tuple[str, SessionData]:
    _clean_expired()
    now = int(time.time())
    session_id = secrets.token_urlsafe(24)
    expires_at = now + _SESSION_TTL_SECONDS
    clean_name = (display_name or "Creator").strip()[:80] or "Creator"
    session = SessionData(session_id=session_id, display_name=clean_name, expires_at=expires_at)
    _sessions[session_id] = session

    payload = _b64encode(
        json.dumps(
            {"sid": session_id, "exp": expires_at},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    token = f"{payload}.{_sign(payload)}"
    return token, session


def resolve_session_token(token: str) -> SessionData:
    _clean_expired()
    try:
        payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    expected = _sign(payload)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    try:
        data = json.loads(_b64decode(payload))
        session_id = str(data["sid"])
        expires_at = int(data["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    if expires_at <= int(time.time()):
        _sessions.pop(session_id, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session unavailable")
    return session


def require_session(authorization: str | None = Header(default=None)) -> SessionData:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session required")
    return resolve_session_token(authorization[7:].strip())


def get_preview(preview_id: str) -> str | None:
    _clean_expired()
    for session in _sessions.values():
        preview = session.previews.get(preview_id)
        if preview is not None:
            return preview
    return None


def session_ttl_seconds() -> int:
    return _SESSION_TTL_SECONDS
