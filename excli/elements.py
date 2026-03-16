"""High-level element builders for Excalidraw.

These functions create composite elements (box with label, arrow between shapes)
in a single call, reducing what would be 3-5 MCP tool calls to one CLI command.
"""

from excli.backend import (
    batch_create, create_element, list_elements, delete_element,
)

# ── Defaults ────────────────────────────────────────────

DEFAULT_BOX_W = 200
DEFAULT_BOX_H = 80
DEFAULT_FONT_SIZE = 20
DEFAULT_FONT_FAMILY = 2  # Helvetica
DEFAULT_STROKE = "#1e1e1e"
DEFAULT_BG = "transparent"
DEFAULT_PADDING = 40  # space between boxes in auto-layout

# Text measurement calibration for Helvetica.
# Excalidraw text x,y = TOP-LEFT of the text bounding box.
# We must manually center: text_x = box_x + (box_w - text_w) / 2
_CHAR_WIDTH_FACTOR = 0.72   # avg char width at fontSize=1 (Helvetica, tuned for Cyrillic)
_LINE_HEIGHT_FACTOR = 1.35  # line height at fontSize=1
_TEXT_PADDING = 20           # min padding inside shape


def _make_id(prefix: str = "el") -> str:
    import time, random
    return f"{prefix}_{int(time.time() * 1000) % 100000}_{random.randint(100, 999)}"


def estimate_text_size(text: str, font_size: float = DEFAULT_FONT_SIZE) -> tuple[float, float]:
    """Estimate pixel width and height for a text string."""
    lines = text.split("\n")
    max_chars = max(len(line) for line in lines) if lines else 0
    w = max_chars * font_size * _CHAR_WIDTH_FACTOR
    h = len(lines) * font_size * _LINE_HEIGHT_FACTOR
    return w, h


def auto_box_size(
    text: str,
    font_size: float = DEFAULT_FONT_SIZE,
    min_w: float = 120,
    min_h: float = 50,
    shape: str = "rectangle",
) -> tuple[float, float]:
    """Calculate box size that fits the text with padding."""
    tw, th = estimate_text_size(text, font_size)
    w = max(min_w, tw + _TEXT_PADDING * 2)
    h = max(min_h, th + _TEXT_PADDING * 2)
    if shape == "diamond":
        # Inscribed rectangle of a diamond ≈ w*0.5 x h*0.5
        w = max(w * 2.0, min_w * 1.6)
        h = max(h * 2.0, min_h * 1.6)
    elif shape == "ellipse":
        w = max(w * 1.4, min_w * 1.2)
        h = max(h * 1.4, min_h * 1.2)
    return w, h


def _center_text_in_box(
    box_x: float, box_y: float, box_w: float, box_h: float,
    text: str, font_size: float, shape: str = "rectangle",
) -> tuple[float, float]:
    """Calculate text top-left position so it's visually centered in the box.

    Excalidraw text x,y = top-left corner of the text bounding box.
    For all shapes (including diamonds), we center within the bounding box.
    Diamond shapes are already enlarged by auto_box_size() to compensate.
    """
    tw, th = estimate_text_size(text, font_size)
    tx = box_x + (box_w - tw) / 2
    ty = box_y + (box_h - th) / 2
    return tx, ty


# ── Box (rectangle + centered label) ──────────────────

def make_box(
    text: str,
    x: float = 0,
    y: float = 0,
    w: float | None = None,
    h: float | None = None,
    bg: str = DEFAULT_BG,
    stroke: str = DEFAULT_STROKE,
    shape: str = "rectangle",
    font_size: float = DEFAULT_FONT_SIZE,
    box_id: str | None = None,
    text_id: str | None = None,
    opacity: int = 100,
    fill_style: str | None = None,
    roughness: int = 1,
    stroke_width: float | None = None,
    font_family: int | None = None,
    roundness: dict | float | None = None,
) -> list[dict]:
    """Create a shape with centered text inside."""
    box_el, text_el, _, _ = box_elements(
        text=text, x=x, y=y, w=w, h=h, bg=bg, stroke=stroke,
        shape=shape, font_size=font_size, box_id=box_id, text_id=text_id,
        opacity=opacity, fill_style=fill_style, roughness=roughness,
        stroke_width=stroke_width, font_family=font_family, roundness=roundness,
    )
    return batch_create([box_el, text_el])


# ── Raw elements for batch (no API call) ────────────────

def box_elements(
    text: str,
    x: float = 0,
    y: float = 0,
    w: float | None = None,
    h: float | None = None,
    bg: str = DEFAULT_BG,
    stroke: str = DEFAULT_STROKE,
    shape: str = "rectangle",
    font_size: float = DEFAULT_FONT_SIZE,
    box_id: str | None = None,
    text_id: str | None = None,
    opacity: int = 100,
    fill_style: str | None = None,
    roughness: int = 1,
    stroke_width: float | None = None,
    font_family: int | None = None,
    roundness: dict | float | None = None,
) -> tuple[dict, dict, float, float]:
    """Return (box_el, text_el, width, height) without calling the API."""
    bid = box_id or _make_id("box")
    tid = text_id or _make_id("txt")

    if w is None or h is None:
        auto_w, auto_h = auto_box_size(text, font_size, shape=shape)
        w = w or auto_w
        h = h or auto_h

    tx, ty = _center_text_in_box(x, y, w, h, text, font_size, shape=shape)

    resolved_font = font_family if font_family is not None else DEFAULT_FONT_FAMILY

    box_el: dict = {
        "id": bid,
        "type": shape,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "backgroundColor": bg,
        "strokeColor": stroke,
        "roughness": roughness,
    }
    if opacity != 100:
        box_el["opacity"] = opacity
    if fill_style is not None:
        box_el["fillStyle"] = fill_style
    if stroke_width is not None:
        box_el["strokeWidth"] = stroke_width
    if roundness is not None:
        if isinstance(roundness, (int, float)):
            box_el["roundness"] = {"type": 3, "value": roundness}
        else:
            box_el["roundness"] = roundness

    text_el: dict = {
        "id": tid,
        "type": "text",
        "x": tx,
        "y": ty,
        "text": text,
        "fontSize": font_size,
        "fontFamily": resolved_font,
        "strokeColor": stroke,
        "textAlign": "center",
    }
    if opacity != 100:
        text_el["opacity"] = opacity

    return box_el, text_el, w, h


# ── Arrow between two element IDs ──────────────────────

def make_arrow(
    from_id: str,
    to_id: str,
    label: str | None = None,
    stroke: str = DEFAULT_STROKE,
    style: str = "solid",
    start_arrowhead: str | None = None,
    end_arrowhead: str = "arrow",
    stroke_width: float | None = None,
    opacity: int | None = None,
    elbowed: bool = False,
) -> list[dict]:
    """Create an arrow connecting two elements by ID."""
    arr = arrow_element(
        from_id, to_id, stroke=stroke, style=style,
        start_arrowhead=start_arrowhead, end_arrowhead=end_arrowhead,
        stroke_width=stroke_width, opacity=opacity, elbowed=elbowed,
    )
    elements = [arr]

    if label:
        elements.append({
            "id": _make_id("albl"),
            "type": "text",
            "x": 0,
            "y": 0,
            "text": label,
            "fontSize": 16,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": stroke,
        })

    return batch_create(elements)


def arrow_element(
    from_id: str,
    to_id: str,
    stroke: str = DEFAULT_STROKE,
    style: str = "solid",
    arrow_id: str | None = None,
    start_arrowhead: str | None = None,
    end_arrowhead: str = "arrow",
    stroke_width: float | None = None,
    opacity: int | None = None,
    elbowed: bool = False,
) -> dict:
    """Return a raw arrow dict without calling the API."""
    el: dict = {
        "id": arrow_id or _make_id("arr"),
        "type": "arrow",
        "x": 0,
        "y": 0,
        "strokeColor": stroke,
        "strokeStyle": style,
        "start": {"id": from_id},
        "end": {"id": to_id},
        "endArrowhead": end_arrowhead,
    }
    if start_arrowhead is not None:
        el["startArrowhead"] = start_arrowhead
    if stroke_width is not None:
        el["strokeWidth"] = stroke_width
    if opacity is not None:
        el["opacity"] = opacity
    if elbowed:
        el["elbowed"] = True
    return el


# ── Text ────────────────────────────────────────────────

def make_text(
    text: str,
    x: float = 0,
    y: float = 0,
    size: float = DEFAULT_FONT_SIZE,
    color: str = DEFAULT_STROKE,
) -> dict:
    """Create a standalone text element."""
    return create_element({
        "type": "text",
        "x": x,
        "y": y,
        "text": text,
        "fontSize": size,
        "fontFamily": DEFAULT_FONT_FAMILY,
        "strokeColor": color,
    })
