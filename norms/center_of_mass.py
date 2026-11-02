"""Единый модуль расчёта ЦТ и нагрузок на тележки (ADR-004, задача 2.4а).

Ось X — вдоль вагона, начало у торца A. Тележки симметричны относительно
середины вагона: координата центра первой тележки = (длина вагона − база) / 2.
"""
from dataclasses import dataclass

from norms.constants import BOGIE_WHEELBASE_MM, CT_HEIGHT_MAX_MM


@dataclass(frozen=True)
class WagonBogies:
    wheelbase_mm: float  # расстояние между центрами тележек
    first_center_mm: float | None = None  # координата центра первой тележки от торца A


def center_of_mass(placed: list[dict], wagon_length_mm: int) -> tuple[float, float, float, float]:
    """Возвращает (x_цт, y_цт, z_цт, масса_кг) по размещённым грузам.

    placed: dict с полями x,y,z,length,width,height,mass (мм/кг, низ груза).
    """
    total = sum(p["mass"] for p in placed)
    if total == 0:
        return 0.0, 0.0, 0.0, 0
    cx = sum(p["mass"] * (p["x"] + p["length"] / 2) for p in placed) / total
    cy = sum(p["mass"] * (p["y"] + p["width"] / 2) for p in placed) / total
    cz = sum(p["mass"] * (p["z"] + p["height"] / 2) for p in placed) / total
    return cx, cy, cz, total


def bogies_from_wagon(wagon: dict) -> WagonBogies:
    """База тележек из модели вагона (задача 1.4), иначе — константа-заглушка."""
    wheelbase = wagon.get("bogie_wheelbase_mm") or BOGIE_WHEELBASE_MM.value
    return WagonBogies(wheelbase_mm=float(wheelbase))


def ct_height_above_rail(wagon: dict, placed: list[dict]) -> dict:
    """Высота общего ЦТ вагона с грузом над УГР — формула (19) ЦМ-943 гл. 10.

    Для полной формулы нужна высота ЦТ тары вагона (табл. 18 — только полувагоны
    и платформы); если её в сид-данных нет, возвращается оценка только по грузу
    с признаком with_tare=False (проверка по п. 10.4.1 требует данных — 2.4а).
    """
    _, _, cz, total = center_of_mass(placed, wagon["inner"]["length"])
    floor = wagon["floor_height_urg"]
    tare_ct = wagon.get("tare_ct_mm")
    if tare_ct and total:
        tare_kg = wagon["tare_t"] * 1000
        value = (total * (floor + cz) + tare_kg * tare_ct) / (total + tare_kg)
        with_tare = True
    else:
        value = floor + cz
        with_tare = False
    return {
        "value_mm": value,
        "with_tare": with_tare,
        # п. 10.4.1: превышение — триггер проверки поперечной устойчивости (не запрет)
        "trigger": value > CT_HEIGHT_MAX_MM.value,
        "norm_point": "ЦМ-943 гл. 10 п. 10.4.1 (формула 19), п. 6.3.6",
    }


def bogie_loads(placed: list[dict], wagon_length_mm: int, bogies: WagonBogies) -> tuple[float, float]:
    """Нагрузки на тележки A и B, кг. Статика: опоры в центрах тележек."""
    cx, _, _, total = center_of_mass(placed, wagon_length_mm)
    if total == 0:
        return 0.0, 0.0
    # опоры не в торцах вагона, а в центрах тележек: x_a = (L − база)/2
    b = bogies.wheelbase_mm
    x_a = bogies.first_center_mm if bogies.first_center_mm is not None else (wagon_length_mm - b) / 2
    load_b = total * (cx - x_a) / b
    return total - load_b, load_b
