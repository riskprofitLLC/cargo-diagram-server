"""Alembic env: URL из DATABASE_URL или TEST_DATABASE_URL (sqlite для тестов).

Запуск из каталога server/: пакет db не установлен, поэтому добавляем server/
в sys.path (та же конвенция, что в tests/ и tools/)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

from db.models import Base  # noqa: E402
target_metadata = Base.metadata


def run_migrations_online():
    # тесты передают готовое соединение (in-memory sqlite)
    if config.attributes.get("connection") is not None:
        connectable = config.attributes["connection"]
    else:
        connectable = engine_from_config(config.get_section(config.config_ini_section),
                                         prefix="sqlalchemy.", poolclass=pool.NullPool)
    if config.attributes.get("connection") is not None:
        conn = connectable
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with connectable.connect() as conn:
            context.configure(connection=conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()


run_migrations_online()
