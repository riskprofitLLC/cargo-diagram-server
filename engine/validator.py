"""Независимый валидатор — гейт 1 (задача 3.4). Не использует алгоритмы ядра.

Проверки: границы вагона, взаимные пересечения, ориентации, опора ≥ порога
(ADR-004), масса на штабель, нагрузка на пол, грузоподъёмность, ЦТ и тележки.
"""
from schemas.models import GateStatus, FailureReason
from norms.constants import SUPPORT_SHARE, CART_DIFF_MAX_T, FORKLIFT_WHEEL_KN
from norms.center_of_mass import center_of_mass, bogie_loads, bogies_from_wagon, ct_height_above_rail
from norms import tables as norm_tables


def _mass_kg(item: dict, items_meta: dict) -> float:
    """Масса места: из справочника, иначе из самого места (план несёт массу, ADR-016)."""
    meta = items_meta.get(item["type_id"]) or {}
    return float(meta.get("mass") or item.get("mass") or 0)


def _stack_loads(item: dict, others: list[dict], items_meta: dict, k_v: float) -> tuple[int, float]:
    """(число мест выше, нормативная вертикальная нагрузка на тару) — гл. 11 п. 1.15."""
    above = [o for o in others if o is not item and o["z"] >= item["z"] + item["height"]
             and _footprint_overlap(item, o)]
    return len(above), k_v * sum(_mass_kg(o, items_meta) for o in above)


def _footprint_overlap(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["length"] and b["x"] < a["x"] + a["length"]
            and a["y"] < b["y"] + b["width"] and b["y"] < a["y"] + a["width"])


def stack_load_violations(placed: list[dict], items_meta: dict, wagon: dict) -> list[FailureReason]:
    """Штабелирование: гл. 11 п. 1.15 (P_в = K_в·Σm_выше) и запрет штабелировать
    нештабелируемый груз."""
    k_v = norm_tables.covered_wagon_k("вертикальная") if wagon.get("type") == "covered" else 1.0
    out: list[FailureReason] = []
    for p in placed:
        count, load = _stack_loads(p, placed, items_meta, k_v)
        if count == 0:
            continue
        meta = items_meta.get(p["type_id"]) or {}
        if not meta.get("stackable", True):
            out.append(FailureReason(code="ШТАБЕЛИРОВАНИЕ_НАРУШЕНО", objects=[p["type_id"]],
                                     value=float(count)))
            continue
        limit = meta.get("max_load_on_top")
        if limit is None:
            continue  # нет данных о прочности упаковки → NEEDS_DATA (оркестратор)
        if load > limit:
            out.append(FailureReason(code="ШТАБЕЛИРОВАНИЕ_НАРУШЕНО", objects=[p["type_id"]], value=load))
    return out


def kososymmetric_violations(placed: list[dict], items_meta: dict, wagon: dict) -> list[FailureReason]:
    """Кососимметричная пара мест: ЦМ-943 п. 6.3.6 и табл. 12 (равные массы,
    расстояния между ЦТ не более табличных; общий ЦТ — по табл. 10/11)."""
    if len(placed) != 2:
        return []
    a, b = placed
    length, width = wagon["inner"]["length"], wagon["inner"]["width"]
    ax = a["x"] + a["length"] / 2 - length / 2
    ay = a["y"] + a["width"] / 2 - width / 2
    bx = b["x"] + b["length"] / 2 - length / 2
    by = b["y"] + b["width"] / 2 - width / 2
    if not (ax * bx < 0 and ay * by < 0):
        return []  # не диагональное (кососимметричное) размещение
    out: list[FailureReason] = []
    mass_a, mass_b = _mass_kg(a, items_meta), _mass_kg(b, items_meta)
    if mass_a != mass_b:
        out.append(FailureReason(code="КОСОСИММЕТРИЯ", objects=[a["type_id"], b["type_id"]],
                                 value=float(mass_a - mass_b)))
    allowed = norm_tables.allowed_kososymmetric_distances_mm((mass_a + mass_b) / 1000)
    if abs(ax - bx) > allowed["l_mm"]:
        out.append(FailureReason(code="КОСОСИММЕТРИЯ", objects=[a["type_id"], b["type_id"]],
                                 value=abs(ax - bx)))
    if abs(ay - by) > allowed["b_mm"]:
        out.append(FailureReason(code="КОСОСИММЕТРИЯ", objects=[a["type_id"], b["type_id"]],
                                 value=abs(ay - by)))
    return out


def _rect_union_area(rects: list[tuple[int, int, int, int]]) -> int:
    """Площадь объединения прямоугольников (x0, y0, x1, y1) — без двойного счёта."""
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    area = 0
    for x0, x1 in zip(xs, xs[1:]):
        if x1 <= x0:
            continue
        spans = sorted((r[1], r[3]) for r in rects if r[0] < x1 and r[2] > x0)
        height = 0
        cur_start = cur_end = None
        for y0, y1 in spans:
            if cur_start is None:
                cur_start, cur_end = y0, y1
            elif y0 > cur_end:
                height += cur_end - cur_start
                cur_start, cur_end = y0, y1
            else:
                cur_end = max(cur_end, y1)
        if cur_start is not None:
            height += cur_end - cur_start
        area += (x1 - x0) * height
    return area


def _overlap(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["x"] + b["length"] and b["x"] < a["x"] + a["length"]
        and a["y"] < b["y"] + b["width"] and b["y"] < a["y"] + a["width"]
        and a["z"] < b["z"] + b["height"] and b["z"] < a["z"] + a["height"]
    )


def support_share(item: dict, others: list[dict], wagon: dict) -> float:
    """Доля площади основания, лежащей на полу (z=0) или на другом грузе."""
    if item["z"] == 0:
        return 1.0
    base = item["length"] * item["width"]
    if base <= 0:
        return 0.0  # габарит неизвестен → опора не подтверждена (fail-closed)
    rects = []
    for o in others:
        if o is item or o["z"] + o["height"] != item["z"]:
            continue
        x0 = max(item["x"], o["x"])
        x1 = min(item["x"] + item["length"], o["x"] + o["length"])
        y0 = max(item["y"], o["y"])
        y1 = min(item["y"] + item["width"], o["y"] + o["width"])
        if x1 > x0 and y1 > y0:
            rects.append((x0, y0, x1, y1))
    # площадь объединения, а не сумма площадок: пересечения опор не считаются дважды
    return min(_rect_union_area(rects) / base, 1.0)


def validate_gate1(placed: list[dict], items_meta: dict, wagon: dict, payload_t: int) -> tuple[GateStatus, list[FailureReason]]:
    violations: list[FailureReason] = []
    L, W, H = wagon["inner"]["length"], wagon["inner"]["width"], wagon["inner"]["height"]
    for i, p in enumerate(placed):
        if not (0 <= p["x"] and p["x"] + p["length"] <= L and 0 <= p["y"] and p["y"] + p["width"] <= W
                and 0 <= p["z"] and p["z"] + p["height"] <= H):
            violations.append(FailureReason(code="OUT_OF_BOUNDS", objects=[p["type_id"]], value=float(i)))
        # запрещённые зоны (модель вагона, задача 1.3): пересечение с зоной — нарушение
        for zone in wagon.get("forbidden_zones") or []:
            if _overlap(p, zone):
                violations.append(FailureReason(code="ЗАПРЕЩЁННАЯ_ЗОНА", objects=[p["type_id"], zone.get("name", "зона")],
                                                value=float(i)))
        share = support_share(p, placed, wagon)
        if share < SUPPORT_SHARE.value:
            violations.append(FailureReason(code="SUPPORT_VIOLATION", objects=[p["type_id"]], value=share))
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if _overlap(placed[i], placed[j]):
                violations.append(FailureReason(code="OVERLAP", objects=[placed[i]["type_id"], placed[j]["type_id"]]))
    violations.extend(stack_load_violations(placed, items_meta, wagon))
    violations.extend(kososymmetric_violations(placed, items_meta, wagon))
    # масса и ЦТ (расчёт — единый модуль ADR-004)
    weighted = [{**p, "mass": _mass_kg(p, items_meta)} for p in placed]
    total_kg = sum(p["mass"] for p in weighted)
    if total_kg > payload_t * 1000:
        violations.append(FailureReason(code="ПЕРЕГРУЗ_МАССА", value=total_kg / 1000))
    cx, cy, cz, _ = center_of_mass(weighted, L)
    # Высота ЦТ вагона с грузом над УГР (формула 19): > 2300 мм — ТРИГГЕР проверки
    # поперечной устойчивости (п. 10.4.1), а не запрет. Полная проверка требует
    # высоты ЦТ тары (табл. 18 для крытого вагона — задача 2.4а, данных нет).
    ct_check = ct_height_above_rail(wagon, weighted)
    mass_t = total_kg / 1000
    tr_long = norm_tables.trace_longitudinal(mass_t)
    if abs(cx - L / 2) > tr_long["result_mm"]:
        violations.append(FailureReason(code="ЦТ_ПРОДОЛЬНОЕ", value=cx - L / 2))
    # таблица 11 нормируется по высоте ЦТ вагона с грузом над УГР
    tr_lat = norm_tables.trace_lateral(mass_t, ct_check["value_mm"])
    if abs(cy - W / 2) > tr_lat["result_mm"]:
        violations.append(FailureReason(code="ЦТ_ПОПЕРЕЧНОЕ", value=cy - W / 2))
    traces = [tr_long, tr_lat]
    la, lb = bogie_loads(weighted, L, bogies_from_wagon(wagon))
    if abs(la - lb) / 1000 > CART_DIFF_MAX_T.value:
        violations.append(FailureReason(code="ЦТ_ТЕЛЕЖКИ", value=abs(la - lb) / 1000))
    # нагрузка на пол (2.4): эквивалент колеса погрузчика 22 кН на пятно 0,25×0,25 м
    # (ГОСТ 22235-2023 п. 4.3.1) — давление груза на пол не выше этого эквивалента
    max_pressure_pa = FORKLIFT_WHEEL_KN.value * 1000 / (0.25 * 0.25)
    for p in placed:
        if p["z"] != 0:
            continue
        pressure = _mass_kg(p, items_meta) * 9.81 / (p["length"] * p["width"] / 1e6)
        if pressure > max_pressure_pa:
            violations.append(FailureReason(code="НАГРУЗКА_ПОЛ", objects=[p["type_id"]], value=pressure / 1000))
    validate_gate1.traces = traces  # доступно оркестратору для NormsReport
    validate_gate1.ct_check = ct_check  # триггер высоты ЦТ (п. 10.4.1)
    return (GateStatus.PASSED if not violations else GateStatus.FAILED), violations
