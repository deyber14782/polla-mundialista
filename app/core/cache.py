"""
Caché en memoria con TTL para evitar lecturas repetidas a Firestore.
"""
import time

_cache: dict[str, dict] = {}


def get(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > entry["ttl"]:
        del _cache[key]
        return None
    return entry["data"]


def set(key: str, data, ttl: int = 300):
    """ttl en segundos (default 5 min)"""
    _cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}


def invalidate(*keys: str):
    if not keys:
        _cache.clear()
    else:
        for k in keys:
            _cache.pop(k, None)