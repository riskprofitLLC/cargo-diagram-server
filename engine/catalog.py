"""L0 — каталог типовых схем (задачи 1.7/3.1): подбор схемы по условиям применимости.

Схема (data/schemes/*.json) задаёт условия применимости и параметры раскладки;
`match_scheme` выбирает наиболее специфичную подходящую схему, `None` — нет
типовой схемы, работает L1/L2.
"""
import json
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "schemes")


def load_schemes() -> list[dict]:
    out = []
    for f in sorted(os.listdir(DATA)):
        if f.endswith(".json"):
            with open(os.path.join(DATA, f), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def applicable(scheme: dict, wagon: dict, items: list[dict]) -> bool:
    """Проверка условий применимости схемы."""
    app = scheme.get("applicability") or {}
    if app.get("wagon_type") and app["wagon_type"] != wagon.get("type"):
        return False
    if app.get("door_center") and (wagon.get("door") or {}).get("position") != "center_side":
        return False
    if app.get("packages") and not all(it.get("is_package") for it in items):
        # признака «транспортный пакет» во входном контракте пока нет (задача 1.2/1.7)
        return False
    if app.get("two_layers"):
        height = wagon["inner"]["height"]
        if not any(it.get("stackable", True) and 2 * it["height"] <= height for it in items):
            return False
    return True


def match_scheme(wagon: dict, items: list[dict]) -> dict | None:
    """Наиболее специфичная подходящая схема (по числу условий) или None."""
    candidates = [s for s in load_schemes() if applicable(s, wagon, items)]
    if not candidates:
        return None
    return max(sorted(candidates, key=lambda s: s["scheme_id"]),
               key=lambda s: len(s.get("applicability") or {}))
