# cargo-diagram server — аудит--версия (только наш код)

Урезанная копия `server/` **только с нашим кодом**: сторонние библиотеки не
копируются, ниже ссылки на них (PyPI/upstream). Размер папки — см. замер внизу.

## Состав

- `app/ engine/ norms/ schemas/ db/ export/` — наше приложение (API, движок, нормы, БД, экспорты);
- `data/` — сид-данные (вагоны, нормы, схемы, типы грузов);
- `alembic/` + `alembic.ini` — миграции; `cli.py`, `worker.py` — CLI и воркер;
- `requirements.txt` — зависимости **ссылками**; `Dockerfile` нет (сборка — `pip install -r requirements.txt`);
- `docker-compose.dev.yml`, `nginx.conf` — dev/прод-конфиги; `tests/test_smoke.py` — smoke-тест.

## Зависимости (ссылки вместо кода)

| Пакет | Версия | Ссылка |
|---|---|---|
| packingsolver (ядро L1, MIT) | 0.1.1218 | https://pypi.org/project/packingsolver/ · https://github.com/PackingSolver/PackingSolver |
| FastAPI / uvicorn / Pydantic | 0.115 / 0.32 / 2.9 | pypi.org/project/fastapi, /uvicorn, /pydantic |
| SQLAlchemy / Alembic / psycopg2-binary | 2.0 / 1.13 / 2.9 | pypi.org/project/SQLAlchemy, /alembic, /psycopg2-binary |
| RQ / redis (Valkey) | 1.16 / 5.0 | pypi.org/project/rq, /redis |
| OR-Tools (L2) | 9.15 | pypi.org/project/ortools · github.com/google/or-tools |
| ezdxf (DXF) | 1.3 | pypi.org/project/ezdxf · github.com/mozman/ezdxf |
| ReportLab (PDF) | 4.2 | pypi.org/project/reportlab |

Полная версия со всеми проверками (vendor, tools, docs, тесты, CI) — в основном
репозитории, ветка `main` (папка `server/`).

## Запуск

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q        # smoke
.venv/bin/python cli.py request.json       # CLI: JSON → план
API_KEYS=<sha256> .venv/bin/uvicorn app.main:app --port 8000
```

## Пуш этой папки (сейчас и на будущее)

В внешний репозиторий `git@github.com:riskprofitLLC/cargo-diagram-server.git`
 эта папка живёт в ветке **`audit`** (main — полная server/):

```bash
cd <корень репо>
git subtree split --prefix=server/audit -b audit-push
git push git@github.com:riskprofitLLC/cargo-diagram-server.git audit-push:audit
```

Замер размера: `du -sm server server/audit` (цель — ≤ 40 % от `server/`).
