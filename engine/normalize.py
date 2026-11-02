"""Нормализация входа (ADR-001, задача 3.0а): целые мм, округление вверх для
габаритов грузов, вниз для внутренних размеров вагона."""
import math


def ceil_mm(v: float) -> int:
    return math.ceil(v)


def floor_mm(v: float) -> int:
    return math.floor(v)


def normalize_request(req) -> dict:
    """Возвращает нормализованный вход: wagon + список грузов (мм/кг)."""
    return {
        "wagon_id": req.wagon_id,
        "items": [
            {
                "type_id": it.type_id,
                "length": ceil_mm(it.length),
                "width": ceil_mm(it.width),
                "height": ceil_mm(it.height),
                "mass": ceil_mm(it.mass),
                "quantity": it.quantity,
                "stackable": it.stackable,
                "is_package": it.is_package,
                "max_load_on_top": it.max_load_on_top,
                "allowed_orientations": it.allowed_orientations,
            }
            for it in req.items
        ],
        "goal": req.goal.value,
        "completeness_field": req.completeness_field,
        "seed": req.seed,
        "time_limit_s": req.time_limit_s,
    }
