"""DXF-экспорт плана (задача 5.2, ADR-008/008а): вид сверху, прямоугольники
грузов 1-го яруса; кириллица — через отдельный текстовый стиль с TTF."""
import ezdxf

from schemas.models import Plan
from export.dims import load_cargo_types, load_disclaimer, placed_dims

CYR_STYLE = "CYR"
CYR_FONT = "DejaVuSans.ttf"  # шрифт в образ ставится пакетом fonts-dejavu-core


def _ensure_cyr_style(doc) -> None:
    """Стиль для кириллицы (ADR-008а): без него САПР не отобразит русский текст."""
    if not doc.styles.has_entry(CYR_STYLE):
        doc.styles.add(CYR_STYLE, font=CYR_FONT)


def plan_to_dxf(plan: Plan, wagon: dict, out_path: str) -> None:
    types = load_cargo_types()
    doc = ezdxf.new("R2010")  # ADR-008: Unicode-совместимая версия
    _ensure_cyr_style(doc)
    msp = doc.modelspace()
    L, W = wagon["inner"]["length"], wagon["inner"]["width"]
    msp.add_lwpolyline([(0, 0), (L, 0), (L, W), (0, W)], close=True)
    for p in plan.placed:
        if p.z > 0:
            continue  # вид сверху: только первый ярус
        dims = placed_dims(p, types)
        if dims is None:
            continue  # тип вне справочника — место не рисуем, но оно есть в плане
        ln, w = dims[0], dims[1]
        msp.add_lwpolyline(
            [(p.x, p.y), (p.x + ln, p.y), (p.x + ln, p.y + w), (p.x, p.y + w)],
            close=True,
        )
        msp.add_text(str(p.index), height=100, dxfattribs={"style": CYR_STYLE}).set_placement(
            (p.x + ln / 2, p.y + w / 2)
        )
    # дисклеймер (2.7, 4.8в) — текст из сид-данных (задача 1.6б)
    full_disclaimer, _short = load_disclaimer()
    msp.add_text(full_disclaimer, height=60, dxfattribs={"style": CYR_STYLE}).set_placement((0, -300))
    doc.saveas(out_path)
