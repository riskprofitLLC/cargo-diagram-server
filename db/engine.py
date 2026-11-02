"""Единая фабрика движков (задача 4.3): пул соединений переиспользуется,
движок на каждый вызов не создаётся."""
import os
from functools import lru_cache

from sqlalchemy import create_engine


@lru_cache(maxsize=8)
def _engine_for_url(url: str):
    return create_engine(url)


def get_engine():
    """Движок по DATABASE_URL или None (режим без БД — JSON-фолбэк)."""
    url = os.environ.get("DATABASE_URL")
    return _engine_for_url(url) if url else None
