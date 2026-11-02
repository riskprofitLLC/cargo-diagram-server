"""Габариты места для экспортов (задачи 5.1/5.2): план самодостаточен (ADR-016),
справочник типоразмеров — только фолбэк для планов старого формата."""
import json
import os

from schemas.models import PlacedItem, resolve_dims

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def load_disclaimer() -> tuple[str, str]:
    """(полный, краткий) текст дисклеймера МТУ/НТУ из сид-данных (задача 1.6б)."""
    with open(os.path.join(DATA, "norms", "mtu_ntu.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data["disclaimer"], data["short_disclaimer"]


def load_cargo_types() -> dict[str, dict]:
    """Справочник типоразмеров (фолбэк, если план не несёт габаритов)."""
    with open(os.path.join(DATA, "cargo_types.json"), encoding="utf-8") as f:
        return {t["type_id"]: t for t in json.load(f)["types"]}


def placed_dims(item: PlacedItem, types: dict[str, dict]) -> tuple[int, int, int] | None:
    """Габариты места: из плана, иначе из справочника; None — неизвестны."""
    return resolve_dims(item, types)
