"""
Простой in-memory кэш с TTL для горячих данных.
Избавляет от повторных запросов к удалённой Supabase PostgreSQL.
"""
import time
from typing import Any

_cache: dict[str, tuple[Any, float]] = {}


def cache_get(key: str) -> Any | None:
    """Получить значение из кэша. Возвращает None если не найдено или TTL истёк."""
    entry = _cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Записать значение в кэш с TTL в секундах (по умолчанию 5 минут)."""
    _cache[key] = (value, time.monotonic() + ttl)


def cache_invalidate(prefix: str = "") -> None:
    """Удалить записи из кэша по префиксу ключа. Без аргумента — очищает всё."""
    if not prefix:
        _cache.clear()
        return
    keys_to_remove = [k for k in _cache if k.startswith(prefix)]
    for k in keys_to_remove:
        _cache.pop(k, None)
