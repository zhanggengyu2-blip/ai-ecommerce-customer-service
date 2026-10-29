import threading
import time
from fastapi import HTTPException

_lock = threading.Lock()
_windows: dict[str, tuple[int, float]] = {}


def check_rate_limit(key: str, limit: int, window_seconds: int):
    """Fixed-window guard for this single-process first release."""
    now = time.monotonic()
    with _lock:
        count, expires = _windows.get(key, (0, now + window_seconds))
        if now >= expires:
            count, expires = 0, now + window_seconds
        if count >= limit:
            raise HTTPException(429, "Rate limit exceeded")
        _windows[key] = (count + 1, expires)
        if len(_windows) > 10000:
            for stale in [item for item, (_, deadline) in _windows.items() if deadline <= now]:
                del _windows[stale]
