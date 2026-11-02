"""API /v1 (задачи 4.0а/4.1): POST /calc (синхронно или 202 + job), GET/DELETE
/v1/calc/{id}, /v1/plans/{id}/pdf|dxf, /v1/wagons, POST /v1/validate.
Idempotency-Key: тот же ключ+тело → тот же план; другой тело → 422.
Кэш по хэшу входа (4.3): SUCCESS/PARTIALLY_PLACED.
"""
import json
import os
import uuid

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse

from schemas.models import CalcRequest, Plan, JobState, resolve_dims
from app.auth import require_api_key
from app import jobs
from app.limits import cleanup_artifacts, check_request_limits, check_rate_limit
from engine.orchestrator import calc, load_wagon, available_wagons
from engine.validator import validate_gate1
from export.pdf import plan_to_pdf
from export.dxf import plan_to_dxf

app = FastAPI(title="cargo-diagram server", version="0.1.0")

# CORS для web-панели клиента (ADR-021): разрешённые origins — из env CORS_ORIGINS
# (через запятую), по умолчанию ничего не разрешено (API-only)
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["X-API-Key", "Content-Type", "Idempotency-Key"])

_PLANS: dict[str, Plan] = {}
_OWNERS: dict[str, str] = {}  # plan_id → хэш ключа владельца (4.5: владение объектом)
_SYNC_LIMIT_S = 5  # при превышении — 202 + job
MAX_PLANS_IN_MEMORY = int(os.environ.get("MAX_PLANS_IN_MEMORY", "1000"))  # ретеншн планов в памяти
DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _remember_plan(plan: Plan, owner_key: str = "") -> None:
    """Держит в памяти не больше MAX_PLANS_IN_MEMORY планов (FIFO) — защита от роста."""
    while len(_PLANS) >= MAX_PLANS_IN_MEMORY > 0:
        _PLANS.pop(next(iter(_PLANS)), None)
        _OWNERS.pop(next(iter(_OWNERS)), None)
    _PLANS[plan.plan_id] = plan
    _OWNERS[plan.plan_id] = owner_key


def _owned(plan_id: str, owner_key: str) -> Plan | None:
    """План доступен только своему владельцу (4.5): чужой ключ видит 404."""
    plan = _PLANS.get(plan_id)
    if plan is None or _OWNERS.get(plan_id) != owner_key:
        return None
    return plan


def _copy_for_owner(plan: Plan, owner_key: str) -> Plan:
    """4.3: попадание кэша для другого владельца — копия с новым plan_id и владельцем."""
    copy = plan.model_copy(update={"plan_id": uuid.uuid4().hex[:12]})
    _remember_plan(copy, owner_key)
    from db.audit import record_plan
    record_plan(copy, owner_key)
    return copy


def _run_calc(req: CalcRequest, owner_key: str = "") -> Plan:
    """Расчёт + сохранение. ValueError входа (например wagon_id) → 422."""
    try:
        plan = calc(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan.plan_id = uuid.uuid4().hex[:12]
    _remember_plan(plan, owner_key)
    from db.audit import record_plan
    record_plan(plan, owner_key)  # аудит-трейл 4.6
    return plan


def _item_meta() -> dict[str, dict]:
    """Типоразмеры справочника — единственный источник габаритов для перепроверки."""
    with open(os.path.join(DATA, "cargo_types.json"), encoding="utf-8") as f:
        return {t["type_id"]: t for t in json.load(f)["types"]}


def _placed_with_dims(plan: Plan, meta: dict[str, dict]) -> list[dict]:
    """PlacedItem → dict с габаритами: из плана (ADR-016), иначе из справочника."""
    out, unknown = [], set()
    for p in plan.placed:
        dims = resolve_dims(p, meta)
        if dims is None:
            unknown.add(p.type_id)
            continue
        length, width, height = dims
        out.append(p.model_dump() | {"length": length, "width": width, "height": height})
    if unknown:
        raise HTTPException(422, f"нет габаритов для типоразмеров: {', '.join(sorted(unknown))}")
    return out


@app.middleware("http")
async def structured_logging(request: Request, call_next):
    """Структурный JSON-лог каждого запроса в stdout (6.3): сборка — docker logs/Loki."""
    import json as _json
    import logging as _logging
    import time as _time
    logger = _logging.getLogger("cargo.request")
    t0 = _time.time()
    response = await call_next(request)
    logger.info(_json.dumps({
        "method": request.method, "path": request.url.path,
        "status": response.status_code, "duration_s": round(_time.time() - t0, 3),
    }, ensure_ascii=False))
    return response


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Лимит размера тела запроса (задача 4.7, MAX_BODY_BYTES)."""
    from app import limits
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            too_big = int(declared) > limits.MAX_BODY_BYTES
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "некорректный Content-Length"})
        if too_big:
            return JSONResponse(status_code=413, content={"detail": "тело запроса слишком большое"})
    return await call_next(request)


@app.get("/health")
def health(deep: bool = False) -> dict:
    """Живость; `?deep=1` — ещё и доступность БД (6.3, для алертов)."""
    out = {"status": "ok"}
    if deep:
        from db.engine import get_engine
        eng = get_engine()
        if eng is None:
            out["db"] = "not_configured"
        else:
            try:
                with eng.connect() as conn:
                    conn.exec_driver_sql("SELECT 1")
                out["db"] = "ok"
            except Exception as exc:
                out["status"] = "degraded"
                out["db"] = f"error: {type(exc).__name__}"
    return out


@app.get("/metrics")
def metrics():
    from app.metrics import render
    return PlainTextResponse(render(), media_type="text/plain")


@app.post("/v1/calc")
def post_calc(req: CalcRequest, idempotency_key: str | None = Header(default=None),
              _key: str = Depends(require_api_key)):
    from app.metrics import inc
    inc("http_requests_total")
    err = check_request_limits(req)  # 4.7: лимиты входа
    if err:
        inc("http_4xx_total")
        raise HTTPException(422, err)
    rl = check_rate_limit(_key)  # 4.5: rate limit по ключу
    if rl:
        inc("http_429_total")
        raise HTTPException(429, rl)
    cleanup_artifacts()  # ретеншн артефактов (ADR-012)
    req_dict = req.model_dump(mode="json")
    # 4.1: Idempotency-Key — область действия «тот же ключ + то же тело → тот же
    # план, другое тело → 422» (срок хранения — пока живёт in-memory хранилище)
    if idempotency_key:
        import hashlib as _hl
        body_hash = _hl.sha256(json.dumps(req_dict, sort_keys=True).encode()).hexdigest()
        seen = jobs.idempotency_body_hash(idempotency_key)
        if seen is not None and seen != body_hash:
            inc("http_4xx_total")
            raise HTTPException(422, "Idempotency-Key уже использован с другим телом запроса")
        jobs.remember_idempotency(idempotency_key, body_hash)
    ckey = jobs.cache_key({"req": req_dict, "wagon": req.wagon_id})  # 4.3: + версии/конфиг
    hit = jobs.get_cached(ckey)
    if hit is not None:
        if not isinstance(hit, str):
            # план из БД: отдаём копию со своим plan_id/владельцем (4.3/4.5)
            inc(f"calc_result_{hit.result_status.value}")
            return _copy_for_owner(hit, _key)
        cached = _owned(hit, _key)
        if cached is not None:
            return cached  # in-memory попадание своего владельца
        if hit in _PLANS:
            # план другого владельца — копия с новым владельцем (4.3)
            inc(f"calc_result_{_PLANS[hit].result_status.value}")
            return _copy_for_owner(_PLANS[hit], _key)
        # план вытеснен из памяти — считаем промахом и пересчитываем
    if req.time_limit_s <= _SYNC_LIMIT_S:
        plan = _run_calc(req, _key)
        inc(f"calc_result_{plan.result_status.value}")
        if plan.result_status.value in ("SUCCESS", "PARTIALLY_PLACED"):
            jobs.put_cache(ckey, plan)  # 4.3: кэшируем только эти статусы (INFEASIBLE доказанный — в db.cache при наличии)
        return plan
    # долгий расчёт: 202 + job в очередь (4.4); без Valkey — in-memory fallback
    from app.queue import enqueue_calc, is_rq
    jid = enqueue_calc(req_dict, owner_key=_key)
    if not is_rq():
        plan = _run_calc(req, _key)
        jobs.set_job(jid, JobState.DONE, plan=plan.plan_id)
        if plan.result_status.value in ("SUCCESS", "PARTIALLY_PLACED"):
            jobs.put_cache(ckey, plan)
        return JSONResponse(status_code=202, content={"job_id": jid, "job_state": "done",
                                                      "plan_id": plan.plan_id})
    return JSONResponse(status_code=202, content={"job_id": jid, "job_state": "queued"})


@app.get("/v1/calc/{job_id}")
def get_calc(job_id: str, _key: str = Depends(require_api_key)):
    job = jobs.get_job(job_id)
    if job is None:
        # задание в RQ (воркер в другом процессе): статус и результат — из очереди
        from app.queue import rq_job_status
        rq = rq_job_status(job_id)
        if rq is not None:
            if rq.get("owner") not in ("", _key):
                raise HTTPException(404, "не найдено")  # чужое задание RQ (4.5/4.8)
            rq.pop("owner", None)
            return rq
        plan = _owned(job_id, _key)  # возможно, передан plan_id
        if plan is None:
            raise HTTPException(404, "не найдено")
        return plan
    if job.get("owner") not in (None, _key):
        raise HTTPException(404, "не найдено")  # чужое задание
    out = {"job_id": job_id, "job_state": job["state"].value}
    if job["plan"]:
        plan = _owned(job["plan"], _key)  # план мог быть вытеснен из памяти (ретеншн)
        out["plan"] = plan.model_dump(mode="json") if plan else None
    return out


@app.delete("/v1/calc/{job_id}")
def cancel_calc(job_id: str, _key: str = Depends(require_api_key)):
    job = jobs.get_job(job_id)
    if job is None or job.get("owner") not in (None, _key):
        raise HTTPException(404)
    jobs.set_job(job_id, JobState.CANCELLED)
    return {"job_id": job_id, "job_state": "cancelled"}


@app.post("/v1/validate")
def validate_plan(plan: Plan, _key: str = Depends(require_api_key)):
    """Диагноз плана пользователя: гейт 1 перепроверяется, VIOLATION допустим."""
    try:
        wagon = load_wagon(plan.wagon_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    meta = _item_meta()
    placed = _placed_with_dims(plan, meta)
    g1, violations = validate_gate1(placed, meta, wagon, wagon["payload_t"])
    return {"gate1_status": g1.value, "violations": [v.model_dump() for v in violations]}


@app.get("/v1/audit/plans")
def audit_plans(_key: str = Depends(require_api_key)):
    """Аудит-трейл 4.6: история расчётов (своего владельца)."""
    from db.audit import list_plans
    return list_plans(owner_key=_key)


@app.get("/v1/wagons")
def list_wagons_endpoint(_key: str = Depends(require_api_key)) -> list[str]:
    return available_wagons()


@app.get("/v1/schemes")
def list_schemes(_key: str = Depends(require_api_key)) -> list[dict]:
    """Каталог типовых схем (задача 4.1): id, название, условия применимости."""
    from engine.catalog import load_schemes
    return [{"scheme_id": s["scheme_id"], "name": s["name"],
             "applicability": s.get("applicability", {}), "source": s.get("source", "")}
            for s in load_schemes()]


@app.get("/v1/norms/revisions")
def norms_revisions(_key: str = Depends(require_api_key)) -> dict:
    """Редакции нормативов, на которых построен расчёт (задачи 1.10/4.1)."""
    from tools.check_revisions import KNOWN, check
    return {"report": check(), "documents": {k: v["note"] for k, v in KNOWN.items()}}


@app.get("/v1/plans/{plan_id}/pdf")
def plan_pdf(plan_id: str, _key: str = Depends(require_api_key)):
    plan = _owned(plan_id, _key)
    if plan is None:
        raise HTTPException(404, "план не найден")
    path = f"/tmp/plan-{plan_id}.pdf"
    plan_to_pdf(plan, load_wagon(plan.wagon_id), path)
    return FileResponse(path, media_type="application/pdf")


@app.get("/v1/plans/{plan_id}/dxf")
def plan_dxf(plan_id: str, _key: str = Depends(require_api_key)):
    plan = _owned(plan_id, _key)
    if plan is None:
        raise HTTPException(404, "план не найден")
    path = f"/tmp/plan-{plan_id}.dxf"
    plan_to_dxf(plan, load_wagon(plan.wagon_id), path)
    return FileResponse(path, media_type="application/dxf")
