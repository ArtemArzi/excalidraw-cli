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


# ── Themes ─────────────────────────────────────────────
# Each theme is a dict of Excalidraw element properties.
# Properties are merged into elements at creation time.

THEMES: dict[str, dict] = {
    "default": {
        # Current behavior — Helvetica, hand-drawn, solid fill
        "roughness": 1,
        "fontFamily": 2,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roundness": None,
    },
    "sketch": {
        # Classic Excalidraw hand-drawn look
        "roughness": 2,
        "fontFamily": 1,  # Virgil (hand-drawn font)
        "fillStyle": "hachure",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roundness": None,
    },
    "clean": {
        # Polished, modern — no roughness, rounded corners
        "roughness": 0,
        "fontFamily": 2,  # Helvetica
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roundness": {"type": 3},
    },
    "bold": {
        # Heavy strokes, solid, no roughness
        "roughness": 0,
        "fontFamily": 2,
        "fillStyle": "solid",
        "strokeWidth": 4,
        "strokeStyle": "solid",
        "roundness": {"type": 3},
    },
    "minimal": {
        # Thin lines, clean, no fill
        "roughness": 0,
        "fontFamily": 2,
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roundness": {"type": 3},
    },
    "blueprint": {
        # Technical drawing — monospace font, dashed
        "roughness": 0,
        "fontFamily": 3,  # Cascadia (monospace)
        "fillStyle": "cross-hatch",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roundness": None,
    },
    "whiteboard": {
        # Casual whiteboard — hand-drawn, bold
        "roughness": 1,
        "fontFamily": 1,  # Virgil
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roundness": None,
    },
    "dots": {
        # Dotted fill, clean lines
        "roughness": 0,
        "fontFamily": 2,
        "fillStyle": "dots",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roundness": {"type": 3},
    },
    "dashed": {
        # Dashed strokes, hachure fill
        "roughness": 1,
        "fontFamily": 2,
        "fillStyle": "hachure",
        "strokeWidth": 2,
        "strokeStyle": "dashed",
        "roundness": None,
    },
}

# Active theme — set via set_theme() or --theme flag
_active_theme: dict = THEMES["default"].copy()


def get_theme() -> dict:
    """Return the currently active theme properties."""
    return _active_theme


def set_theme(name: str) -> None:
    """Set the active theme by name. Raises KeyError if unknown."""
    if name not in THEMES:
        available = ", ".join(THEMES.keys())
        raise KeyError(f"Unknown theme '{name}'. Available: {available}")
    _active_theme.clear()
    _active_theme.update(THEMES[name])


def list_themes() -> list[str]:
    """Return list of available theme names."""
    return list(THEMES.keys())


def _apply_theme(el: dict) -> dict:
    """Apply active theme properties to an element dict."""
    theme = get_theme()
    for key, value in theme.items():
        if key == "fontFamily" and el.get("type") != "text":
            continue  # fontFamily only applies to text
        if key not in el:  # don't override explicit values
            el[key] = value
    return el


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
) -> list[dict]:
    """Create a shape with centered text inside."""
    bid = box_id or _make_id("box")
    tid = text_id or _make_id("txt")

    if w is None or h is None:
        auto_w, auto_h = auto_box_size(text, font_size, shape=shape)
        w = w or auto_w
        h = h or auto_h

    tx, ty = _center_text_in_box(x, y, w, h, text, font_size, shape=shape)

    box_el = _apply_theme({
        "id": bid,
        "type": shape,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "backgroundColor": bg,
        "strokeColor": stroke,
    })
    text_el = _apply_theme({
        "id": tid,
        "type": "text",
        "x": tx,
        "y": ty,
        "text": text,
        "fontSize": font_size,
        "strokeColor": stroke,
        "textAlign": "center",
    })

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
) -> tuple[dict, dict, float, float]:
    """Return (box_el, text_el, width, height) without calling the API."""
    bid = box_id or _make_id("box")
    tid = text_id or _make_id("txt")

    if w is None or h is None:
        auto_w, auto_h = auto_box_size(text, font_size, shape=shape)
        w = w or auto_w
        h = h or auto_h

    tx, ty = _center_text_in_box(x, y, w, h, text, font_size, shape=shape)

    box_el = _apply_theme({
        "id": bid,
        "type": shape,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "backgroundColor": bg,
        "strokeColor": stroke,
    })
    text_el = _apply_theme({
        "id": tid,
        "type": "text",
        "x": tx,
        "y": ty,
        "text": text,
        "fontSize": font_size,
        "strokeColor": stroke,
        "textAlign": "center",
    })

    return box_el, text_el, w, h


# ── Arrow between two element IDs ──────────────────────

def make_arrow(
    from_id: str,
    to_id: str,
    label: str | None = None,
    stroke: str = DEFAULT_STROKE,
) -> list[dict]:
    """Create an arrow connecting two elements by ID."""
    arrow_el = _apply_theme({
        "id": _make_id("arr"),
        "type": "arrow",
        "x": 0,
        "y": 0,
        "strokeColor": stroke,
        "start": {"id": from_id},
        "end": {"id": to_id},
        "endArrowhead": "arrow",
    })
    elements = [arrow_el]

    if label:
        elements.append(_apply_theme({
            "id": _make_id("albl"),
            "type": "text",
            "x": 0,
            "y": 0,
            "text": label,
            "fontSize": 16,
            "strokeColor": stroke,
        }))

    return batch_create(elements)


def arrow_element(
    from_id: str,
    to_id: str,
    stroke: str = DEFAULT_STROKE,
    style: str = "solid",
    arrow_id: str | None = None,
) -> dict:
    """Return a raw arrow dict without calling the API."""
    return _apply_theme({
        "id": arrow_id or _make_id("arr"),
        "type": "arrow",
        "x": 0,
        "y": 0,
        "strokeColor": stroke,
        "strokeStyle": style,
        "start": {"id": from_id},
        "end": {"id": to_id},
        "endArrowhead": "arrow",
    })


# ── Text ────────────────────────────────────────────────

def make_text(
    text: str,
    x: float = 0,
    y: float = 0,
    size: float = DEFAULT_FONT_SIZE,
    color: str = DEFAULT_STROKE,
) -> dict:
    """Create a standalone text element."""
    return create_element(_apply_theme({
        "type": "text",
        "x": x,
        "y": y,
        "text": text,
        "fontSize": size,
        "strokeColor": color,
    }))
