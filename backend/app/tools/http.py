import threading
import time

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_session = requests.Session()
_session.headers["User-Agent"] = "healthcare-briefing-demo/0.1"


class RateLimiter:
    """Enforces a minimum interval between calls across all threads."""

    def __init__(self, min_interval_s: float) -> None:
        self._min_interval = min_interval_s
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._last + self._min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def get(url: str, params: dict, *, limiter: RateLimiter | None = None, retries: int = 3, timeout: float = 30) -> requests.Response:
    for attempt in range(retries + 1):
        if limiter:
            limiter.wait()
        resp = _session.get(url, params=params, timeout=timeout)
        if resp.status_code in RETRYABLE_STATUS and attempt < retries:
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else 2**attempt)
            continue
        resp.raise_for_status()
        return resp
    raise AssertionError("unreachable")
