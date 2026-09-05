from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self.buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.buckets[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


@dataclass(frozen=True)
class SessionData:
    email: str
    csrf: str


class SessionManager:
    def __init__(self, secret: str, max_age_seconds: int = 43200):
        self.serializer = URLSafeTimedSerializer(secret, salt="arjuna-console")
        self.max_age = max_age_seconds

    def issue(self, email: str) -> tuple[str, SessionData]:
        data = SessionData(email=email, csrf=secrets.token_urlsafe(24))
        token = self.serializer.dumps({"email": data.email, "csrf": data.csrf})
        return token, data

    def read(self, token: str | None) -> SessionData | None:
        if not token:
            return None
        try:
            payload = self.serializer.loads(token, max_age=self.max_age)
        except (BadSignature, SignatureExpired):
            return None
        email = str(payload.get("email", ""))
        csrf = str(payload.get("csrf", ""))
        if not email or not csrf:
            return None
        return SessionData(email=email, csrf=csrf)


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
