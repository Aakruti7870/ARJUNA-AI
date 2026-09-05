from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_platform_key(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not any(hmac.compare_digest(token, allowed) for allowed in settings.platform_api_keys):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid platform API key")
