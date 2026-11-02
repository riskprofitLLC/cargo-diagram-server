"""Smoke-тест аудит--версии: сквозной расчёт и auth API."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["API_KEYS"] = hashlib.sha256(b"smoke").hexdigest()

from schemas.models import CalcRequest
from engine.orchestrator import calc


def test_end_to_end_calc():
    plan = calc(CalcRequest.model_validate({
        "wagon_id": "11-217", "goal": "max_fit", "time_limit_s": 3, "seed": 1,
        "items": [{"type_id": "b", "length": 600, "width": 400, "height": 400,
                   "mass": 20, "quantity": 10, "stackable": True, "max_load_on_top": 200}]}))
    assert plan.result_status in ("SUCCESS", "PARTIALLY_PLACED")
    assert len(plan.placed) == 10
    assert plan.gate1_status.value == "PASSED"


def test_api_requires_key():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    req = {"wagon_id": "11-217", "goal": "max_fit", "time_limit_s": 3,
           "items": [{"type_id": "b", "length": 600, "width": 400, "height": 400,
                      "mass": 20, "quantity": 5, "stackable": True, "max_load_on_top": 200}]}
    assert c.post("/v1/calc", json=req).status_code == 401
    r = c.post("/v1/calc", headers={"X-API-Key": "smoke"}, json=req)
    assert r.status_code == 200 and r.json()["result_status"] in ("SUCCESS", "PARTIALLY_PLACED")
