"""Pydantic-модели контрактов (задача 1.1, ADR-003 оси статусов §3.1 плана v1.6).

Единицы — целые мм, масса — целые кг (ADR-001).
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Оси статусов (ADR-003) ---
class ResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIALLY_PLACED = "PARTIALLY_PLACED"
    FAILED = "FAILED"
    NEEDS_DATA = "NEEDS_DATA"
    NO_PLAN = "NO_PLAN"


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # L0


class GateStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # только gate2


class NormsStatus(str, Enum):
    PASSED = "PASSED"
    VIOLATION = "VIOLATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_CHECKED = "NOT_CHECKED"  # план не достроен (NO_PLAN) — нормы не проверялись (ADR-015)
    ERROR = "ERROR"


class ComplianceStatus(str, Enum):
    TYPICAL_SCHEME = "TYPICAL_SCHEME"
    NON_TYPICAL = "NON_TYPICAL"
    NOT_CHECKED = "NOT_CHECKED"


class PlanSource(str, Enum):
    CATALOG = "CATALOG"  # L0
    L1 = "L1"
    L1_L2 = "L1+L2"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    POISON = "poison"
    RETRY_EXHAUSTED = "retry_exhausted"


class GoalMode(str, Enum):
    FIT_ALL = "fit_all"  # «вместить всё»: PARTIALLY_PLACED запрещён
    MAX_FIT = "max_fit"  # «максимум вместимого»: допустим unplaced[]


# --- Вход ---
class CargoItem(BaseModel):
    """Типоразмер груза (1.2, 1.5): box, целые мм/кг."""
    type_id: str
    length: int = Field(gt=0)  # мм, ось X (вдоль вагона)
    width: int = Field(gt=0)   # мм, ось Y (поперёк)
    height: int = Field(gt=0)  # мм, ось Z (вверх)
    mass: int = Field(gt=0)    # кг
    quantity: int = Field(gt=0)
    stackable: bool = True
    is_package: bool = False  # транспортный пакет (схема typical-2, задача 1.7)
    max_load_on_top: Optional[int] = None  # кг; None → недостаточно данных (NEEDS_DATA)
    allowed_orientations: list[str] = Field(default_factory=lambda: ["xyz", "xzy"])


class CalcRequest(BaseModel):
    wagon_id: str
    items: list[CargoItem]
    goal: GoalMode = GoalMode.FIT_ALL
    completeness_field: str = Field(default="count")  # count | mass | volume (ADR-002)
    seed: int = 0
    time_limit_s: int = Field(default=30, ge=1, le=600)


class WagonModel(BaseModel):
    """Модель вагона (задача 1.3): контур, дверной проём, запрещённые зоны,
    увязочные устройства, пол, источник данных."""
    wagon_id: str
    type: str
    inner: dict
    door: dict
    floor_height_urg: int
    payload_t: int
    tare_t: int
    tare_ct_mm: Optional[int] = None  # для открытого ПС (табл. 18); ADR-018
    bogie_wheelbase_mm: Optional[int] = None  # база вагона (задача 1.4)
    forbidden_zones: list[dict] = Field(default_factory=list)  # выступы/зоны, куда нельзя
    tie_down_devices: list[dict] = Field(default_factory=list)  # увязочные устройства
    source: str = ""
    source_note: str = ""


# --- Выход ---
class PlacedItem(BaseModel):
    type_id: str
    index: int  # порядковый номер погрузки (от торцов к двери)
    x: int
    y: int
    z: int  # низ груза, мм от уровня пола
    orientation: str
    # габариты/масса места с учётом поворота (ADR-016): план самодостаточен —
    # перепроверка и экспорт не зависят от справочника типоразмеров
    length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mass: Optional[int] = None

    @property
    def dims(self) -> Optional[tuple[int, int, int]]:
        """Габариты места из плана; None — план старого формата (нужен справочник)."""
        if self.length and self.width and self.height:
            return self.length, self.width, self.height
        return None


class UnplacedItem(BaseModel):
    type_id: str
    quantity: int
    reason: str


class FailureReason(BaseModel):
    code: str
    objects: list[str] = Field(default_factory=list)
    value: Optional[float] = None


class FasteningPlan(BaseModel):
    """Ведомость крепления (1.6в, 2.5). MVP: распорные рамы и бруски."""
    means: list[dict] = Field(default_factory=list)
    sequence_ok: bool = True
    tie_points_ok: bool = True  # есть увязочные устройства под растяжки/обвязки (модель вагона 1.3)


class NormsReport(BaseModel):
    norms_status: NormsStatus
    compliance_status: ComplianceStatus
    checks: list[dict] = Field(default_factory=list)  # пункт ТУ + значение + происхождение


class ValidationReport(BaseModel):
    gate1_status: GateStatus
    gate2_status: GateStatus
    violations: list[FailureReason] = Field(default_factory=list)


class Plan(BaseModel):
    plan_id: str
    wagon_id: str
    placed: list[PlacedItem]
    unplaced: list[UnplacedItem] = Field(default_factory=list)
    fastening: FasteningPlan
    norms: NormsReport
    result_status: ResultStatus
    solver_status: SolverStatus
    plan_source: PlanSource
    # оси §3.1: гейты и структурированные причины (обязательны при FAILED/NEEDS_DATA)
    gate1_status: GateStatus = GateStatus.NOT_CHECKED
    gate2_status: GateStatus = GateStatus.NOT_CHECKED
    failure_reason: list[FailureReason] = Field(default_factory=list)
    versions: dict = Field(default_factory=dict)  # модель/ядро/нормы/валидатор/seed/хэш входа


def resolve_dims(item: PlacedItem, catalog: dict[str, dict]) -> Optional[tuple[int, int, int]]:
    """Габариты места (ADR-016): из плана, иначе из справочника с учётом поворота."""
    if item.dims:
        return item.dims
    t = catalog.get(item.type_id)
    if t is None:
        return None
    length, width, height = t["length"], t["width"], t["height"]
    if str(item.orientation).upper().endswith("YXZ"):  # поворот YXZ меняет оси X и Y
        length, width = width, length
    return length, width, height


class OptimizationResult(BaseModel):
    plan: Plan
    validation: ValidationReport
