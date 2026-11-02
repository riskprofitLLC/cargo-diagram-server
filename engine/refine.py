"""L2 — CP-SAT дорешивание 2D-подзадач слоёв (задача 3.6).

Режем слой по высоте, в каждом 2D-слое решаем упаковку остатков через
AddNoOverlap2D. Включается только при улучшении ≥ порога X (конфиг, 3.9).
"""
from ortools.sat.python import cp_model


def refine_layer(layer_items: list[dict], area: tuple[int, int, int, int],
                 time_limit_s: float = 2.0) -> list[dict]:
    """2D-размещение items внутри прямоугольника area=(x0, y0, w, h) слоя."""
    ax, ay, aw, ah = area
    # предметы больше области отбрасываем: иначе пустой домен переменной
    fitting = [it for it in layer_items if 0 < it["length"] <= aw and 0 < it["width"] <= ah]
    if not fitting:
        return []
    m = cp_model.CpModel()
    chosen, xvars, yvars, x_ints, y_ints = [], [], [], [], []
    for i, it in enumerate(fitting):
        ln, w = it["length"], it["width"]
        x = m.NewIntVar(ax, ax + aw - ln, f"x{i}")
        y = m.NewIntVar(ay, ay + ah - w, f"y{i}")
        c = m.NewBoolVar(f"c{i}")
        chosen.append(c)
        xvars.append(x)
        yvars.append(y)
        x_ints.append(m.NewIntervalVar(x, ln, x + ln, f"xi{i}"))
        y_ints.append(m.NewIntervalVar(y, w, y + w, f"yi{i}"))
    m.AddNoOverlap2D(x_ints, y_ints)
    m.Maximize(sum(chosen))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1  # воспроизводимость стенда (3.9)
    status = solver.Solve(m)
    out = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, it in enumerate(fitting):
            if solver.Value(chosen[i]):
                out.append({**it, "x": solver.Value(xvars[i]), "y": solver.Value(yvars[i]),
                            "z": it.get("z", 0)})
    return out
