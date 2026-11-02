"""Сид БД из data/*.json (задачи 1.4/1.5/1.6/1.7): вагоны, схемы, нормы."""
import json
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Wagon, Scheme, NormTable

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed(engine) -> None:
    with Session(engine) as s:
        for f in sorted(os.listdir(os.path.join(DATA, "wagons"))):
            if f.endswith(".json"):
                d = _load(os.path.join(DATA, "wagons", f))
                s.merge(Wagon(wagon_id=d["wagon_id"], type=d["type"], data=d, source=d.get("source", "")))
        for f in sorted(os.listdir(os.path.join(DATA, "schemes"))):
            if f.endswith(".json"):
                d = _load(os.path.join(DATA, "schemes", f))
                s.merge(Scheme(scheme_id=d["scheme_id"], name=d["name"], data=d, source=d.get("source", "")))
        d = _load(os.path.join(DATA, "norms", "tu_cm943.json"))
        s.merge(NormTable(doc=d["doc"], data=d))
        s.commit()


if __name__ == "__main__":
    seed(create_engine(os.environ["DATABASE_URL"]))
