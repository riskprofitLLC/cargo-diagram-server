"""Лимиты входа и ретеншн артефактов (задача 4.7, ADR-012).

Лимиты — конфиг (происхождение: РЕШЕНИЕ ВЛАДЕЛЬЦА, архитектор).
Ретеншн: файлы PDF/DXF в /tmp чистятся по TTL.
"""
import os
import threading
import time

MAX_ITEMS_TYPES = int(os.environ.get("MAX_ITEM_TYPES", "50"))       # типов в запросе
MAX_TOTAL_ITEMS = int(os.environ.get("MAX_TOTAL_ITEMS", "10000"))   # всего мест
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(2 * 1024 * 1024)))  # 2 МБ
ARTIFACT_TTL_S = int(os.environ.get("ARTIFACT_TTL_S", str(24 * 3600)))        # 24 ч
ARTIFACT_DIR = os.environ.get("ARTIFACT_DIR", "/tmp")
# Rate limit по API-ключу (4.5, простой скользящий окно): запросов в минуту
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))

_rl_lock = threading.Lock()
_rl_hits: dict[str, list[float]] = {}  # key_hash -> [timestamps]


def check_rate_limit(key_hash: str) -> str | None:
    """None — можно, иначе текст ошибки (HTTP 429). Лимит читается на каждый вызов."""
    limit = int(os.environ.get("RATE_LIMIT_PER_MIN", str(RATE_LIMIT_PER_MIN)))
    now = time.time()
    with _rl_lock:
        hits = [t for t in _rl_hits.get(key_hash, []) if now - t < 60]
        if len(hits) >= limit:
            _rl_hits[key_hash] = hits
            return f"превышен лимит запросов: {limit}/мин"
        hits.append(now)
        _rl_hits[key_hash] = hits
        if len(_rl_hits) > 10000:  # защита от роста словаря
            _rl_hits.clear()
    return None


def check_request_limits(req) -> str | None:
    """Возвращает текст ошибки или None."""
    if len(req.items) > MAX_ITEMS_TYPES:
        return f"слишком много типов грузов: {len(req.items)} > {MAX_ITEMS_TYPES}"
    total = sum(it.quantity for it in req.items)
    if total > MAX_TOTAL_ITEMS:
        return f"слишком много мест: {total} > {MAX_TOTAL_ITEMS}"
    for it in req.items:
        if it.length * it.width * it.height <= 0:
            return "нулевой габарит груза"
    return None


def cleanup_artifacts(now: float | None = None) -> int:
    """Удаляет артефакты старше TTL. Возвращает число удалённых файлов."""
    now = now or time.time()
    removed = 0
    for f in os.listdir(ARTIFACT_DIR):
        if f.startswith("plan-") and (f.endswith(".pdf") or f.endswith(".dxf")):
            path = os.path.join(ARTIFACT_DIR, f)
            if now - os.path.getmtime(path) > ARTIFACT_TTL_S:
                os.remove(path)
                removed += 1
    return removed
