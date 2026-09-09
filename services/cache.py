import time
from hashlib import sha256

_CACHE: dict[str, tuple[float, object]] = {}


def key(prefix: str, value: str) -> str:
    return prefix + ":" + sha256(value.strip().lower().encode()).hexdigest()


def get(cache_key: str, ttl: int):
    item = _CACHE.get(cache_key)
    if not item:
        return None
    created, value = item
    if time.time() - created > ttl:
        _CACHE.pop(cache_key, None)
        return None
    return value


def put(cache_key: str, value):
    _CACHE[cache_key] = (time.time(), value)
