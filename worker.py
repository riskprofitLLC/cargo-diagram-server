"""Воркер RQ (задачи 4.0/4.4): расчёт в отдельном процессе, лимиты, retry/poison.

Запуск: `rq worker --url redis://valkey:6379/0 calc`.
Изоляция решателя (4.4): каждое задание RQ выполняется в отдельном work-horse
процессе (fork), убить можно по `WORKER_JOB_TIMEOUT_S`; лимит памяти в проде —
через cgroup контейнера воркера (docker-compose). rlimit внутри процесса
выключен по умолчанию: нативное ядро packingsolver резервирует много
виртуальной памяти, и жёсткий RLIMIT_AS убивает work-horse (signal 6) —
замерено в интеграционном тесте очереди. Включить для ужесточения: SOLVER_RLIMIT=1.

При провале задание повторяется (`WORKER_MAX_RETRIES`), после исчерпания
помечается `retry_exhausted`, «отравленное» задание (ошибка валидации входа) —
`poison` (§3.1).
"""
import os
import resource
import traceback

from schemas.models import CalcRequest, JobState
from engine.orchestrator import calc

MEM_LIMIT_MB = int(os.environ.get("SOLVER_MEM_LIMIT_MB", "512"))
MAX_RETRIES = int(os.environ.get("WORKER_MAX_RETRIES", "3"))
JOB_TIMEOUT_S = int(os.environ.get("WORKER_JOB_TIMEOUT_S", "120"))  # жёсткое убийство


def _apply_limits() -> None:
    """rlimit памяти внутри процесса — только по явному SOLVER_RLIMIT=1.

    По умолчанию изоляция — через work-horse RQ (отдельный процесс на задание)
    и cgroup контейнера; см. docstring модуля.
    """
    if os.environ.get("SOLVER_RLIMIT", "0") != "1":
        return
    mb = MEM_LIMIT_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mb, mb))


def run_calc(payload: dict) -> dict:
    """Точка входа задания RQ. Возвращает JSON плана."""
    _apply_limits()
    req = CalcRequest.model_validate(payload)
    plan = calc(req)
    return plan.model_dump(mode="json")


def job_state_on_failure(retries_left: int, exc: BaseException) -> JobState:
    """Состояние задания после падения: повтор или исчерпание попыток (§3.1).

    «Отравленное» задание (ошибка валидации входа — повтор не поможет) — poison.
    """
    from pydantic import ValidationError
    if isinstance(exc, ValidationError):
        return JobState.POISON
    return JobState.RETRY_EXHAUSTED if retries_left <= 0 else JobState.QUEUED


def retry_config():
    """Конфиг повторов RQ (задача 4.4): 3 попытки, экспоненциальная пауза."""
    from rq import Retry
    return Retry(max=MAX_RETRIES, interval=[10, 30, 60])


def on_job_failure(job, connection, exc_type, exc_value, job_tb) -> None:
    """Обработчик провала задания: пишет состояние в job-хранилище и метрики."""
    from app import jobs as job_store
    from app.metrics import inc
    retries_left = getattr(job, "retries_left", 0)
    state = job_state_on_failure(retries_left, exc_value)
    job_store.set_job(job.id, state, error=str(exc_value))
    inc(f"worker_failures_{state.value}")
    if state == JobState.POISON:
        job_store.set_job(job.id, state,
                          error=f"poison: {traceback.format_exception_only(exc_type, exc_value)[-1].strip()}")
