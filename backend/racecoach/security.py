from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from threading import Lock


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000)
    return f"pbkdf2${salt}${value.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


class LoginLimiter:
    def __init__(self):
        self.attempts = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        with self.lock:
            now = time.monotonic()
            queue = self.attempts[key]
            while queue and queue[0] < now - 300:
                queue.popleft()
            if len(queue) >= 15:
                return False
            queue.append(now)
            # Bound the process-local map; single-host MVP, not a distributed limiter.
            if len(self.attempts) > 10000:
                for old in list(self.attempts)[:5000]:
                    if old != key:
                        del self.attempts[old]
            return True


def new_token() -> str:
    return secrets.token_urlsafe(32)
