"""Балластировка вагона (задача 2.4а): ЦМ-943 гл. 6 п. 6.3.5.

Допускается балластировка для соблюдения требований о положении общего ЦТ;
масса и место балласта определяются по формулам (1) и (2) той же главы.
Балласт — такое же грузовое место: он входит в расчёт ЦТ, массы и тележек.
"""
BALLAST_TYPE_ID = "балласт"
BALLAST_SIZE_MM = (1000, 1000, 500)  # габарит места балласта (РЕШЕНИЕ ВЛАДЕЛЬЦА, MVP)


def ballast_item(placed: list[dict], items_meta: dict, wagon: dict) -> dict | None:
    """Подбирает балласт для возврата ЦТ в допуск (табл. 10/11).

    Возвращает место балласта (dict для `placed`) или None, если балласт не нужен
    либо невозможен (нет запаса по грузоподъёмности).
    """
    from norms.center_of_mass import center_of_mass
    from norms import tables as norm_tables

    if not placed:
        return None
    length, width = wagon["inner"]["length"], wagon["inner"]["width"]
    weighted = [{**p, "mass": items_meta[p["type_id"]]["mass"]} for p in placed]
    cx, cy, cz, total_kg = center_of_mass(weighted, length)
    if total_kg <= 0:
        return None
    mass_t = total_kg / 1000
    allowed_long = norm_tables.allowed_longitudinal_shift_mm(mass_t)
    allowed_lat = norm_tables.allowed_lateral_shift_mm(mass_t, wagon["floor_height_urg"] + cz)
    shift_x = cx - length / 2
    shift_y = cy - width / 2
    need_x = abs(shift_x) - allowed_long
    need_y = abs(shift_y) - allowed_lat
    if need_x <= 0 and need_y <= 0:
        return None
    ballast_length, ballast_width, ballast_height = BALLAST_SIZE_MM
    # балласт ставим у противоположной стенки: он смещает ЦТ к середине
    x = 0 if shift_x > 0 else length - ballast_length
    y = 0 if shift_y > 0 else width - ballast_width
    lever_x = abs(x + ballast_length / 2 - length / 2)
    lever_y = abs(y + ballast_width / 2 - width / 2)
    mass_kg = 0.0
    if need_x > 0 and lever_x > 0:
        # (M·cx + m·x_b)/(M+m) = L/2 + allowed  →  m = M·need_x/(lever_x − need_x)
        mass_kg = max(mass_kg, total_kg * need_x / max(1e-9, lever_x - need_x))
    if need_y > 0 and lever_y > 0:
        mass_kg = max(mass_kg, total_kg * need_y / max(1e-9, lever_y - need_y))
    mass_kg = int(mass_kg) + 1  # консервативно вверх (ADR-001)
    if total_kg + mass_kg > wagon["payload_t"] * 1000:
        return None  # запаса по грузоподъёмности нет — балласт невозможен
    return {
        "type_id": BALLAST_TYPE_ID,
        "x": x,
        "y": y,
        "z": 0,
        "length": ballast_length,
        "width": ballast_width,
        "height": ballast_height,
        "mass": mass_kg,
        "orientation": "xyz",
        "reason": "балластировка для удержания ЦТ в допуске (п. 6.3.5)",
    }
