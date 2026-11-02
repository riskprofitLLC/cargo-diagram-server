"""Репозиторий чтения сид-данных из БД (fallback на JSON при пустой БД)."""
import json
import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.engine import get_engine
from db.models import Wagon, Scheme

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
WAGON_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

_engine = get_engine


def wagon_path(wagon_id: str) -> str:
    """Путь к сид-файлу вагона; некорректный id отвергается (обход пути)."""
    if not WAGON_ID_RE.match(wagon_id):
        raise ValueError(f"некорректный wagon_id: {wagon_id!r}")
    return os.path.join(DATA, "wagons", f"{wagon_id}.json")


def load_wagon(wagon_id: str) -> dict:
    eng = _engine()
    if eng:
        try:
            with Session(eng) as s:
                w = s.get(Wagon, wagon_id)
                if w:
                    return w.data
        except Exception:
            pass  # БД недоступна — fallback на JSON
    with open(wagon_path(wagon_id), encoding="utf-8") as f:
        return json.load(f)


def load_schemes() -> list[dict]:
    eng = _engine()
    if eng:
        try:
            with Session(eng) as s:
                rows = s.scalars(select(Scheme)).all()
                if rows:
                    return [r.data for r in rows]
        except Exception:
            pass
    out = []
    d = os.path.join(DATA, "schemes")
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out
