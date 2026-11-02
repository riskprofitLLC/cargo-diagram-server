"""Интерпретатор нормативных таблиц (задача 2.1): линейная интерполяция по
таблицам 10/11 ЦМ-943 (п. 6.3.4). Каждая формула привязана к редакции."""
import json
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "norms", "tu_cm943.json")


def _load() -> dict:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _interp(points: list, x: float) -> float:
    """Линейная интерполяция по упорядоченным точкам [[x, y], ...]."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def allowed_longitudinal_shift_mm(mass_t: float) -> float:
    """Таблица 10: допускаемое продольное смещение ЦТ груза, мм."""
    return _interp(_load()["tables"]["tab10_longitudinal_ct_shift"]["points"], mass_t)


def allowed_lateral_shift_mm(mass_t: float, ct_height_mm: float) -> float:
    """Таблица 11: допускаемое поперечное смещение, мм; интерполяция по массе
    и по высоте ЦТ вагона с грузом над УГР."""
    grid = _load()["tables"]["tab11_lateral_ct_shift"]["grid"]
    masses = grid["masses_t"]
    heights = grid["ct_heights_mm"]
    vals = grid["values"]

    def row(m: float) -> dict:
        # интерполяция по массе для каждой высоты
        out = {}
        for h in heights:
            col = []
            for mt in masses:
                v = vals.get(str(mt), {}).get(str(h))
                if v is not None:
                    col.append((mt, v))
            out[h] = _interp(sorted(col), m) if col else None
        return out

    # сначала интерполируем по высоте для границ масс, потом по массе
    def at_mass(mt: float) -> float:
        r = row(mt)
        pts = [(h, v) for h, v in r.items() if v is not None]
        return _interp(sorted(pts), ct_height_mm)

    return _interp([(m, at_mass(m)) for m in masses], mass_t)


# --- Трассировка (задача 2.1): формула → значения → пункт ТУ + редакция ---
EDITION = "ЦМ-943 (КонсультантПлюс с отметками ВС РФ АКПИ17-799, изм. 23.10.2017)"


def trace_longitudinal(mass_t: float) -> dict:
    """Трассировка проверки продольного смещения ЦТ (табл. 10, п. 6.3.1)."""
    value = allowed_longitudinal_shift_mm(mass_t)
    return {
        "formula": "l_c = интерполяция табл. 10 (п. 6.3.4)",
        "inputs": {"масса_груза_т": mass_t},
        "result_mm": value,
        "norm_point": "ЦМ-943 табл. 10, п. 6.3.1",
        "edition": EDITION,
    }


def trace_lateral(mass_t: float, ct_height_mm: float) -> dict:
    """Трассировка проверки поперечного смещения ЦТ (табл. 11, п. 6.3.2)."""
    value = allowed_lateral_shift_mm(mass_t, ct_height_mm)
    return {
        "formula": "b_c = интерполяция табл. 11 по массе и высоте ЦТ (п. 6.3.4)",
        "inputs": {"масса_груза_т": mass_t, "высота_цт_мм": ct_height_mm},
        "result_mm": value,
        "norm_point": "ЦМ-943 табл. 11, п. 6.3.2",
        "edition": EDITION,
    }


# --- Гл. 6 табл. 12: кососимметричное размещение двух мест (п. 6.3.6) ---
def allowed_kososymmetric_distances_mm(mass_t: float) -> dict:
    """Допускаемые расстояния между ЦТ двух мест (l — продольное, b — поперечное)."""
    points = _load()["tables"]["tab12_kososymmetric_pair"]["points"]
    l_pts = [(p[0], p[1]) for p in points]
    b_pts = [(p[0], p[2]) for p in points]
    return {"l_mm": _interp(l_pts, mass_t), "b_mm": _interp(b_pts, mass_t)}


def trace_kososymmetric(mass_t: float) -> dict:
    allowed = allowed_kososymmetric_distances_mm(mass_t)
    return {
        "formula": "l, b = интерполяция табл. 12 (п. 6.3.6)",
        "inputs": {"общая_масса_двух_мест_т": mass_t},
        "result_mm": allowed,
        "norm_point": "ЦМ-943 табл. 12, п. 6.3.6",
        "edition": EDITION,
    }


# --- Гл. 10: инерционные силы и трение (пп. 10.2.1, 10.2.2, 10.3.1) ---
def inertial_coefficients(fastening: str | None = None) -> dict:
    """Коэффициенты a22/a94 удельной продольной инерционной силы (табл. 17)."""
    tab = _load()["tables"]["tab17_inertial_force"]
    kind = fastening or tab["default"]
    if kind not in tab["fastening"]:
        raise ValueError(f"неизвестный тип крепления: {kind!r} (есть {sorted(tab['fastening'])})")
    return tab["fastening"][kind]


def longitudinal_inertial_coefficient(mass_t: float, fastening: str | None = None) -> float:
    """a_пр по формуле (4): a22 − Q_гр·(a22 − a94)/72, тс/т.

    Q_гр — масса груза, т: при 0 т → a22, при 72 т → a94 (разность масс брутто
    вагона 94 − 22 = 72 т — знаменатель формулы из текста ТУ).
    """
    c = inertial_coefficients(fastening)
    return c["a22"] - mass_t * (c["a22"] - c["a94"]) / 72


def lateral_inertial_coefficient(ct_shift_mm: float, wagon_base_mm: float) -> float:
    """a_п по формуле (7): 0.33 + 0.44·l_гр/l_в, тс/т."""
    if wagon_base_mm <= 0:
        raise ValueError("база вагона должна быть положительной")
    return 0.33 + 0.44 * abs(ct_shift_mm) / wagon_base_mm


def friction_coefficient(kind: str | None = None) -> float:
    """Коэффициент трения μ (п. 10.3.1)."""
    tab = _load()["tables"]["friction"]
    key = kind or tab["default"]
    if key not in tab["values"]:
        raise ValueError(f"неизвестная пара поверхностей: {key!r} (есть {sorted(tab['values'])})")
    return tab["values"][key]


def covered_wagon_k(kind: str) -> float:
    """Коэффициенты гл. 11 п. 1.15; для продольной берётся большее (консервативно)."""
    tab = _load()["tables"]["covered_wagon_loads"]["K"]
    value = tab.get(kind)
    if isinstance(value, list):
        return float(max(value))
    if value is None:
        raise ValueError(f"неизвестная нагрузка: {kind!r} (есть {sorted(tab)})")
    return float(value)


def trace_inertial_forces(mass_t: float, ct_shift_mm: float, wagon_base_mm: float,
                          fastening: str | None = None, friction: str | None = None) -> dict:
    """Трассировка силового расчёта (гл. 10): силы инерции и трение."""
    kind = fastening or _load()["tables"]["tab17_inertial_force"]["default"]
    a_pr = longitudinal_inertial_coefficient(mass_t, kind)
    a_p = lateral_inertial_coefficient(ct_shift_mm, wagon_base_mm)
    mu = friction_coefficient(friction)
    return {
        "formula": "F_пр = a_пр·Q (3)(4); a_п = 0.33 + 0.44·l_цт/l_в (7); F_тр = Q·μ (11)",
        "inputs": {"масса_груза_т": mass_t, "смещение_цт_мм": ct_shift_mm,
                   "база_вагона_мм": wagon_base_mm, "тип_крепления": kind, "трение": mu},
        "result": {"a_пр_тс_т": round(a_pr, 4), "a_п_тс_т": round(a_p, 4),
                   "F_пр_тс": round(a_pr * mass_t, 4), "F_п_тс": round(a_p * mass_t, 4),
                   "F_тр_тс": round(mu * mass_t, 4)},
        "norm_point": "ЦМ-943 гл. 10 пп. 10.2.1, 10.2.2, 10.3.1; табл. 17",
        "edition": EDITION,
    }


# --- Гл. 1: крепёжные изделия (табл. 7, пп. 4.4, 4.17) ---
def allowed_nail_sizes() -> list[list[float]]:
    """Допускаемые размеры гвоздей: [диаметр, длина min, длина max, шляпка]."""
    return [list(row) for row in _load()["tables"]["ch1_fastening_hardware"]["nails"]]


def wire_requirements() -> dict:
    """Требования к проволоке растяжек (п. 4.4)."""
    return dict(_load()["tables"]["ch1_fastening_hardware"]["wire"])


def nail_is_allowed(diameter_mm: float, length_mm: float) -> bool:
    """Проверка гвоздя по табл. 7 (диаметр + длина в допускаемом диапазоне)."""
    for d, length_min, length_max, _head in allowed_nail_sizes():
        if abs(d - diameter_mm) < 1e-9 and length_min <= length_mm <= length_max:
            return True
    return False


def trace_hardware() -> dict:
    """Трассировка требований к крепёжным изделиям (гл. 1)."""
    return {
        "formula": "табл. 7 (гвозди), п. 4.4 (проволока), п. 4.17 (стойки)",
        "result": {"гвозди": allowed_nail_sizes(), "проволока": wire_requirements()},
        "norm_point": "ЦМ-943 гл. 1 табл. 7, пп. 4.4, 4.17",
        "edition": EDITION,
    }
