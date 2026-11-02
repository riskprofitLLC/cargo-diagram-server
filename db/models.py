"""SQLAlchemy-модели (этап 1/4): вагоны, схемы, нормы, планы, задания."""
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Wagon(Base):
    __tablename__ = "wagons"
    wagon_id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON)  # полный JSON модели вагона
    source: Mapped[str] = mapped_column(String, default="")


class Scheme(Base):
    __tablename__ = "schemes"
    scheme_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String, default="")


class NormTable(Base):
    __tablename__ = "norm_tables"
    doc: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class PlanRow(Base):
    __tablename__ = "plans"
    plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    wagon_id: Mapped[str] = mapped_column(ForeignKey("wagons.wagon_id"))
    owner_key: Mapped[str] = mapped_column(String, default="")  # хэш API-ключа владельца
    payload: Mapped[dict] = mapped_column(JSON)
    created: Mapped[str] = mapped_column(String)


class Job(Base):
    __tablename__ = "jobs"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str]
    plan_id: Mapped[str] = mapped_column(String, ForeignKey("plans.plan_id"), nullable=True)
    error: Mapped[str] = mapped_column(String, nullable=True)


class CalcCache(Base):
    __tablename__ = "calc_cache"
    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.plan_id"))
    created: Mapped[str]
