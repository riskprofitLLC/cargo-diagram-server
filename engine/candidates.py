"""Генератор кандидатов (задача 3.0г): L0 (каталог) и L1 идут параллельно,
к валидатору — оба, выбирается лучший проверенный (не первый)."""
import concurrent.futures
import os

from schemas.models import GateStatus, SolverStatus
from engine.adapter import solve_l1
from engine.catalog import match_scheme
from engine.validator import validate_gate1


def solve_l0(wagon: dict, items: list[dict], scheme: dict | None = None) -> list[dict]:
    """L0: типовая схема из каталога (задачи 1.7/3.1) — столбцами от торца.

    Столбец (одна позиция по X) заполняется рядами по ширине вагона; число ярусов
    берётся из схемы (`pattern.layers`, по умолчанию 1) и ограничено высотой
    кузова и штабелируемостью груза. Всего мест по типу — не больше заказанного.
    """
    pattern = (scheme or {}).get("pattern") or {}
    layers = max(1, int(pattern.get("layers", 1)))
    placed = []
    L, W, H = wagon["inner"]["length"], wagon["inner"]["width"], wagon["inner"]["height"]
    x = 0
    for it in items:
        ln, w, h = it["length"], it["width"], it["height"]
        per_column = W // w if w > 0 else 0
        if ln <= 0 or h <= 0 or per_column < 1:
            continue  # тип не помещается по габаритам вагона
        tiers = layers if it.get("stackable", True) and layers * h <= H else 1
        slots = [(row * w, level * h) for level in range(tiers) for row in range(per_column)]
        alternation = pattern.get("row_alternation") or {}
        gap = W - per_column * w
        column = 0
        remaining = it["quantity"]
        while remaining > 0 and x + ln <= L:
            take = min(remaining, len(slots))
            # гл. 11 п. 3.1: при зазорах 200–400 мм ряды чередуют (в чётных столбцах
            # прижимают к противоположной стенке), чтобы зазоры были «примерно одинаковые»
            offset = gap if (alternation and column % 2 == 1
                             and alternation["min_gap_mm"] < gap <= alternation["max_gap_mm"]) else 0
            for y, z in slots[:take]:
                placed.append({**it, "x": x, "y": y + offset, "z": z})
            remaining -= take
            x += ln
            column += 1
    return placed


# число потоков на параллельные кандидаты (лимит потоков воркера, 4.4)
MAX_CANDIDATE_THREADS = max(1, int(os.environ.get("SOLVER_MAX_THREADS", "4")))


def generate_candidates(wagon: dict, items: list[dict], time_limit_s: int, seed: int) -> dict:
    """Возвращает {"L0": {...}, "L1": {...}} — параллельно, со статусом модели."""
    scheme = match_scheme(wagon, items)  # 1.7/3.1: типовая схема гл. 11, если применима
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, MAX_CANDIDATE_THREADS)) as ex:
        f0 = ex.submit(solve_l0, wagon, items, scheme)
        f1 = ex.submit(solve_l1, wagon, items, time_limit_s, seed)
        l1 = f1.result()
        return {
            # L0 — каталог, не модель оптимизации (ADR-003а: NOT_APPLICABLE)
            "L0": {"placed": f0.result(), "solver_status": SolverStatus.NOT_APPLICABLE},
            "L1": {"placed": l1["placed"], "solver_status": SolverStatus(l1["solver_status"])},
        }


def pick_best(candidates: dict, items_meta: dict, wagon: dict) -> tuple[str, list[dict], SolverStatus]:
    """Выбирает кандидата с высшим числом размещённых после гейта 1."""
    best, best_n = None, -1
    for src, cand in candidates.items():
        g, _ = validate_gate1(cand["placed"], items_meta, wagon, wagon["payload_t"])
        n = len(cand["placed"]) if g == GateStatus.PASSED else -1
        if n > best_n:
            best, best_n = src, n
    if best is None:
        best = "L1"  # все кандидаты невалидны — берём L1, repair/отказ дальше
    return best, candidates[best]["placed"], candidates[best]["solver_status"]
