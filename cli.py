#!/usr/bin/env python3
"""CLI сквозного скелета (задача 3.0): вход JSON → план JSON."""
import json
import sys

from schemas.models import CalcRequest
from engine.orchestrator import calc


def main():
    req = CalcRequest.model_validate(json.load(open(sys.argv[1], encoding="utf-8")))
    plan = calc(req)
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
