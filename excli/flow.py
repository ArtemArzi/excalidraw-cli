"""Flow builder — create flowcharts from simple text notation.

One CLI call replaces 10-15 MCP calls.

Notation: "Step A -> Step B -> Step C"
  Creates auto-sized boxes for each step, connected by arrows.

Supports:
  "A -> B -> C"     arrow separator
  "A | B | C"       pipe separator
  "A\\nB\\nC"       newline separator (vertical by default)
"""

from excli.backend import batch_create, clear_canvas
from excli.elements import (
    DEFAULT_BOX_W, DEFAULT_BOX_H, DEFAULT_PADDING, DEFAULT_FONT_SIZE,
    DEFAULT_FONT_FAMILY, _center_text_in_box, auto_box_size, _make_id,
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


def parse_flow(text: str) -> list[str]:
    """Parse flow notation into step names.

    Supports:
      "A -> B -> C"  (arrow separator)
      "A | B | C"    (pipe separator)
      "A\\nB\\nC"    (newline separator)
    """
    if " -> " in text:
        return [s.strip() for s in text.split(" -> ") if s.strip()]
    if " | " in text:
        return [s.strip() for s in text.split(" | ") if s.strip()]
    return [s.strip() for s in text.strip().split("\n") if s.strip()]


def build_flow(
    steps: list[str],
    direction: str = "horizontal",
    palette: str = "default",
    start_x: float = 100,
    start_y: float = 100,
    box_w: float | None = None,
    box_h: float | None = None,
    gap: float = DEFAULT_PADDING,
    do_clear: bool = False,
) -> list[dict]:
    """Build a complete flowchart from a list of step names.

    Auto-sizes boxes to fit text. Uses uniform height (horizontal)
    or uniform width (vertical) for visual consistency.
    """
    if do_clear:
        clear_canvas()

    pal = PALETTES.get(palette, PALETTES["default"])
    colors = pal["bg"]
    stroke = pal["stroke"]

    # Compute sizes for each step
    step_sizes: list[tuple[float, float]] = []
    for step in steps:
        w, h = auto_box_size(step, DEFAULT_FONT_SIZE, DEFAULT_BOX_W, DEFAULT_BOX_H)
        step_sizes.append((box_w or w, box_h or h))

    # Uniform cross-axis size for visual consistency
    if direction == "horizontal":
        uniform_h = max(h for _, h in step_sizes)
        step_sizes = [(w, uniform_h) for w, _ in step_sizes]
    else:
        uniform_w = max(w for w, _ in step_sizes)
        step_sizes = [(uniform_w, h) for _, h in step_sizes]

    elements: list[dict] = []
    box_ids: list[str] = []

    cx, cy = start_x, start_y

    for i, step in enumerate(steps):
        bid = _make_id("box")
        tid = _make_id("txt")
        box_ids.append(bid)

        bw, bh = step_sizes[i]
        bg = colors[i % len(colors)]

        elements.append({
            "id": bid,
            "type": "rectangle",
            "x": cx,
            "y": cy,
            "width": bw,
            "height": bh,
            "backgroundColor": bg,
            "strokeColor": stroke,
            "roughness": 1,
        })
        tx, ty = _center_text_in_box(cx, cy, bw, bh, step, DEFAULT_FONT_SIZE)
        elements.append({
            "id": tid,
            "type": "text",
            "x": tx,
            "y": ty,
            "text": step,
            "fontSize": DEFAULT_FONT_SIZE,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": stroke,
            "textAlign": "center",
        })

        if direction == "horizontal":
            cx += bw + gap
        else:
            cy += bh + gap

    # Arrows between consecutive boxes
    for i in range(len(box_ids) - 1):
        elements.append({
            "id": _make_id("arr"),
            "type": "arrow",
            "x": 0,
            "y": 0,
            "strokeColor": stroke,
            "start": {"id": box_ids[i]},
            "end": {"id": box_ids[i + 1]},
            "endArrowhead": "arrow",
        })

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
