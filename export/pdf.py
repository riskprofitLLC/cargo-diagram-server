"""PDF-эскиз плана (задача 5.1, ADR-011: выбран ReportLab).
Вид сверху + таблица последовательности погрузки, штамп МТУ/НТУ."""
import os

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from schemas.models import Plan
from export.dims import load_cargo_types, load_disclaimer, placed_dims

# Кириллический шрифт (OFL): в образ ставится fonts-dejavu-core (Dockerfile)
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def register_fonts() -> tuple[str, str]:
    """Регистрирует кириллический TTF; без него — Helvetica (текст неполный)."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("PlanSans", path))
            return "PlanSans", "PlanSans"
    return "Helvetica", "Helvetica-Bold"


def pdf_primitives(plan: Plan, wagon: dict) -> dict:
    """Примитивы эскиза (задача 5.1) в координатах вагона (мм).

    Вид сверху: контур вагона, места первого яруса с фактическими габаритами,
    метка общего ЦТ груза, средства крепления из FasteningPlan; вид сбоку —
    высота погрузки и высота кузова. Рендер в PDF — отдельно, чтобы примитивы
    можно было проверить тестом (наличие ЦТ и крепления в эскизе).
    """
    types = load_cargo_types()
    length, width, height = wagon["inner"]["length"], wagon["inner"]["width"], wagon["inner"]["height"]
    rects = [{"role": "wagon", "x": 0, "y": 0, "length": length, "width": width}]
    for p in plan.placed:
        if p.z > 0:
            continue  # вид сверху: первый ярус
        dims = placed_dims(p, types)
        if dims is None:
            continue
        rects.append({"role": "item", "type_id": p.type_id, "index": p.index,
                      "x": p.x, "y": p.y, "length": dims[0], "width": dims[1]})
    # ЦТ груза (формула (1)/(2) ЦМ-943): по массам мест плана
    mass_total = sum((p.mass or 0) for p in plan.placed)
    if mass_total:
        cx = sum((p.mass or 0) * (p.x + (p.length or 0) / 2) for p in plan.placed) / mass_total
        cy = sum((p.mass or 0) * (p.y + (p.width or 0) / 2) for p in plan.placed) / mass_total
    else:
        cx = cy = 0.0
    top = max((p.z + (p.height or 0) for p in plan.placed), default=0)
    fastening = [{"role": "fastening", "type": m.get("type", "крепление"),
                  "gap_mm": m.get("gap_mm"), "required_force_t": m.get("required_force_t"),
                  "x": length / 2, "y": width / 2}
                 for m in plan.fastening.means]
    # продольный разрез (вид сбоку, плоскость XZ): проекции мест на ось X
    side = []
    for p in plan.placed:
        dims = placed_dims(p, types)
        if dims is None:
            continue
        side.append({"role": "side_item", "type_id": p.type_id, "index": p.index,
                     "x": p.x, "z": p.z, "length": dims[0], "height": dims[2]})
    door = wagon.get("door", {})
    return {
        "rects": rects,
        "ct": {"role": "ct", "x": cx, "y": cy, "mass_kg": mass_total},
        "fastening": fastening,
        "side_view": {
            "role": "side_view", "wagon_height_mm": height, "cargo_top_mm": top,
            "items": side,
            "door_x": length / 2, "door_width_mm": door.get("width", 0), "door_height_mm": door.get("height", 0),
        },
        "door": door,
        "dimensions": {"length_mm": length, "width_mm": width},
    }


def plan_to_pdf(plan: Plan, wagon: dict, out_path: str) -> None:
    font, font_bold = register_fonts()
    prim = pdf_primitives(plan, wagon)
    length, width = prim["dimensions"]["length_mm"], prim["dimensions"]["width_mm"]
    c = canvas.Canvas(out_path, pagesize=landscape(A4))
    c.setFont(font, 12)
    c.drawString(40, 560, f"Схема размещения груза, вагон {plan.wagon_id}")
    c.drawString(40, 544, f"Статус: {plan.result_status.value}; источник: {plan.plan_source.value}; мест: {len(plan.placed)}")
    # вид сверху: контур вагона, места 1-го яруса, ЦТ, крепление
    scale = min(500 / length, 200 / width)
    ox, oy = 40, 300
    c.rect(ox, oy, length * scale, width * scale)
    for rect in prim["rects"]:
        if rect["role"] != "item":
            continue
        c.rect(ox + rect["x"] * scale, oy + rect["y"] * scale,
               rect["length"] * scale, rect["width"] * scale)
    ct = prim["ct"]
    if ct["mass_kg"]:
        cx, cy = ox + ct["x"] * scale, oy + ct["y"] * scale
        c.line(cx - 6, cy, cx + 6, cy)
        c.line(cx, cy - 6, cx, cy + 6)
        c.setFont(font, 7)
        c.drawString(cx + 8, cy + 2, f"ЦТ {ct['mass_kg'] / 1000:.1f} т")
    for m in prim["fastening"]:
        fx = ox + m["x"] * scale
        c.setDash(2, 2)
        c.line(fx, oy, fx, oy + width * scale)
        c.setDash()
        c.setFont(font, 7)
        label = m["type"] + (f", усилие {m['required_force_t']} тс" if m.get("required_force_t") else "")
        c.drawString(fx + 3, oy - 10, label)
    # продольный разрез (вид сбоку) под планом: ось X вправо, Z вверх
    sv = prim["side_view"]
    sx0, sy0 = ox, 60
    sscale = min(500 / length, 90 / max(1, sv["wagon_height_mm"]))
    c.rect(sx0, sy0, length * sscale, sv["wagon_height_mm"] * sscale)
    for item in sv["items"]:
        c.rect(sx0 + item["x"] * sscale, sy0 + item["z"] * sscale,
               item["length"] * sscale, item["height"] * sscale)
    # дверной проём посередине борта (виден в разрезе)
    c.setDash(2, 2)
    c.line(sx0 + (sv["door_x"] - sv["door_width_mm"] / 2) * sscale, sy0,
           sx0 + (sv["door_x"] - sv["door_width_mm"] / 2) * sscale, sy0 + sv["door_height_mm"] * sscale)
    c.line(sx0 + (sv["door_x"] + sv["door_width_mm"] / 2) * sscale, sy0,
           sx0 + (sv["door_x"] + sv["door_width_mm"] / 2) * sscale, sy0 + sv["door_height_mm"] * sscale)
    c.setDash()
    c.setFont(font, 7)
    c.drawString(ox, oy - 20, f"Вид сверху. Длина {length} мм; ширина {width} мм.")
    c.drawString(sx0, sy0 - 10, f"Вид сбоку (продольный разрез): высота погрузки {sv['cargo_top_mm']} мм "
                                 f"при кузове {sv['wagon_height_mm']} мм; дверь {sv['door_width_mm']}×{sv['door_height_mm']} мм посередине борта")
    # таблица последовательности
    c.setFont(font, 8)
    y = 280
    c.drawString(40, y, "№  тип  x  y  z")
    for p in plan.placed:
        if y < 60:
            break  # таблица обрезана по месту листа (полный план — JSON)
        y -= 10
        c.drawString(40, y, f"{p.index}  {p.type_id}  {p.x}  {p.y}  {p.z}")
    full_disclaimer, _short = load_disclaimer()
    c.setFont(font_bold, 9)
    c.drawString(40, 30, full_disclaimer[:120])
    c.drawString(40, 18, full_disclaimer[120:] or "")
    c.save()
