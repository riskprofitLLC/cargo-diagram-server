"""Очередь расчётов (задача 4.4): RQ на Valkey; fallback — in-memory, если
Valkey недоступен (dev). Возвращает job_id; результат — через get_job."""
import os

from app import jobs

try:
    import redis
    from rq import Queue
    # жёсткие таймауты: недоступный Valkey не должен подвешивать импорт/запрос
    _r = redis.from_url(os.environ.get("VALKEY_URL", "redis://localhost:6379/0"),
                        socket_connect_timeout=0.5, socket_timeout=0.5)
    _r.ping()
    _q = Queue("calc", connection=_r)
    RQ_OK = True
except Exception:
    _q = None
    RQ_OK = False


def enqueue_calc(payload: dict, owner_key: str = "") -> str:
    """Ставит расчёт в очередь (с политикой повторов, 4.4). Возвращает job_id."""
    from app.metrics import set_gauge
    if RQ_OK:
        from worker import retry_config
        try:
            j = _q.enqueue("worker.run_calc", payload, retry=retry_config(),
                           job_timeout=__import__("worker").JOB_TIMEOUT_S,
                           on_failure="worker.on_job_failure",
                           meta={"owner": owner_key})  # владение (4.5): проверяется в get_calc
        except Exception:
            j = _q.enqueue("worker.run_calc", payload, meta={"owner": owner_key})
        set_gauge("queue_depth", float(len(_q)))
        return j.id
    jid = jobs.new_job(owner_key)
    set_gauge("queue_depth", 0.0)
    return jid


def is_rq() -> bool:
    return RQ_OK


def rq_job_status(job_id: str) -> dict | None:
    """Статус и результат задания RQ (4.1): None, если задание неизвестно RQ."""
    if not RQ_OK:
        return None
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=_r)
    except Exception:
        return None
    out = {"job_id": job_id, "job_state": job.get_status(),
           "owner": (job.meta or {}).get("owner", "")}  # владелец для проверки в API
    if job.is_finished and job.result is not None:
        out["plan"] = job.result
    elif job.exc_info:
        out["error"] = job.exc_info[-300:]
    return out
