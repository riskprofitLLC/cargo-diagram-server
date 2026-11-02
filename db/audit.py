"""Аудит-трейл (задача 4.6): запись расчётов в БД (кто/что/когда/версии)."""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.engine import get_engine
from db.models import PlanRow

_engine = get_engine


def record_plan(plan, owner_key: str = "") -> None:
    try:
        eng = _engine()
    except Exception:
        return  # БД недоступна — пропускаем (in-memory режим)
    if not eng:
        return
    try:
        with Session(eng) as s:
            s.merge(PlanRow(
                plan_id=plan.plan_id,
                wagon_id=plan.wagon_id,
                owner_key=owner_key,
                payload=plan.model_dump(mode="json"),
                created=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ))
            s.commit()
    except Exception:
        pass  # аудит не должен ронять расчёт (FK на wagons при несовпавшем сиде и т.п.)


def list_plans(owner_key: str | None = None) -> list[dict]:
    eng = _engine()
    if not eng:
        return []
    with Session(eng) as s:
        q = select(PlanRow)
        if owner_key:
            q = q.where(PlanRow.owner_key == owner_key)
        return [
            {"plan_id": r.plan_id, "wagon_id": r.wagon_id, "created": r.created,
             "result_status": r.payload.get("result_status")}
            for r in s.scalars(q).all()
        ]
