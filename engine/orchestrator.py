"""Оркестрация (задача 3.8): L0‖L1 → гейт 1 → repair → гейт 2 → нормы → план."""
import hashlib
import json
import os

from schemas.models import (
    CalcRequest, Plan, FasteningPlan, FailureReason, NormsReport, ResultStatus,
    SolverStatus, GateStatus, NormsStatus, ComplianceStatus, PlanSource, GoalMode,
)
from engine.normalize import normalize_request
from engine.validator import validate_gate1
from engine.validator_fastening import check_gate2
from engine.sequence import build_sequence
from engine import repair as repair_mod
from engine.refine import refine_layer
from engine.candidates import generate_candidates, pick_best
from engine.precheck import precheck, apply_goal_mode
from engine.gate_norms import norms_gate

L2_ENABLED = os.environ.get("L2_ENABLED", "0") == "1"  # ИЗМЕРЕНО в 3.9: gain 0% → выключен по умолчанию (задача 3.6)
L2_MIN_GAIN = int(os.environ.get("L2_MIN_GAIN", "1"))  # порог улучшения; ИЗМЕРЕНО в 3.9: 0% → L2 не даёт выигрыша
REPAIR_ITERATIONS = int(os.environ.get("REPAIR_ITERATIONS", "3"))  # конфиг, §5.1
# Версии конвейера (DoD-3): попадают и в Plan.versions, и в ключ кэша (4.3)
SOLVER_PIN = "packingsolver 0.1.1218"
NORMS_EDITION = "ЦМ-943 (КонсультантПлюс, АКПИ17-799) + ГОСТ 22235-2023"
VALIDATOR_VERSION = "1.0"

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
WAGONS_DIR = os.path.join(DATA, "wagons")


def available_wagons() -> list[str]:
    """Белый список моделей из сид-данных: wagon_id приходит извне (вход API)."""
    return sorted(f[:-5] for f in os.listdir(WAGONS_DIR) if f.endswith(".json"))


def load_wagon(wagon_id: str) -> dict:
    # сверка с каталогом сид-данных исключает обход пути через wagon_id
    if wagon_id not in available_wagons():
        raise ValueError(f"неизвестная модель вагона: {wagon_id!r}")
    with open(os.path.join(WAGONS_DIR, f"{wagon_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def _versions(norm: dict, solver_status: SolverStatus) -> dict:
    """Версии и хэш входа (DoD-3) — заполняются для любого исхода."""
    return {
        "solver": SOLVER_PIN,
        "norms": NORMS_EDITION,
        "validator": VALIDATOR_VERSION,
        "seed": norm["seed"],
        "solver_status": solver_status.value,
        "input_hash": hashlib.sha256(
            json.dumps(norm, sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
    }


def _unplaced(items: list[dict], placed: list[dict]) -> list[dict]:
    """Остаток по каждому типоразмеру (а не запрошенное количество)."""
    placed_counts: dict[str, int] = {}
    for p in placed:
        placed_counts[p["type_id"]] = placed_counts.get(p["type_id"], 0) + 1
    out = []
    for it in items:
        rest = it["quantity"] - placed_counts.get(it["type_id"], 0)
        if rest > 0:
            out.append({"type_id": it["type_id"], "quantity": rest, "reason": "не вместилось"})
    return out


def _refine_rest(items: list[dict], placed: list[dict], wagon: dict) -> list[dict]:
    """L2 (3.6): 2D-дорешивание слоя неразмещёнными остатками."""
    placed_counts: dict[str, int] = {}
    for p in placed:
        placed_counts[p["type_id"]] = placed_counts.get(p["type_id"], 0) + 1
    rest = []
    for it in items:
        for _ in range(max(0, it["quantity"] - placed_counts.get(it["type_id"], 0))):
            rest.append({**it})
    if not rest:
        return []
    return refine_layer(rest, (0, 0, wagon["inner"]["width"], wagon["inner"]["length"]), 2.0)


def _early_plan(norm: dict, result: ResultStatus, solver: SolverStatus,
                reasons: list[FailureReason], norms_status: NormsStatus,
                unplaced: list[dict], plan_source: PlanSource = PlanSource.L1) -> Plan:
    """Ранний отказ/недостаток данных: план без размещения, но с трассировкой."""
    return Plan(
        plan_id="local", wagon_id=norm["wagon_id"], placed=[], unplaced=unplaced,
        fastening=FasteningPlan(),
        norms=NormsReport(norms_status=norms_status, compliance_status=ComplianceStatus.NOT_CHECKED),
        result_status=result, solver_status=solver, plan_source=plan_source,
        gate1_status=GateStatus.NOT_CHECKED, gate2_status=GateStatus.NOT_CHECKED,
        failure_reason=reasons, versions=_versions(norm, solver),
    )


def calc(req: CalcRequest) -> Plan:
    norm = normalize_request(req)
    wagon = load_wagon(norm["wagon_id"])
    # 1.2: штабелируемый груз без известной прочности упаковки — не хватает данных
    unknown = [it for it in norm["items"] if it["stackable"] and it["max_load_on_top"] is None]
    if unknown:
        return _early_plan(
            norm, ResultStatus.NEEDS_DATA, SolverStatus.NOT_APPLICABLE,
            [FailureReason(code="INSUFFICIENT_DATA", objects=[it["type_id"] for it in unknown])],
            NormsStatus.INSUFFICIENT_DATA,
            [{"type_id": it["type_id"], "quantity": it["quantity"],
              "reason": "неизвестна допустимая нагрузка на упаковку (max_load_on_top)"}
             for it in unknown],
        )
    # 3.0б: предварительный анализ выполнимости по режиму цели
    pre = precheck(norm["items"], wagon)
    if apply_goal_mode(pre, GoalMode(norm["goal"])) == "FAILED":
        return _early_plan(
            norm, ResultStatus.FAILED, SolverStatus.INFEASIBLE,
            [FailureReason(code="ПРЕДПРОВЕРКА", objects=[it["type_id"] for it in norm["items"]],
                           value=float(len(norm["items"])))],
            NormsStatus.VIOLATION,
            [{"type_id": it["type_id"], "quantity": it["quantity"], "reason": pre["reason"]}
             for it in norm["items"]],
        )
    items_meta = {it["type_id"]: it for it in norm["items"]}
    # 3.0г: L0 и L1 параллельно, к гейту 1 — оба, выбирается лучший проверенный
    cands = generate_candidates(wagon, norm["items"], norm["time_limit_s"], norm["seed"])
    best_src, placed, solver_status = pick_best(cands, items_meta, wagon)
    plan_source = PlanSource.CATALOG if best_src == "L0" else PlanSource.L1
    # L2 (3.6): слой принимается только если не ухудшает гейт 1 (иначе остаёмся на L0/L1)
    if L2_ENABLED and placed:
        layer = _refine_rest(norm["items"], placed, wagon)
        if len(layer) >= L2_MIN_GAIN:
            combined = placed + layer
            g, _ = validate_gate1(combined, items_meta, wagon, wagon["payload_t"])
            if g == GateStatus.PASSED:
                placed, plan_source = combined, PlanSource.L1_L2
    # 3.7: repair по каталогу кодов §5.1, защита от зацикливания — хэш состояния
    seen: set[int] = set()
    ballast: dict | None = None
    for _ in range(REPAIR_ITERATIONS):
        g1, violations = validate_gate1(placed, items_meta, wagon, wagon["payload_t"])
        if g1 != GateStatus.FAILED:
            break
        new = repair_mod.repair(violations, placed, seen, wagon, items_meta)
        if new is None or new == placed:
            break
        placed = new
    g1, violations = validate_gate1(placed, items_meta, wagon, wagon["payload_t"])
    # п. 6.3.5: если ЦТ не удалось вернуть перестановкой — балластировка вагона
    if {v.code for v in violations} & {"ЦТ_ПРОДОЛЬНОЕ", "ЦТ_ПОПЕРЕЧНОЕ", "ЦТ_ТЕЛЕЖКИ"}:
        from norms.ballast import BALLAST_SIZE_MM, BALLAST_TYPE_ID, ballast_item
        item = ballast_item(placed, items_meta, wagon)
        if item is not None:
            candidate = placed + [item]
            meta_b = dict(items_meta)
            meta_b[BALLAST_TYPE_ID] = {
                "type_id": BALLAST_TYPE_ID, "mass": item["mass"], "stackable": False,
                "max_load_on_top": 0, "length": BALLAST_SIZE_MM[0],
                "width": BALLAST_SIZE_MM[1], "height": BALLAST_SIZE_MM[2],
            }
            g_b, _ = validate_gate1(candidate, meta_b, wagon, wagon["payload_t"])
            if g_b == GateStatus.PASSED:
                placed, items_meta, ballast = candidate, meta_b, item
                g1, violations = validate_gate1(placed, items_meta, wagon, wagon["payload_t"])
    g2, fastening, gate2_violations = check_gate2(placed, wagon, items_meta)
    seq = build_sequence(placed, wagon)
    norms = norms_gate(g1, wagon)
    if ballast is not None:
        fastening = FasteningPlan(
            means=list(fastening.means) + [{
                "type": "балласт",
                "mass_kg": ballast["mass"],
                "x": ballast["x"], "y": ballast["y"],
                "norm_point": "ЦМ-943 гл. 6 п. 6.3.5 (балластировка вагона)",
            }],
            sequence_ok=fastening.sequence_ok,
        )
    total = sum(it["quantity"] for it in norm["items"])
    cargo = [p for p in placed if p["type_id"] != "балласт"]  # балласт — не груз комплекта
    placed_n = len(cargo)
    unplaced = _unplaced(norm["items"], cargo)
    # §3.1 NO_PLAN (ADR-015): солвер доказал неразместимость или не успел —
    # план не достроен, поэтому и гейты, и нормы остаются непроверенными
    if not placed and solver_status in (SolverStatus.INFEASIBLE, SolverStatus.TIMEOUT):
        g1 = GateStatus.NOT_CHECKED
        g2 = GateStatus.NOT_CHECKED
        norms = NormsReport(
            norms_status=NormsStatus.NOT_CHECKED,
            compliance_status=ComplianceStatus.NOT_CHECKED,
            checks=[{"name": "no_plan", "solver_status": solver_status.value}],
        )
        status = ResultStatus.NO_PLAN
        reasons = [FailureReason(code="NO_PLAN", objects=[solver_status.value])]
    # правило §3.1: выдача только при PASSED на гейте 1, гейте 2 и нормативном гейте
    elif g1 != GateStatus.PASSED or g2 == GateStatus.FAILED or norms.norms_status != NormsStatus.PASSED:
        status = ResultStatus.FAILED
        reasons = list(violations) + list(gate2_violations)
    elif placed_n < total and norm["goal"] == GoalMode.FIT_ALL.value:
        status = ResultStatus.FAILED
        reasons = [FailureReason(code="НЕ_ВМЕЩАЕТСЯ", objects=[u["type_id"] for u in unplaced],
                                 value=float(sum(u["quantity"] for u in unplaced)))]
    elif placed_n < total:
        status = ResultStatus.PARTIALLY_PLACED
        reasons = []
    else:
        status = ResultStatus.SUCCESS
        reasons = []
    return Plan(
        plan_id="local",
        wagon_id=norm["wagon_id"],
        placed=seq,
        unplaced=unplaced,
        fastening=fastening,
        norms=norms,
        result_status=status,
        solver_status=solver_status,
        plan_source=plan_source,
        gate1_status=g1,
        gate2_status=g2,
        failure_reason=reasons,
        versions=_versions(norm, solver_status),
    )
