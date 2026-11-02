"""Job-хранилище и кэш (задачи 4.1/4.3, in-memory MVP; БД — этап 4 с миграциями).

Кэш: ключ = хэш входа + вагон + seed + time_limit. Кэшируются SUCCESS и
PARTIALLY_PLACED; TIMEOUT/ERROR — нет (план 4.3).
"""
import hashlib
import json
import os
import threading
import time

from schemas.models import JobState

_lock = threading.Lock()
_jobs: dict[str, dict] = {}       # job_id -> {state, plan, error, created}
_cache: dict[str, str] = {}       # cache_key -> plan_id
# Ретеншн in-memory хранилищ (ADR-012): FIFO-вытеснение старейшей записи
MAX_JOBS_IN_MEMORY = int(os.environ.get("MAX_JOBS_IN_MEMORY", "1000"))
MAX_CACHE_IN_MEMORY = int(os.environ.get("MAX_CACHE_IN_MEMORY", "1000"))


def _evict_oldest(store: dict, limit: int) -> None:
    while len(store) >= limit > 0:
        store.pop(next(iter(store)), None)


_idem: dict[str, str] = {}  # idempotency_key -> хэш тела запроса (4.1)
MAX_IDEMPOTENCY_IN_MEMORY = int(os.environ.get("MAX_IDEMPOTENCY_IN_MEMORY", "1000"))


def remember_idempotency(key: str, body_hash: str) -> None:
    with _lock:
        _evict_oldest(_idem, MAX_IDEMPOTENCY_IN_MEMORY)
        _idem[key] = body_hash


def idempotency_body_hash(key: str) -> str | None:
    with _lock:
        return _idem.get(key)


def cache_key(req_dict: dict, config: dict | None = None) -> str:
    """Ключ кэша (4.3): вход + вагон + версии ядра/норм/валидатора + конфиг.

    Версии и конфиг обязательны: после смены пина ядра, редакции норм, версии
    валидатора или флага L2 старые записи кэша недействительны.
    """
    payload = {"req": req_dict, "config": config if config is not None else solver_config()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def solver_config() -> dict:
    """Версии и конфиг, влияющие на результат (DoD-3/4.3)."""
    import os
    from engine import orchestrator
    return {
        "solver": orchestrator.SOLVER_PIN,
        "norms": orchestrator.NORMS_EDITION,
        "validator": orchestrator.VALIDATOR_VERSION,
        "l2_enabled": bool(orchestrator.L2_ENABLED),
        "l2_min_gain": orchestrator.L2_MIN_GAIN,
        "repair_iterations": orchestrator.REPAIR_ITERATIONS,
        "packingsolver_mode": os.environ.get("PACKINGSOLVER_MODE", "anytime"),
    }


def get_cached(key: str):
    """Кэш 4.3: сначала БД (с ревалидацией), потом in-memory fallback."""
    from db.cache import get as db_get
    plan = db_get(key, wagon_loader=_wagon_loader)
    if plan is not None:
        return plan
    with _lock:
        return _cache.get(key)


def put_cache(key: str, plan) -> None:
    from db.cache import put as db_put
    try:
        db_put(key, plan)
    except Exception:
        pass  # БД недоступна — in-memory
    with _lock:
        _evict_oldest(_cache, MAX_CACHE_IN_MEMORY)
        _cache[key] = plan.plan_id if hasattr(plan, "plan_id") else plan


def _wagon_loader(wagon_id: str) -> dict:
    from engine.orchestrator import load_wagon
    return load_wagon(wagon_id)


def new_job(owner: str = "") -> str:
    import uuid
    jid = uuid.uuid4().hex[:12]
    with _lock:
        _evict_oldest(_jobs, MAX_JOBS_IN_MEMORY)
        _jobs[jid] = {"state": JobState.QUEUED, "plan": None, "error": None,
                      "created": time.time(), "owner": owner}
    _publish_job_gauges()
    return jid


def set_job(jid: str, state: JobState, plan=None, error=None) -> None:
    with _lock:
        if jid in _jobs:
            _jobs[jid].update(state=state, plan=plan, error=error)
    _publish_job_gauges()


def _publish_job_gauges() -> None:
    """Метрики заданий по состояниям (6.3): jobs_<state>."""
    from app.metrics import set_gauge
    with _lock:
        counts: dict[str, int] = {}
        for job in _jobs.values():
            counts[job["state"].value] = counts.get(job["state"].value, 0) + 1
        set_gauge("jobs_total", float(len(_jobs)))
    for state, value in counts.items():
        set_gauge(f"jobs_{state}", float(value))


def get_job(jid: str) -> dict | None:
    with _lock:
        return _jobs.get(jid)


def store_plan(plan) -> None:
    with _lock:
        _jobs  # plans хранятся отдельно
    from app.main import _PLANS
    _PLANS[plan.plan_id] = plan
