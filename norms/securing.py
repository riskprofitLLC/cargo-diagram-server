"""Крепление (задача 2.5): методика ЦМ-943 — гл. 10 (силы) и гл. 11 (крытые вагоны).

Путь A (`compute_fastening`): считает зазоры (гл. 11 п. 3.1, п. 1.13) и силы
(гл. 10 пп. 10.2, 10.3), формирует ведомость средств крепления по гл. 11
(распорная рама п. 2.8, доски ограждения двери п. 1.12, заполнение зазоров п. 1.14).

Путь B (`check_fastening`): независимо пересчитывает потребность в удержании
(через массу и смещение ЦТ) и проверяет, что ведомость её закрывает и что средство
геометрически разместимо. Несущая способность средств (число гвоздей, скоб,
сечения) — задача 1.6в/2.5+, здесь же силы считаются и выдаются в ведомость.
"""
import json
import os

from norms.constants import GAP_NO_FASTENING_MM
from norms import tables as norm_tables

# Средства крепления — из каталога 1.6в (data/norms/fastening_means.json),
# чтобы сечения и нормативные пункты не дублировались в коде
MEANS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "norms", "fastening_means.json")
FRAME_KEY = "распорная рама"


def load_means_catalog() -> dict[str, dict]:
    """Каталог крепёжных средств: {type: запись каталога}."""
    with open(MEANS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {m["type"]: m for m in data["means"]}


MEANS = {name: {"section_mm": m["section_mm"], "norm_point": m["norm_point"],
                "filler_max_mm": m.get("filler_max_mm")}
         for name, m in load_means_catalog().items()}


def _union_length(intervals: list[tuple[float, float]]) -> float:
    """Длина объединения интервалов (слияние перекрытий)."""
    merged = 0.0
    cur_start: float | None = None
    cur_end = 0.0
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if cur_start is None:
            cur_start, cur_end = start, end
        elif start > cur_end:
            merged += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_start is not None:
        merged += cur_end - cur_start
    return merged


def _transverse_rows(placed: list[dict]) -> list[list[dict]]:
    """Поперечные ряды: группы мест, перекрывающихся по длине вагона (ось X)."""
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_end = None
    for p in sorted(placed, key=lambda item: item["x"]):
        if cur_end is None or p["x"] >= cur_end:
            if cur:
                rows.append(cur)
            cur, cur_end = [p], p["x"] + p["length"]
        else:
            cur.append(p)
            cur_end = max(cur_end, p["x"] + p["length"])
    if cur:
        rows.append(cur)
    return rows


def transverse_gaps_mm(placed: list[dict], wagon: dict) -> float:
    """Сумма зазоров по ширине вагона — гл. 11 п. 3.1 (транспортные пакеты).

    Для каждого поперечного ряда берётся его нижний ярус: зазоры между местами
    и до боковых стенок в сумме.
    """
    width = wagon["inner"]["width"]
    total = 0.0
    for row in _transverse_rows(placed):
        z_min = min(p["z"] for p in row)
        level = [(p["y"], p["y"] + p["width"]) for p in row if p["z"] == z_min]
        total += max(0.0, width - _union_length(level))
    return total


def total_gaps_mm(placed: list[dict], wagon: dict) -> float:
    """Путь A: сумма зазоров по длине вагона (соседние интервалы + торцы)."""
    L = wagon["inner"]["length"]
    xs = sorted((p["x"], p["x"] + p["length"]) for p in placed)
    if not xs:
        return float(L)
    gaps = [xs[0][0]] + [xs[i][0] - xs[i - 1][1] for i in range(1, len(xs))] + [L - xs[-1][1]]
    return float(sum(max(0.0, g) for g in gaps))


def uncovered_length_mm(placed: list[dict], wagon: dict) -> float:
    """Путь B: непокрытая длина по оси X (объединение интервалов)."""
    L = wagon["inner"]["length"]
    covered = _union_length([(max(0.0, p["x"]), min(p["x"] + p["length"], L)) for p in placed])
    return max(0.0, L - covered)


def force_requirements_t(placed: list[dict], items_meta: dict, wagon: dict,
                         fastening: str | None = None, friction: str | None = None) -> dict:
    """Потребность в удержании груза по гл. 10: силы инерции против трения, тс.

    F_пр = a_пр·Q (3)(4), F_п = a_п·Q (6)(7) с базой вагона, F_тр = Q·μ (11)(12);
    потребное удержание — превышение инерционной силы над трением.
    """
    from norms.center_of_mass import center_of_mass, bogies_from_wagon
    total_kg = sum(items_meta[p["type_id"]]["mass"] for p in placed)
    mass_t = total_kg / 1000
    if mass_t <= 0:
        return {"масса_т": 0.0, "F_пр_тс": 0.0, "F_п_тс": 0.0, "F_тр_тс": 0.0,
                "удержание_продольное_тс": 0.0, "удержание_поперечное_тс": 0.0}
    length = wagon["inner"]["length"]
    weighted = [{**p, "mass": items_meta[p["type_id"]]["mass"]} for p in placed]
    cx, cy, _, _ = center_of_mass(weighted, length)
    base = bogies_from_wagon(wagon).wheelbase_mm
    a_pr = norm_tables.longitudinal_inertial_coefficient(mass_t, fastening)
    a_p = norm_tables.lateral_inertial_coefficient(cx - length / 2, base)
    mu = norm_tables.friction_coefficient(friction)
    return {
        "масса_т": round(mass_t, 3),
        "база_вагона_мм": base,
        "a_пр_тс_т": round(a_pr, 4),
        "a_п_тс_т": round(a_p, 4),
        "F_пр_тс": round(a_pr * mass_t, 3),
        "F_п_тс": round(a_p * mass_t, 3),
        "F_тр_тс": round(mu * mass_t, 3),
        # норматив (11)(12): в поперечном направлении трение снижается на долю a_в
        "F_тр_поперечное_тс": round(mu * mass_t * (1 - a_p), 3),
        "удержание_продольное_тс": round(max(0.0, a_pr * mass_t - mu * mass_t), 3),
        "удержание_поперечное_тс": round(max(0.0, a_p * mass_t - mu * mass_t * (1 - a_p)), 3),
        "norm_point": "ЦМ-943 гл. 10 пп. 10.2.1, 10.2.2, 10.3.1",
    }


def hardware_violations(means: list[dict]) -> list[dict]:
    """Проверка крепёжных изделий ведомости по гл. 1 (табл. 7, п. 4.4).

    Ведомость может указывать параметры крепежа: `nails` ([диаметр, длина]) и
    `wire_diameter_mm`. Значения вне табличных — нарушение.
    """
    out: list[dict] = []
    for m in means:
        nails = m.get("nails")
        if nails:
            diameter, length = nails[0], nails[1]
            if not norm_tables.nail_is_allowed(diameter, length):
                out.append({"code": "КРЕПЁЖ_ИЗДЕЛИЯ", "objects": [m.get("type", "крепление")],
                            "value": float(diameter),
                            "reason": f"гвоздь {diameter}×{length} мм не входит в табл. 7 гл. 1"})
        wire = m.get("wire_diameter_mm")
        if wire is not None and wire < norm_tables.wire_requirements()["min_diameter_mm"]:
            out.append({"code": "КРЕПЁЖ_ИЗДЕЛИЯ", "objects": [m.get("type", "растяжка")],
                        "value": float(wire),
                        "reason": f"проволока {wire} мм тоньше минимальных "
                                  f"{norm_tables.wire_requirements()['min_diameter_mm']} мм (п. 4.4)"})
    return out


def compute_fastening(placed: list[dict], items_meta: dict, wagon: dict,
                      fastening: str | None = None, friction: str | None = None) -> list[dict]:
    """Путь A: ведомость средств крепления с силами и зазорами."""
    lateral = transverse_gaps_mm(placed, wagon)
    longitudinal = total_gaps_mm(placed, wagon)
    gap = max(lateral, longitudinal)
    forces = force_requirements_t(placed, items_meta, wagon, fastening, friction)
    means: list[dict] = []
    # гл. 11: при плотной укладке (зазоры ≤ 200 мм) сдвиг удерживают стенки вагона
    # и соседние места; средства нужны, когда есть свободная зона (пп. 1.13, 3.1).
    if gap > GAP_NO_FASTENING_MM.value:
        means.append({
            "type": FRAME_KEY,
            "gap_mm": round(gap, 1),
            "gaps_mm": {"по_ширине": round(lateral, 1), "по_длине": round(longitudinal, 1)},
            "required_force_t": forces["удержание_продольное_тс"],
            "section_mm": MEANS[FRAME_KEY]["section_mm"],
            "norm_point": MEANS[FRAME_KEY]["norm_point"],
            "origin": GAP_NO_FASTENING_MM.origin,
        })
        if longitudinal > GAP_NO_FASTENING_MM.value and forces["удержание_продольное_тс"] > 0:
            means.append({
                "type": "упорные бруски",
                "required_force_t": forces["удержание_продольное_тс"],
                "section_mm": MEANS["упорные бруски"]["section_mm"],
                "norm_point": MEANS["упорные бруски"]["norm_point"],
                "origin": GAP_NO_FASTENING_MM.origin,
            })
        if lateral > GAP_NO_FASTENING_MM.value and forces["удержание_поперечное_тс"] > 0:
            means.append({
                "type": "поперечные упоры",
                "required_force_t": forces["удержание_поперечное_тс"],
                "norm_point": "ЦМ-943 гл. 10 п. 10.2.2 (поперечная инерционная сила) + гл. 11 п. 1.13",
                "origin": GAP_NO_FASTENING_MM.origin,
            })
        if gap <= (MEANS["заполнение зазора"]["filler_max_mm"] or 0):
            means.append({
                "type": "заполнение зазора",
                "gap_mm": round(gap, 1),
                "norm_point": MEANS["заполнение зазора"]["norm_point"],
            })
    return means


def check_fastening(placed: list[dict], means: list[dict], wagon: dict,
                    items_meta: dict | None = None) -> bool:
    """Путь B (независимая проверка): зазоры и потребность в удержании закрыты."""
    if not placed:
        return True
    lateral = transverse_gaps_mm(placed, wagon)
    longitudinal = uncovered_length_mm(placed, wagon)
    types = {m["type"] for m in means}
    limit = GAP_NO_FASTENING_MM.value
    if max(lateral, longitudinal) > limit and FRAME_KEY not in types:
        return False  # свободная зона — крепление обязательно (гл. 11 п. 1.13)
    if items_meta:  # силовая проверка по гл. 10: трение должно удерживать либо есть упоры
        forces = force_requirements_t(placed, items_meta, wagon)
        if longitudinal > limit and forces["удержание_продольное_тс"] > 0 and not (types & {FRAME_KEY, "упорные бруски"}):
            return False
        if lateral > limit and forces["удержание_поперечное_тс"] > 0 and "поперечные упоры" not in types:
            return False
    # крепёжные изделия ведомости — по гл. 1 (табл. 7, п. 4.4)
    if hardware_violations(means):
        return False
    # геометрия средства: сечение бруска должно помещаться в зазор
    for m in means:
        if m["type"] == FRAME_KEY and m.get("gap_mm", 0) < (MEANS[FRAME_KEY]["section_mm"][1] or 0):
            return False
    return True
