"""Начальная миграция: таблицы вагонов, схем, норм, планов, заданий."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def _json_type(dialect_name: str | None = None):
    """JSONB для PostgreSQL, обычный JSON для SQLite (тесты)."""
    name = dialect_name or op.get_bind().dialect.name
    if name == "sqlite":
        return sa.JSON()
    return JSONB()


def upgrade():
    op.create_table(
        "wagons",
        sa.Column("wagon_id", sa.String, primary_key=True),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("source", sa.String, server_default=""),
    )
    op.create_table(
        "schemes",
        sa.Column("scheme_id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("data", _json_type(), nullable=False),
        sa.Column("source", sa.String, server_default=""),
    )
    op.create_table(
        "norm_tables",
        sa.Column("doc", sa.String, primary_key=True),
        sa.Column("data", _json_type(), nullable=False),
    )
    op.create_table(
        "plans",
        sa.Column("plan_id", sa.String, primary_key=True),
        sa.Column("wagon_id", sa.String, sa.ForeignKey("wagons.wagon_id"), nullable=False),
        sa.Column("owner_key", sa.String, server_default=""),
        sa.Column("payload", _json_type(), nullable=False),
        sa.Column("created", sa.String, nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String, primary_key=True),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("plan_id", sa.String, sa.ForeignKey("plans.plan_id"), nullable=True),
        sa.Column("error", sa.String, nullable=True),
    )


def downgrade():
    for t in ("jobs", "plans", "norm_tables", "schemes", "wagons"):
        op.drop_table(t)
