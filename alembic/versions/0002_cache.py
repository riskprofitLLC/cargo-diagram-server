"""Миграция 0002: таблица кэша расчётов (задача 4.3)."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "calc_cache",
        sa.Column("cache_key", sa.String, primary_key=True),
        sa.Column("plan_id", sa.String, sa.ForeignKey("plans.plan_id"), nullable=False),
        sa.Column("created", sa.String, nullable=False),
    )


def downgrade():
    op.drop_table("calc_cache")
