"""Нормативный гейт (задача 3.4в): нормы и применимость правил для кандидата.

Отдельный шаг конвейера (§3): выставляет `norms_status` и `compliance_status`
по результату гейта 1 и прикладывает трассировки формул к пунктам ТУ.
"""
from schemas.models import ComplianceStatus, GateStatus, NormsReport, NormsStatus
from engine.validator import validate_gate1
from norms.applicability import applicable_rules
from norms.tables import EDITION


def applicable_rule_codes(wagon: dict) -> list[str]:
    """Коды применимых к вагону правил (неприменённое ≠ PASSED, задача 2.2)."""
    return [r.code for r in applicable_rules(wagon.get("type", "covered"))]


def norms_gate(g1: GateStatus, wagon: dict, ct_check: dict | None = None,
               traces: list[dict] | None = None) -> NormsReport:
    """NormsReport для кандидата: статус норм, применимость, трассировки."""
    app_rules = applicable_rule_codes(wagon)
    if traces is None:
        traces = list(getattr(validate_gate1, "traces", []))
    if ct_check is None:
        ct_check = getattr(validate_gate1, "ct_check", {})
    checks: list[dict] = [{"name": "gate1", "status": g1.value, "applicable_rules": app_rules}]
    if ct_check:
        # ADR-018: к крытому вагону правило п. 10.4.1 не применяется (гл. 11 не требует)
        height_applicable = "CT_HEIGHT" in app_rules
        checks.append({
            "name": "ct_height_above_rail",
            "status": ("ПРОВЕРЕНО" if ct_check["with_tare"] else "ТРЕБУЕТСЯ ИЗ ПЕРВОИСТОЧНИКА")
                      if height_applicable else "НЕ ПРИМЕНИМО (ЦМ-943 гл. 11, ADR-018)",
            "value_mm": round(ct_check["value_mm"], 1),
            "trigger_stability_check": ct_check["trigger"],
            "norm_point": ct_check["norm_point"],
            "edition": EDITION,
        })
    checks.extend(traces)
    return NormsReport(
        norms_status=NormsStatus.PASSED if g1 == GateStatus.PASSED else NormsStatus.VIOLATION,
        compliance_status=ComplianceStatus.NON_TYPICAL,
        checks=checks,
    )
