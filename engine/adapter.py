"""Адаптер packingsolver boxstacks (задачи 3.2а/3.2, уровень L1).

Ядро само учитывает опору/штабелируемость (boxstacks). Ограничения зон и
запрет ориентации — через rotations (ADR-007а), нештабелируемость — через
maximum_stackability=1 (в штабеле с грузом нет соседей).
"""
import os

from packingsolver import boxstacks as psbs

# ядро boxstacks допускает только эти два поворота (ось Z остаётся высотой)
ROTATIONS = {"xyz": psbs.Rotation.XYZ, "yxz": psbs.Rotation.YXZ}
WEIGHT_ABOVE_UNKNOWN = 10**12  # «без ограничения» для штабелируемых без данных о прочности
# Режим поиска: anytime — лучший план в бюджете (прод); deterministic —
# воспроизводимость стенда независимо от загрузки машины (задачи 0.3/3.9)
SOLVER_MODES = {
    "anytime": psbs.OptimizationMode.Anytime,
    "deterministic": psbs.OptimizationMode.NotAnytimeDeterministic,
}
DEFAULT_MODE = os.environ.get("PACKINGSOLVER_MODE", "anytime")


def solve_mode(name: str | None = None):
    """Режим поиска по имени (неизвестное имя — ошибка, а не тихий фолбэк)."""
    key = (name or DEFAULT_MODE).lower()
    if key not in SOLVER_MODES:
        raise ValueError(f"неизвестный режим решателя: {name!r} (есть {sorted(SOLVER_MODES)})")
    return SOLVER_MODES[key]


def core_rotations(allowed_orientations: list[str] | None) -> list:
    """Ориентации входа → повороты ядра; несовместимые отбрасываются (ADR-007а)."""
    names = allowed_orientations or ["xyz", "yxz"]
    return [ROTATIONS[name.lower()] for name in names if name.lower() in ROTATIONS]


def _flag(value) -> bool:
    """Флаг из биндинга: в разных сборках это атрибут или метод (защита от дрейфа)."""
    return bool(value() if callable(value) else value)


def solver_status(output, has_solution: bool, time_limit_s: float) -> str:
    """Статус модели по §3.1: OPTIMAL / FEASIBLE / INFEASIBLE / TIMEOUT / UNKNOWN."""
    if _flag(output.is_proven_infeasible):
        return "INFEASIBLE"
    if has_solution:
        return "OPTIMAL" if _flag(output.is_proven_optimal) else "FEASIBLE"
    # решения нет: различаем «не успел» и «ничего не уместилось»
    if output.time >= time_limit_s * 0.99:
        return "TIMEOUT"
    return "UNKNOWN"


def solve_l1(wagon: dict, items: list[dict], time_limit_s: int, seed: int,
             mode: str | None = None) -> dict:
    """Решает boxstacks. Возвращает {placed, solver_status}."""
    L, W, H = wagon["inner"]["length"], wagon["inner"]["width"], wagon["inner"]["height"]
    b = psbs.InstanceBuilder()
    b.set_objective(psbs.Objective.Knapsack)  # один вагон = одна задача: макс. число размещённых
    b.add_bin_type(L, W, H, copies=1)
    id_to_type = {}
    type_dims = {}
    for idx, it in enumerate(items):
        rotations = core_rotations(it.get("allowed_orientations"))
        if not rotations or it["quantity"] <= 0:
            continue  # ни одна допустимая ориентация не поддержана ядром — тип не размещаем
        stackable = bool(it.get("stackable", True))
        item_type_id = b.add_item_type(
            it["length"], it["width"], it["height"],
            rotations=rotations,
            weight=it["mass"],
            stackability_id=idx,  # в один штабель — только места одного типоразмера
            maximum_stackability=1 if not stackable else None,
            maximum_weight_above=(
                it["max_load_on_top"] if it["max_load_on_top"] is not None else WEIGHT_ABOVE_UNKNOWN
            ),
            copies=it["quantity"],
        )
        id_to_type[str(item_type_id)] = it["type_id"]
        type_dims[it["type_id"]] = (it["length"], it["width"], it["height"])
    instance = b.build()
    params = psbs.OptimizeParameters()
    params.verbosity_level = 0
    params.time_limit = time_limit_s
    params.optimization_mode = solve_mode(mode)
    # seed в OptimizeParameters не предусмотрен; воспроизводимость — через
    # фиксацию версии ядра и лимитов (задача 0.3)
    output = psbs.optimize(instance, params)
    placed = []
    sol = output.solution
    if sol is None or sol.number_of_bins() == 0:
        status = solver_status(output, has_solution=False, time_limit_s=time_limit_s)
        return {"placed": placed, "solver_status": status, "objective": 0}
    sbin = sol.bin(0)  # один контейнер (copies=1)
    for stack in sbin.stacks:
        for item in stack.items:
            tid = id_to_type[str(item.item_type_id)]
            ln, w, h = type_dims[tid]
            # поворот YXZ меняет местами x и y
            if str(item.rotation).endswith("YXZ"):
                ln, w = w, ln
            placed.append({
                "type_id": tid,
                "x": stack.x_start,
                "y": stack.y_start,
                "z": item.z_start,
                "length": ln,
                "width": w,
                "height": h,
                "mass": next(it["mass"] for it in items if it["type_id"] == tid),
                "orientation": str(item.rotation),
            })
    status = solver_status(output, has_solution=True, time_limit_s=time_limit_s)
    return {"placed": placed, "solver_status": status, "objective": sol.number_of_items()}
