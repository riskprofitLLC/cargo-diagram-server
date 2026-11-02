"""Repair loop (задача 3.7): каталог кодов §5.1 плана, защита хэшем состояния."""

CATALOG = {
    "ЦТ_ТЕЛЕЖКИ": "перестановка слоёв/типов (балансировка), макс. 3 итерации",
    "ВЫСОТА_ЦТ_ПРЕВЫШЕНА": "перестановка тяжёлого вниз",
    "ЗАЗОР_ТРЕБУЕТ_КРЕПЛЕНИЯ": "распорная рама / перестановка мест",
    "ПЕРЕГРУЗ_МАССА": "исключение мест из кандидата",
    "ШТАБЕЛИРОВАНИЕ_НАРУШЕНО": "снятие верхнего места нагруженного штабеля (гл. 11 п. 1.15)",
    "КОСОСИММЕТРИЯ": "не repair: пара мест кососимметрична — выравнивание масс (п. 6.3.6)",
    "НЕ_ВМЕЩАЕТСЯ": "не repair: отказ режима «вместить всё»",
    "SUPPORT_VIOLATION": "кандидат отброшен, возврат к L1",
    "OVERLAP": "кандидат отброшен, возврат к L1",
    "OUT_OF_BOUNDS": "кандидат отброшен, возврат к L1",
}


def state_hash(placed: list[dict]) -> int:
    return hash(tuple(sorted((p["x"], p["y"], p["z"], p["type_id"]) for p in placed)))


def balance(placed: list[dict], wagon: dict) -> list[dict]:
    """Центрирование раскладки по МАССЕ (не по габаритной рамке): приводит общий ЦТ
    к середине вагона — repair кодов ЦТ_ПОПЕРЕЧНОЕ / ЦТ_ПРОДОЛЬНОЕ / ЦТ_ТЕЛЕЖКИ (§5.1)."""
    if not placed:
        return placed
    L, W = wagon["inner"]["length"], wagon["inner"]["width"]
    total = sum(p.get("mass") or 0 for p in placed)
    if total <= 0:
        # масса неизвестна — центрируем по габаритной рамке (прежнее поведение)
        dx = int((L - max(p["x"] + p["length"] for p in placed)) / 2)
        dy = int((W - max(p["y"] + p["width"] for p in placed)) / 2)
        return [{**p, "x": p["x"] + dx, "y": p["y"] + dy} for p in placed]
    cx = sum((p.get("mass") or 0) * (p["x"] + p["length"] / 2) for p in placed) / total
    cy = sum((p.get("mass") or 0) * (p["y"] + p["width"] / 2) for p in placed) / total
    min_x, max_x = min(p["x"] for p in placed), max(p["x"] + p["length"] for p in placed)
    min_y, max_y = min(p["y"] for p in placed), max(p["y"] + p["width"] for p in placed)
    dx = max(-min_x, min(int(round(L / 2 - cx)), L - max_x))
    dy = max(-min_y, min(int(round(W / 2 - cy)), W - max_y))
    return [{**p, "x": p["x"] + dx, "y": p["y"] + dy} for p in placed]


def drop_top_of_stack(placed: list[dict], items_meta: dict, wagon: dict) -> list[dict] | None:
    """ШТАБЕЛИРОВАНИЕ_НАРУШЕНО: снимаем верхнее место самого нагруженного штабеля."""
    if not placed:
        return None
    worst, worst_load = None, -1.0
    for p in placed:
        above = [o for o in placed if o is not p and o["z"] >= p["z"] + p["height"]
                 and o["x"] < p["x"] + p["length"] and p["x"] < o["x"] + o["length"]
                 and o["y"] < p["y"] + p["width"] and p["y"] < o["y"] + o["width"]]
        if not above:
            continue
        load = sum((items_meta.get(o["type_id"]) or {}).get("mass", 0) or o.get("mass") or 0 for o in above)
        if load > worst_load:
            worst, worst_load = max(above, key=lambda o: o["z"]), load
    if worst is None:
        return None
    return [p for p in placed if p is not worst]


def repair(violations: list, placed: list[dict], seen: set[int], wagon: dict | None = None,
           items_meta: dict | None = None) -> list[dict] | None:
    """Возвращает новый кандидат или None (неремонтируемо/повтор состояния)."""
    h = state_hash(placed)
    if h in seen:
        return None
    seen.add(h)
    codes = {v.code for v in violations}
    if codes & {"OVERLAP", "OUT_OF_BOUNDS", "SUPPORT_VIOLATION"}:
        return None  # кандидат L1/L2 невалиден — откат, не ремонт
    if "ПЕРЕГРУЗ_МАССА" in codes:
        # снимаем самый тяжёлый груз
        return sorted(placed, key=lambda p: p.get("mass", 0))[:-1] if placed else None
    if "ШТАБЕЛИРОВАНИЕ_НАРУШЕНО" in codes:
        return drop_top_of_stack(placed, items_meta or {}, wagon or {})
    if codes & {"ЦТ_ПОПЕРЕЧНОЕ", "ЦТ_ПРОДОЛЬНОЕ", "ЦТ_ТЕЛЕЖКИ"} and wagon is not None:
        return balance(placed, wagon)
    return placed  # прочие коды покрываются гейтом 2/нормативом
