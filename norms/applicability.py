"""Области применимости правил норм (задача 2.2): правило применяется только
в своей области; неприменённое правило — NOT_CHECKED, а не PASSED."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    applies_if: str  # условие применимости
    check: str      # что проверяем


RULES = [
    Rule("CT_LONG", "всегда", "продольное смещение ЦТ ≤ табл. 10"),
    Rule("CT_LAT", "всегда", "поперечное смещение ЦТ ≤ табл. 11"),
    # табл. 18 гл. 10 дана только для полувагонов и платформ; гл. 11 (крытые вагоны)
    # требования по высоте ЦТ не устанавливает (ADR-018)
    Rule("CT_HEIGHT", "открытый ПС (полувагон, платформа)", "высота ЦТ вагона с грузом ≤ 2300 мм над УГР"),
    Rule("GAP", "загружен крытый вагон", "зазоры по ширине в сумме ≤ 200 мм или крепление"),
    Rule("BOGIE_DIFF", "4-осный вагон", "разность нагрузок на тележки ≤ 10 т (РЕШЕНИЕ ВЛАДЕЛЬЦА)"),
    Rule("FORKLIFT", "погрузка погрузчиком", "18/22 кН на колесо (ГОСТ 22235-2023)"),
]


def applicable_rules(wagon_type: str, loading: str = "forklift") -> list[Rule]:
    out = []
    for r in RULES:
        if r.code == "GAP" and wagon_type != "covered":
            continue
        if r.code == "CT_HEIGHT" and wagon_type == "covered":
            continue  # гл. 11 такого требования не содержит (ADR-018)
        if r.code == "FORKLIFT" and loading != "forklift":
            continue
        out.append(r)
    return out
