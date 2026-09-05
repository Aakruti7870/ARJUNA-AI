from app.security import SessionManager, SlidingWindowLimiter


def test_session_round_trip():
    manager = SessionManager("a"*40)
    token, created = manager.issue("admin@example.com")
    read = manager.read(token)
    assert read and read.email == created.email and read.csrf == created.csrf


def test_rate_limit():
    limiter = SlidingWindowLimiter(2, window_seconds=60)
    assert limiter.allow("key")
    assert limiter.allow("key")
    assert not limiter.allow("key")
