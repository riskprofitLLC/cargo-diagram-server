"""Предварительный анализ выполнимости (задача 3.0б), зависит от режима цели:
fit_all → ранний отказ с причиной; max_fit → груз в unplaced[] с причиной.

Дополнительно проверяется матрица «груз→вагон» (задача 1.9): категория груза
(`category` во входе, по умолчанию тарно-штучный) должна допускать вагон.
"""
import json
import os

from schemas.models import GoalMode

MATRIX = os.path.join(os.path.dirname(__file__), "..", "data", "wagon_matrix.json")


def load_matrix() -> dict:
    with open(MATRIX, encoding="utf-8") as f:
        return json.load(f)


def wagon_allowed(items: list[dict], wagon: dict) -> tuple[bool, str]:
    """Матрица «груз→вагон» (1.9): допускает ли матрица эти категории в вагоне."""
    matrix = load_matrix()
    wagon_type = wagon.get("type", "covered")
    for it in items:
        category = it.get("category", "tarno-shtuchny")
        entry = matrix["categories"].get(category)
        if entry is None:
            return False, f"категория груза {category!r} отсутствует в матрице «груз→вагон»"
        if wagon_type not in entry["allowed_wagons"]:
            return False, (f"категория {category!r} не допускается в вагон типа {wagon_type!r} "
                           f"(матрица «груз→вагон», источник: {entry['source']})")
    return True, ""


def precheck(items: list[dict], wagon: dict) -> dict:
    """Грубые оценки: объём комплекта vs объём вагона, масса vs грузоподъёмность.

    Возвращает {"feasible": bool, "reason": str, "overload": {...}}.
    """
    V = wagon["inner"]["length"] * wagon["inner"]["width"] * wagon["inner"]["height"]
    vol = sum(it["length"] * it["width"] * it["height"] * it["quantity"] for it in items)
    mass_kg = sum(it["mass"] * it["quantity"] for it in items)
    payload_kg = wagon["payload_t"] * 1000
    out = {"feasible": True, "reason": "", "overload": {}}
    reasons = []
    if vol > V:
        reasons.append("объём комплекта превышает объём вагона")
        out["overload"]["volume"] = {"required": vol, "available": V}
    if mass_kg > payload_kg:
        reasons.append("масса комплекта превышает грузоподъёмность")
        out["overload"]["mass"] = {"required": mass_kg, "available": payload_kg}
    allowed, why = wagon_allowed(items, wagon)
    if not allowed:
        reasons.append(why)
    if reasons:
        out["feasible"] = False
        out["reason"] = "; ".join(reasons)
    return out


def apply_goal_mode(pre: dict, goal: GoalMode) -> str | None:
    """fit_all: infeasible → FAILED; max_fit: продолжаем (грузы уйдут в unplaced)."""
    if pre["feasible"]:
        return None
    return "FAILED" if goal == GoalMode.FIT_ALL else None
