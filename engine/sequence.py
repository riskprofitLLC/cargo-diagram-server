"""Порядок погрузки (задача 3.5): от торцов к дверному проёму, нумерация 1..N.

Достижимость: груз должен пройти через дверной проём — его габарит
(по ширине проёма и высоте) не больше проёма; иначе — структурированный отказ.
"""
from schemas.models import PlacedItem, FailureReason


def door_clearance(placed: list[dict], wagon: dict) -> list[FailureReason]:
    """Каждый груз должен пройти через дверь: min(width, height) груза ≤ проёму."""
    door_w = wagon.get("door", {}).get("width", 0)
    door_h = wagon.get("door", {}).get("height", 0)
    out = []
    for p in placed:
        gw, gh = p["width"], p["height"]
        # проходит, если влезает в проём хотя бы одной ориентацией (width×height)
        if not (gw <= door_w and gh <= door_h) and not (gh <= door_w and gw <= door_h):
            out.append(FailureReason(code="МЕСТО_ЗАБЛОКИРОВАНО", objects=[p["type_id"]],
                                     value=float(min(gw, gh))))
    return out


def build_sequence(placed: list[dict], wagon: dict) -> list[PlacedItem]:
    """Сортировка: сначала дальние от двери (по |x - центр двери| по убыванию),
    затем по z (снизу вверх). Дверь — посередине борта, ось X вдоль вагона."""
    L = wagon["inner"]["length"]
    door_center = L / 2
    ordered = sorted(placed, key=lambda p: (-abs(p["x"] + p["length"] / 2 - door_center), p["z"], p["y"]))
    return [
        PlacedItem(type_id=p["type_id"], index=i + 1, x=p["x"], y=p["y"], z=p["z"],
                   orientation=p.get("orientation", "xyz"),
                   length=p.get("length"), width=p.get("width"),
                   height=p.get("height"), mass=p.get("mass"))
        for i, p in enumerate(ordered)
    ]
