"""Diagram engine — parse YAML, layout (auto/manual/mixed/grid), render to Excalidraw.

YAML format reference:
    title: "Diagram Title"
    direction: TB           # TB (top→bottom) or LR (left→right, default)
    layout: auto             # auto | manual | grid  (default: auto)

    style:                   # diagram-level defaults
      gap: 80                # space between layers
      node_gap: 40           # space between nodes in a layer
      font_size: 18          # default font size

    grid:                    # only for layout: grid
      cols: 3
      row_gap: 40
      col_gap: 60

    sections:                # visual frames around node groups
      sec_id:
        title: "① Section"
        color: "#edf2ff"     # background fill
        border: "#4dabf7"    # stroke color
        padding: 30          # extra space around nodes
        opacity: 40          # 0-100

    nodes:
      key: "Short text"                          # simple string
      key2: {text: "Label", style: blue}         # with style
      key3: {text: "Manual", x: 400, y: 200}    # manual position
      key4: {text: "Custom", w: 300, h: 80}     # custom size
      key5:                                      # full spec
        text: "Full"
        style: green
        shape: diamond       # rectangle | ellipse | diamond
        size: large          # small | normal | large | xl
        font_size: 22
        stroke: "#333"
        stroke_style: dashed # solid | dashed | dotted
        opacity: 80

    edges:
      - [src, dst]
      - [src, dst, {label: "text", color: blue, style: dashed}]

    side:                    # auxiliary dashed connections
      - [src, aux_key, {text: "label", color: gray}]

    notes:
      - "Annotation line 1"
      - "Annotation line 2"
"""

import yaml
from collections import defaultdict, deque

from excli.backend import batch_create, clear_canvas
from excli.elements import (
    box_elements, arrow_element, estimate_text_size, auto_box_size,
    _make_id, _center_text_in_box,
    DEFAULT_FONT_SIZE, DEFAULT_FONT_FAMILY, DEFAULT_STROKE,
)

# ── Color palette ───────────────────────────────────────

STYLE_COLORS = {
    "blue":    "#a5d8ff",
    "green":   "#b2f2bb",
    "yellow":  "#ffec99",
    "orange":  "#ffd8a8",
    "red":     "#ffa8a8",
    "pink":    "#fcc2d7",
    "purple":  "#d0bfff",
    "violet":  "#eebefa",
    "cyan":    "#99e9f2",
    "mint":    "#c3fae8",
    "gray":    "#e9ecef",
    "lime":    "#c0eb75",
    "white":   "#ffffff",
}

EDGE_COLORS = {
    "green":  "#2b8a3e",
    "red":    "#e03131",
    "blue":   "#1971c2",
    "orange": "#e8590c",
    "gray":   "#868e96",
    "black":  "#1e1e1e",
    "purple": "#7048e8",
    "cyan":   "#0c8599",
}

SIZE_PRESETS = {
    "small":  {"font_size": 14, "min_w": 100, "min_h": 40},
    "normal": {"font_size": 18, "min_w": 140, "min_h": 55},
    "large":  {"font_size": 22, "min_w": 180, "min_h": 70},
    "xl":     {"font_size": 26, "min_w": 220, "min_h": 85},
}

SECTION_DEFAULTS = {
    "padding": 30,
    "title_height": 35,
    "title_font_size": 16,
    "border_width": 2,
    "corner_radius": 12,
}

FONT_FAMILIES = {
    "virgil": 1, "hand": 1,
    "helvetica": 2, "sans": 2,
    "cascadia": 3, "mono": 3,
    "excalifont": 5,
    "nunito": 6,
    "lilita": 7,
    "comic": 8,
}


# ── YAML parsing ───────────────────────────────────────

def load_diagram(path: str) -> dict:
    """Load a .excli.yaml diagram file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML dict, got {type(data)}")
    return data


def load_diagram_from_string(text: str) -> dict:
    """Parse a diagram from a YAML string."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML dict, got {type(data)}")
    return data


def save_diagram(path: str, data: dict):
    """Save diagram data back to YAML."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _parse_node(key: str, value) -> dict:
    """Normalize node definition to a dict."""
    if isinstance(value, str):
        return {"text": value}
    if isinstance(value, dict):
        return value
    return {"text": str(value)}


def _parse_edge(item) -> dict:
    """Normalize edge definition.

    Formats:
      [src, dst]
      [src, dst, {label: "...", color: "...", style: "..."}]
      {from: src, to: dst, label: "...", color: "...", style: "..."}
    """
    if isinstance(item, (list, tuple)):
        if len(item) == 2:
            return {"from": item[0], "to": item[1]}
        elif len(item) >= 3:
            opts = item[2] if isinstance(item[2], dict) else {}
            return {"from": item[0], "to": item[1], **opts}
    if isinstance(item, dict):
        return item
    raise ValueError(f"Cannot parse edge: {item}")


# ── Topological layering ───────────────────────────────

def _break_cycles(node_ids: list[str], edges: list[dict]) -> list[dict]:
    """Remove back-edges to make the graph acyclic (DFS-based)."""
    adj: dict[str, list[str]] = defaultdict(list)
    node_set = set(node_ids)
    for e in edges:
        src, dst = e["from"], e["to"]
        if src in node_set and dst in node_set:
            adj[src].append(dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}
    back_edges: set[tuple[str, str]] = set()

    def dfs(u: str):
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                back_edges.add((u, v))
            elif color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for nid in node_ids:
        if color[nid] == WHITE:
            dfs(nid)

    return [e for e in edges if (e["from"], e["to"]) not in back_edges]


def _compute_layers(node_ids: list[str], edges: list[dict]) -> dict[str, int]:
    """Assign each node to a layer using longest-path (Kahn's algorithm)."""
    dag_edges = _break_cycles(node_ids, edges)

    successors: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for e in dag_edges:
        src, dst = e["from"], e["to"]
        if src in in_degree and dst in in_degree:
            successors[src].append(dst)
            in_degree[dst] += 1

    layer: dict[str, int] = {}
    queue = deque()
    for nid in node_ids:
        if in_degree[nid] == 0:
            queue.append(nid)
            layer[nid] = 0

    while queue:
        node = queue.popleft()
        for succ in successors[node]:
            candidate = layer[node] + 1
            if succ not in layer or candidate > layer[succ]:
                layer[succ] = candidate
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    for nid in node_ids:
        if nid not in layer:
            layer[nid] = 0

    return layer


def _order_within_layers(
    node_ids: list[str],
    layers: dict[str, int],
    edges: list[dict],
) -> dict[int, list[str]]:
    """Group nodes by layer and order to minimize edge crossings."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid in node_ids:
        by_layer[layers[nid]].append(nid)

    predecessors: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        predecessors[e["to"]].append(e["from"])

    pos: dict[str, int] = {}
    for layer_num in sorted(by_layer.keys()):
        nodes = by_layer[layer_num]
        if layer_num == 0:
            for i, nid in enumerate(nodes):
                pos[nid] = i
        else:
            def _median_pred_pos(nid, _pos=pos, _pred=predecessors):
                preds = [_pos[p] for p in _pred[nid] if p in _pos]
                if not preds:
                    return 0
                preds.sort()
                return preds[len(preds) // 2]

            nodes.sort(key=_median_pred_pos)
            for i, nid in enumerate(nodes):
                pos[nid] = i
        by_layer[layer_num] = nodes

    return dict(by_layer)


# ── Size computation ──────────────────────────────────

def _compute_sizes(
    nodes: dict[str, dict],
    default_font_size: float = DEFAULT_FONT_SIZE,
) -> dict[str, tuple[float, float]]:
    """Compute (w, h) for each node, respecting manual w/h overrides."""
    sizes: dict[str, tuple[float, float]] = {}
    for nid, node in nodes.items():
        # Full manual size
        if "w" in node and "h" in node:
            sizes[nid] = (float(node["w"]), float(node["h"]))
            continue

        text = node.get("text", nid)
        size_name = node.get("size", "normal")
        preset = SIZE_PRESETS.get(size_name, SIZE_PRESETS["normal"])
        font_size = node.get("font_size", preset["font_size"])
        shape = node.get("shape", "rectangle")

        w, h = auto_box_size(text, font_size, preset["min_w"], preset["min_h"], shape=shape)

        # Partial overrides
        if "w" in node:
            w = float(node["w"])
        if "h" in node:
            h = float(node["h"])

        sizes[nid] = (w, h)
    return sizes


# ── Position assignment (axis-agnostic) ────────────────

def _assign_positions(
    by_layer: dict[int, list[str]],
    sizes: dict[str, tuple[float, float]],
    nodes: dict[str, dict],
    direction: str,
    start_x: float,
    start_y: float,
    layer_gap: float,
    node_gap: float,
) -> dict[str, dict]:
    """Assign x, y to auto-layout nodes.

    Uses axis-agnostic logic:
    - primary axis: direction of layers (x for LR, y for TB)
    - secondary axis: node spread within a layer (y for LR, x for TB)
    """
    if not by_layer:
        return {}

    max_layer = max(by_layer.keys())
    is_tb = direction.upper() == "TB"

    def _primary_size(nid: str) -> float:
        w, h = sizes[nid]
        return h if is_tb else w

    def _secondary_size(nid: str) -> float:
        w, h = sizes[nid]
        return w if is_tb else h

    # Layer thickness along primary axis (max node size in that direction)
    layer_thickness: dict[int, float] = {}
    for lnum, lnodes in by_layer.items():
        layer_thickness[lnum] = max(_primary_size(nid) for nid in lnodes) if lnodes else 0

    # Layer spread along secondary axis (sum of node sizes + gaps)
    layer_spread: dict[int, float] = {}
    for lnum, lnodes in by_layer.items():
        total = sum(_secondary_size(nid) for nid in lnodes) + node_gap * max(0, len(lnodes) - 1)
        layer_spread[lnum] = total

    max_spread = max(layer_spread.values()) if layer_spread else 0

    # Cumulative primary positions
    primary_start = start_y if is_tb else start_x
    layer_primary: dict[int, float] = {}
    pos = primary_start
    for lnum in range(max_layer + 1):
        layer_primary[lnum] = pos
        pos += layer_thickness.get(lnum, 0) + layer_gap

    # Secondary start
    secondary_start = start_x if is_tb else start_y

    # Place each node
    result: dict[str, dict] = {}
    for lnum, lnodes in by_layer.items():
        spread = layer_spread[lnum]
        sec_offset = secondary_start + (max_spread - spread) / 2

        for nid in lnodes:
            w, h = sizes[nid]
            node = nodes[nid]
            thick = layer_thickness[lnum]
            prim = layer_primary[lnum]

            if is_tb:
                ny = _snap(prim + (thick - h) / 2)
                nx = _snap(sec_offset)
                sec_offset += w + node_gap
            else:
                nx = _snap(prim + (thick - w) / 2)
                ny = _snap(sec_offset)
                sec_offset += h + node_gap

            result[nid] = {**node, "x": nx, "y": ny, "w": w, "h": h}

    return result


# ── Grid layout ────────────────────────────────────────

def _assign_grid_positions(
    node_ids: list[str],
    sizes: dict[str, tuple[float, float]],
    nodes: dict[str, dict],
    cols: int,
    start_x: float,
    start_y: float,
    col_gap: float,
    row_gap: float,
) -> dict[str, dict]:
    """Place nodes in a grid with fixed number of columns."""
    if not node_ids:
        return {}

    # Find max cell size
    max_w = max(sizes[nid][0] for nid in node_ids)
    max_h = max(sizes[nid][1] for nid in node_ids)

    result: dict[str, dict] = {}
    for i, nid in enumerate(node_ids):
        row = i // cols
        col = i % cols
        w, h = sizes[nid]

        # Center within cell
        cell_x = start_x + col * (max_w + col_gap)
        cell_y = start_y + row * (max_h + row_gap)
        nx = _snap(cell_x + (max_w - w) / 2)
        ny = _snap(cell_y + (max_h - h) / 2)

        result[nid] = {**nodes[nid], "x": nx, "y": ny, "w": w, "h": h}

    return result


# ── Section bounding boxes ─────────────────────────────

def compute_sections(
    sections_raw: dict,
    layout: dict[str, dict],
    padding: float = SECTION_DEFAULTS["padding"],
    title_height: float = SECTION_DEFAULTS["title_height"],
) -> list[dict]:
    """Compute section bounding boxes from positioned nodes.

    Returns list of {id, title, color, border, opacity, x, y, w, h}.
    """
    result = []

    for sec_id, sec in sections_raw.items():
        sec_nodes = sec.get("nodes", [])
        positions = [layout[nid] for nid in sec_nodes if nid in layout]
        if not positions:
            continue

        pad = sec.get("padding", padding)
        has_title = bool(sec.get("title"))
        th = title_height if has_title else 0

        min_x = min(p["x"] for p in positions)
        min_y = min(p["y"] for p in positions)
        max_x = max(p["x"] + p["w"] for p in positions)
        max_y = max(p["y"] + p["h"] for p in positions)

        result.append({
            "id": sec_id,
            "title": sec.get("title", ""),
            "color": sec.get("color", "#f8f9fa"),
            "border": sec.get("border", "#dee2e6"),
            "opacity": sec.get("opacity", 40),
            "x": min_x - pad,
            "y": min_y - pad - th,
            "w": (max_x - min_x) + pad * 2,
            "h": (max_y - min_y) + pad * 2 + th,
        })

    return result


# ── Grid snapping ─────────────────────────────────────

def _snap(v: float, grid: int = 20) -> float:
    """Snap a value to the nearest grid line."""
    return round(v / grid) * grid


# ── Main layout computation ────────────────────────────

def compute_layout(
    diagram: dict,
    start_x: float = 80,
    start_y: float = 80,
    layer_gap: float | None = None,
    node_gap: float | None = None,
) -> dict[str, dict]:
    """Compute positions and sizes for all nodes.

    Supports:
    - direction: LR (default) or TB
    - layout: auto (topological sort), manual (all x/y), grid, or mixed
    - Per-node w, h, x, y overrides
    - style.gap, style.node_gap for spacing

    Returns {node_id: {x, y, w, h, text, ...node_props}}.
    """
    direction = diagram.get("direction", "LR").upper()
    layout_mode = diagram.get("layout", "auto").lower()
    style = diagram.get("style", {})

    if layer_gap is None:
        layer_gap = style.get("gap", 80)
    if node_gap is None:
        node_gap = style.get("node_gap", 40)

    nodes_raw = diagram.get("nodes", {})
    edges_raw = diagram.get("edges", [])

    node_ids = list(nodes_raw.keys())
    nodes = {k: _parse_node(k, v) for k, v in nodes_raw.items()}

    # Compute sizes
    default_fs = style.get("font_size", DEFAULT_FONT_SIZE)
    sizes = _compute_sizes(nodes, default_font_size=default_fs)

    # Grid layout
    if layout_mode == "grid":
        grid_cfg = diagram.get("grid", {})
        cols = grid_cfg.get("cols", 3)
        col_gap = grid_cfg.get("col_gap", node_gap)
        row_gap = grid_cfg.get("row_gap", node_gap)
        return _assign_grid_positions(
            node_ids, sizes, nodes, cols,
            start_x, start_y, col_gap, row_gap,
        )

    # Manual layout: all nodes must have x, y
    if layout_mode == "manual":
        result: dict[str, dict] = {}
        for nid in node_ids:
            node = nodes[nid]
            w, h = sizes[nid]
            if "x" not in node or "y" not in node:
                raise ValueError(f"Node '{nid}' missing x/y in manual layout mode")
            result[nid] = {**node, "x": float(node["x"]), "y": float(node["y"]), "w": w, "h": h}
        return result

    # Auto / mixed layout
    manual_ids = {nid for nid, n in nodes.items() if "x" in n and "y" in n}
    auto_ids = [nid for nid in node_ids if nid not in manual_ids]

    result = {}

    # Place manual nodes first
    for nid in manual_ids:
        node = nodes[nid]
        w, h = sizes[nid]
        result[nid] = {**node, "x": float(node["x"]), "y": float(node["y"]), "w": w, "h": h}

    # Auto-layout remaining
    if auto_ids:
        main_edges = [_parse_edge(e) for e in edges_raw]
        known = set(node_ids)
        main_edges = [e for e in main_edges if e["from"] in known and e["to"] in known]

        layers = _compute_layers(auto_ids, main_edges)
        by_layer = _order_within_layers(auto_ids, layers, main_edges)

        # Offset auto nodes if manual nodes occupy space
        adj_x, adj_y = start_x, start_y
        if manual_ids:
            max_right = max(result[nid]["x"] + result[nid]["w"] for nid in manual_ids)
            max_bottom = max(result[nid]["y"] + result[nid]["h"] for nid in manual_ids)
            if direction == "LR":
                adj_x = max(start_x, max_right + layer_gap)
            else:
                adj_y = max(start_y, max_bottom + layer_gap)

        auto_result = _assign_positions(
            by_layer, sizes, nodes, direction,
            adj_x, adj_y, layer_gap, node_gap,
        )
        result.update(auto_result)

    return result


# ── Render to Excalidraw elements ──────────────────────

def render_diagram(
    diagram: dict,
    do_clear: bool = False,
    start_x: float = 80,
    start_y: float = 80,
) -> list[dict]:
    """Render a diagram dict to Excalidraw canvas.

    Renders in layer order: sections (back) → title → nodes → edges → side → notes.
    Returns created elements.
    """
    if do_clear:
        clear_canvas()

    title = diagram.get("title")
    effective_start_y = start_y + 50 if title else start_y

    layout = compute_layout(diagram, start_x=start_x, start_y=effective_start_y)

    all_elements: list[dict] = []

    # ── Sections (rendered behind everything) ──────────
    sections_raw = diagram.get("sections", {})
    if sections_raw:
        sections = compute_sections(sections_raw, layout)
        for sec in sections:
            sec_bg_id = _make_id(f"sec_{sec['id']}")
            opacity = sec.get("opacity", 40)

            all_elements.append({
                "id": sec_bg_id,
                "type": "rectangle",
                "x": sec["x"],
                "y": sec["y"],
                "width": sec["w"],
                "height": sec["h"],
                "backgroundColor": sec["color"],
                "strokeColor": sec["border"],
                "strokeWidth": SECTION_DEFAULTS["border_width"],
                "roundness": {"type": 3, "value": SECTION_DEFAULTS["corner_radius"]},
                "opacity": opacity,
                "roughness": 0,
            })

            if sec["title"]:
                all_elements.append({
                    "id": _make_id(f"stl_{sec['id']}"),
                    "type": "text",
                    "x": sec["x"] + 12,
                    "y": sec["y"] + 8,
                    "text": sec["title"],
                    "fontSize": SECTION_DEFAULTS["title_font_size"],
                    "fontFamily": DEFAULT_FONT_FAMILY,
                    "strokeColor": sec["border"],
                })

    # ── Title ──────────────────────────────────────────
    if title:
        all_elements.append({
            "id": _make_id("title"),
            "type": "text",
            "x": start_x,
            "y": start_y - 10,
            "text": title,
            "fontSize": 28,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": DEFAULT_STROKE,
        })

    # ── Nodes ──────────────────────────────────────────
    style_cfg = diagram.get("style", {})
    default_fs = style_cfg.get("font_size", None)
    default_roughness = style_cfg.get("roughness", 1)
    default_fill_style = style_cfg.get("fillStyle", None)
    default_stroke_width = style_cfg.get("strokeWidth", None)
    default_font_family_name = style_cfg.get("fontFamily", None)
    default_font_family = FONT_FAMILIES.get(default_font_family_name, None) if default_font_family_name else None

    for nid, props in layout.items():
        text = props.get("text", nid)
        shape = props.get("shape", "rectangle")
        style_name = props.get("style", "gray")
        bg = STYLE_COLORS.get(style_name, style_name if style_name.startswith("#") else STYLE_COLORS["gray"])
        size_name = props.get("size", "normal")
        preset = SIZE_PRESETS.get(size_name, SIZE_PRESETS["normal"])
        font_size = props.get("font_size", default_fs or preset["font_size"])
        stroke = props.get("stroke", DEFAULT_STROKE)
        stroke_style = props.get("stroke_style", "solid")
        opacity_val = props.get("opacity", 100)
        roundness = props.get("roundness", None)
        link = props.get("link", None)

        # Resolve font family: node-level > diagram-level > default
        node_ff_name = props.get("fontFamily")
        if node_ff_name:
            resolved_font = FONT_FAMILIES.get(node_ff_name, DEFAULT_FONT_FAMILY)
        elif default_font_family is not None:
            resolved_font = default_font_family
        else:
            resolved_font = None  # box_elements will use DEFAULT_FONT_FAMILY

        bid = f"n_{nid}"
        tid = f"t_{nid}"

        box_el, text_el, _, _ = box_elements(
            text=text,
            x=props["x"],
            y=props["y"],
            w=props["w"],
            h=props["h"],
            bg=bg,
            stroke=stroke,
            shape=shape,
            font_size=font_size,
            box_id=bid,
            text_id=tid,
            opacity=opacity_val,
            fill_style=props.get("fillStyle", default_fill_style),
            roughness=props.get("roughness", default_roughness),
            stroke_width=props.get("strokeWidth", default_stroke_width),
            font_family=resolved_font,
            roundness=roundness,
        )

        if stroke_style != "solid":
            box_el["strokeStyle"] = stroke_style
        if link:
            box_el["link"] = {"type": "url", "url": link}

        all_elements.extend([box_el, text_el])

    # ── Main edges ─────────────────────────────────────
    for item in diagram.get("edges", []):
        edge = _parse_edge(item)
        src, dst = edge["from"], edge["to"]
        color_name = edge.get("color", "black")
        stroke = EDGE_COLORS.get(color_name, color_name if color_name.startswith("#") else DEFAULT_STROKE)
        edge_style = edge.get("style", "solid")

        arr = arrow_element(
            f"n_{src}", f"n_{dst}", stroke=stroke, style=edge_style,
            start_arrowhead=edge.get("startArrowhead"),
            end_arrowhead=edge.get("endArrowhead", "arrow"),
            stroke_width=edge.get("strokeWidth"),
            opacity=edge.get("opacity"),
            elbowed=edge.get("elbowed", False),
        )
        all_elements.append(arr)

        label = edge.get("label")
        if label:
            src_props = layout.get(src, {})
            dst_props = layout.get(dst, {})
            if src_props and dst_props:
                mx = (src_props["x"] + src_props["w"] + dst_props["x"]) / 2
                my = (src_props["y"] + src_props["h"] / 2 + dst_props["y"] + dst_props["h"] / 2) / 2 - 20
            else:
                mx, my = 0, 0

            all_elements.append({
                "id": _make_id("elbl"),
                "type": "text",
                "x": mx,
                "y": my,
                "text": label,
                "fontSize": 13,
                "fontFamily": DEFAULT_FONT_FAMILY,
                "strokeColor": stroke,
            })

    # ── Side connections (dashed) ──────────────────────
    direction = diagram.get("direction", "LR").upper()
    side_offset = style_cfg.get("side_offset", 80)
    for item in diagram.get("side", []):
        edge = _parse_edge(item)
        src = edge["from"]
        dst_key = edge["to"]
        side_text = edge.get("text", dst_key)
        color_name = edge.get("color", "gray")
        stroke = EDGE_COLORS.get(color_name, color_name if color_name.startswith("#") else EDGE_COLORS["gray"])
        side_style = edge.get("style", "gray")
        side_bg = STYLE_COLORS.get(side_style, STYLE_COLORS["gray"])

        if dst_key not in layout:
            src_props = layout.get(src, {})
            if src_props:
                if direction == "TB":
                    sx = src_props["x"] + src_props["w"] + side_offset
                    sy = src_props["y"]
                else:
                    sx = src_props["x"]
                    sy = src_props["y"] + src_props["h"] + side_offset
            else:
                sx, sy = 0, 400

            side_bid = f"n_{dst_key}"
            side_tid = f"t_{dst_key}"
            box_el, text_el, _, _ = box_elements(
                text=side_text,
                x=sx, y=sy,
                bg=side_bg,
                stroke=stroke,
                font_size=14,
                box_id=side_bid,
                text_id=side_tid,
            )
            box_el["strokeStyle"] = "dashed"
            all_elements.extend([box_el, text_el])

        arr = arrow_element(f"n_{src}", f"n_{dst_key}", stroke=stroke, style="dashed")
        all_elements.append(arr)

    # ── Notes block ────────────────────────────────────
    notes = diagram.get("notes", [])
    if notes:
        max_bottom = max(
            (props["y"] + props["h"] for props in layout.values()),
            default=effective_start_y,
        )

        notes_y = max_bottom + 100
        notes_text = "\n".join(f"• {note}" for note in notes)

        nw, nh = estimate_text_size(notes_text, 14)
        nw = max(nw + 40, 400)
        nh = nh + 30

        all_elements.append({
            "id": _make_id("nbg"),
            "type": "rectangle",
            "x": start_x,
            "y": notes_y,
            "width": nw,
            "height": nh,
            "backgroundColor": "#fff9db",
            "strokeColor": "#e8590c",
            "strokeStyle": "dashed",
            "roughness": 1,
        })
        all_elements.append({
            "id": _make_id("ntxt"),
            "type": "text",
            "x": start_x + 20,
            "y": notes_y + 15,
            "text": notes_text,
            "fontSize": 14,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": "#e8590c",
            "textAlign": "left",
        })

    # ── Send to canvas ─────────────────────────────────
    return batch_create(all_elements)


# ── Incremental operations ─────────────────────────────

def add_node(diagram: dict, key: str, text: str, **kwargs) -> dict:
    """Add a node to the diagram data (doesn't render)."""
    if "nodes" not in diagram:
        diagram["nodes"] = {}
    node = {"text": text}
    node.update(kwargs)
    diagram["nodes"][key] = node
    return diagram


def remove_node(diagram: dict, key: str) -> dict:
    """Remove a node and all its edges from the diagram data."""
    if "nodes" in diagram:
        diagram["nodes"].pop(key, None)
    for section in ("edges", "side"):
        if section in diagram:
            diagram[section] = [
                e for e in diagram[section]
                if not (
                    (isinstance(e, (list, tuple)) and key in e[:2]) or
                    (isinstance(e, dict) and (e.get("from") == key or e.get("to") == key))
                )
            ]
    return diagram


def add_edge(diagram: dict, src: str, dst: str, **kwargs) -> dict:
    """Add an edge to the diagram data."""
    if "edges" not in diagram:
        diagram["edges"] = []
    edge = [src, dst]
    if kwargs:
        edge.append(kwargs)
    diagram["edges"].append(edge)
    return diagram


def remove_edge(diagram: dict, src: str, dst: str) -> dict:
    """Remove an edge from the diagram data."""
    for section in ("edges", "side"):
        if section in diagram:
            diagram[section] = [
                e for e in diagram[section]
                if not (
                    (isinstance(e, (list, tuple)) and len(e) >= 2 and e[0] == src and e[1] == dst) or
                    (isinstance(e, dict) and e.get("from") == src and e.get("to") == dst)
                )
            ]
    return diagram
