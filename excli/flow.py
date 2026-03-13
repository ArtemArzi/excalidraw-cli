"""Flow builder — create flowcharts from simple text notation.

This is the main token-saving feature: one CLI call replaces 10-15 MCP calls.

Notation: "Step A -> Step B -> Step C"
  Creates boxes for each step, connected by arrows, auto-laid out horizontally.

Notation with newlines (vertical):
  "Step A
   Step B
   Step C"
  Creates a vertical flow.
"""

from excli.backend import batch_create, clear_canvas
from excli.elements import (
    DEFAULT_BOX_W, DEFAULT_BOX_H, DEFAULT_PADDING, DEFAULT_FONT_SIZE,
    DEFAULT_FONT_FAMILY, _center_text_in_box, _apply_theme,
)

# ── Color palettes ──────────────────────────────────────

PALETTES = {
    "default": {
        "bg": ["#a5d8ff", "#b2f2bb", "#ffec99", "#fcc2d7", "#d0bfff", "#c3fae8"],
        "stroke": "#1e1e1e",
    },
    "mono": {
        "bg": ["#e9ecef", "#dee2e6", "#ced4da", "#adb5bd", "#868e96", "#495057"],
        "stroke": "#1e1e1e",
    },
    "warm": {
        "bg": ["#ffd8a8", "#fcc2d7", "#eebefa", "#ffec99", "#ffa8a8", "#d0bfff"],
        "stroke": "#5c3d2e",
    },
    "cool": {
        "bg": ["#a5d8ff", "#b2f2bb", "#c3fae8", "#d0bfff", "#99e9f2", "#c0eb75"],
        "stroke": "#1e1e1e",
    },
}


def _make_id(prefix: str = "f") -> str:
    import time, random
    return f"{prefix}_{int(time.time() * 1000) % 100000}_{random.randint(100, 999)}"


def parse_flow(text: str) -> list[str]:
    """Parse flow notation into step names.

    Supports:
      "A -> B -> C"  (arrow separator)
      "A | B | C"    (pipe separator)
      "A\\nB\\nC"    (newline separator)
    """
    # Try arrow first
    if " -> " in text:
        return [s.strip() for s in text.split(" -> ") if s.strip()]
    if " | " in text:
        return [s.strip() for s in text.split(" | ") if s.strip()]
    # Newline fallback
    return [s.strip() for s in text.strip().split("\n") if s.strip()]


def build_flow(
    steps: list[str],
    direction: str = "horizontal",
    palette: str = "default",
    start_x: float = 100,
    start_y: float = 100,
    box_w: float = DEFAULT_BOX_W,
    box_h: float = DEFAULT_BOX_H,
    gap: float = DEFAULT_PADDING,
    do_clear: bool = False,
) -> list[dict]:
    """Build a complete flowchart from a list of step names.

    Returns the list of created elements.
    """
    if do_clear:
        clear_canvas()

    pal = PALETTES.get(palette, PALETTES["default"])
    colors = pal["bg"]
    stroke = pal["stroke"]

    elements: list[dict] = []
    box_ids: list[str] = []

    for i, step in enumerate(steps):
        bid = _make_id("box")
        tid = _make_id("txt")
        box_ids.append(bid)

        if direction == "horizontal":
            bx = start_x + i * (box_w + gap)
            by = start_y
        else:
            bx = start_x
            by = start_y + i * (box_h + gap)

        bg = colors[i % len(colors)]

        elements.append(_apply_theme({
            "id": bid,
            "type": "rectangle",
            "x": bx,
            "y": by,
            "width": box_w,
            "height": box_h,
            "backgroundColor": bg,
            "strokeColor": stroke,
        }))
        tx, ty = _center_text_in_box(bx, by, box_w, box_h, step, DEFAULT_FONT_SIZE)
        elements.append(_apply_theme({
            "id": tid,
            "type": "text",
            "x": tx,
            "y": ty,
            "text": step,
            "fontSize": DEFAULT_FONT_SIZE,
            "strokeColor": stroke,
            "textAlign": "center",
        }))

    # Arrows between consecutive boxes
    for i in range(len(box_ids) - 1):
        elements.append(_apply_theme({
            "id": _make_id("arr"),
            "type": "arrow",
            "x": 0,
            "y": 0,
            "strokeColor": stroke,
            "start": {"id": box_ids[i]},
            "end": {"id": box_ids[i + 1]},
            "endArrowhead": "arrow",
        }))

    return batch_create(elements)


def build_flow_from_text(
    text: str,
    direction: str = "horizontal",
    palette: str = "default",
    do_clear: bool = False,
) -> list[dict]:
    """Parse text notation and build the flow. Main entry point."""
    steps = parse_flow(text)
    if not steps:
        raise ValueError(f"Could not parse any steps from: {text!r}")
    return build_flow(steps, direction=direction, palette=palette, do_clear=do_clear)
