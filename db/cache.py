"""Кэш расчётов в БД (задача 4.3): SUCCESS/PARTIALLY_PLACED кэшируются,
при попадании — ревалидация гейтом 1; TIMEOUT/ERROR не кэшируются."""
import datetime
import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.engine import get_engine
from db.models import PlanRow, CalcCache
from schemas.models import Plan, resolve_dims

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

_engine = get_engine


def _item_meta() -> dict[str, dict]:
    with open(os.path.join(DATA, "cargo_types.json"), encoding="utf-8") as f:
        return {t["type_id"]: t for t in json.load(f)["types"]}


def get(cache_key: str, wagon_loader=None):
    """Валидный план из кэша (с ревалидацией гейтом 1) или None."""
    eng = _engine()
    if not eng:
        return None
    with Session(eng) as s:
        pid = s.scalars(select(CalcCache.plan_id).where(CalcCache.cache_key == cache_key)).first()
        if not pid:
            return None
        row = s.get(PlanRow, pid)
        if not row:
            return None
    plan = Plan.model_validate(row.payload)
    # ревалидация гейтом 1 (4.3)
    if wagon_loader is not None:
        from engine.validator import validate_gate1
        wagon = wagon_loader(plan.wagon_id)
        meta = _item_meta()
        placed = []
        for p in plan.placed:
            dims = resolve_dims(p, meta)
            if dims is None:
                return None  # габаритов нет — проверить нельзя, кэш недействителен
            placed.append(p.model_dump() | {"length": dims[0], "width": dims[1], "height": dims[2]})
        g, _ = validate_gate1(placed, meta, wagon, wagon["payload_t"])
        if g.value != "PASSED":
            return None  # кэш протух → пересчёт
    return plan


def put(cache_key: str, plan) -> None:
    eng = _engine()
    if not eng:
        return
    with Session(eng) as s:
        s.merge(CalcCache(cache_key=cache_key, plan_id=plan.plan_id,
                          created=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        s.commit()
