"""Гейт 2 — крепление и последовательность (задача 3.4б, модуль назван по плану).

Проверяет ведомость крепления (расчёт + независимая проверка, ADR-019) и
достижимость каждого места через дверной проём (задача 3.5). Любое нарушение —
FAILED, план не выдаётся (§3.1).
"""
from schemas.models import GateStatus, FailureReason, FasteningPlan
from norms.securing import compute_fastening, check_fastening, hardware_violations
from engine.sequence import door_clearance


def check_gate2(placed: list[dict], wagon: dict, items_meta: dict | None = None) -> tuple[GateStatus, FasteningPlan, list[FailureReason]]:
    """Гейт 2: расчёт крепления (путь A) + независимая проверка (путь B) + дверь."""
    meta = items_meta or {}
    means = compute_fastening(placed, meta, wagon)
    violations: list[FailureReason] = []
    if not check_fastening(placed, means, wagon, meta or None):
        violations.append(FailureReason(code="ЗАЗОР_ТРЕБУЕТ_КРЕПЛЕНИЯ", value=None))
    for problem in hardware_violations(means):
        violations.append(FailureReason(code=problem["code"], objects=problem["objects"],
                                        value=problem.get("value")))
    blocked = door_clearance(placed, wagon)
    violations.extend(blocked)
    # увязочные устройства (модель вагона, задача 1.3): растяжки и обвязки к ним
    # крепятся; если в модели их перечень пуст, а в ведомости они есть — нарушение
    tie_needed = any(m.get("type") in ("растяжка", "обвязка", "увязка") for m in means)
    tie_available = bool(wagon.get("tie_down_devices"))
    if tie_needed and not tie_available:
        violations.append(FailureReason(code="НЕТ_ТОЧЕК_ПРИВЯЗКИ",
                                        objects=[m["type"] for m in means if m.get("type") in ("растяжка", "обвязка", "увязка")]))
    plan = FasteningPlan(means=means, sequence_ok=not blocked, tie_points_ok=not tie_needed or tie_available)
    return (GateStatus.FAILED if violations else GateStatus.PASSED), plan, violations
