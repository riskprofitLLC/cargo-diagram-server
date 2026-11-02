"""Auth по API-ключу (задача 4.5): хэши ключей, простая модель владения.

MVP: ключи хранятся в переменной окружения API_KEYS (sha256 hex через запятую).
"""
import hashlib
import hmac
import os

from fastapi import Header, HTTPException


def _keys() -> set[str]:
    return {k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()}


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key:
        raise HTTPException(401, "нужен X-API-Key")
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    if not any(hmac.compare_digest(digest, k) for k in _keys()):
        raise HTTPException(403, "неверный ключ")
    return digest
