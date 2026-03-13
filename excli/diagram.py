"""Diagram engine — parse YAML, auto-layout, render to Excalidraw.

Supports:
- Nodes with shapes (rectangle, diamond, ellipse), colors, sizes
- Edges with labels and colors
- Auto-layout for DAGs (topological layering)
- Notes block rendered below the diagram
- Side connections (dashed auxiliary links)
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
}

EDGE_COLORS = {
    "green":  "#2b8a3e",
    "red":    "#e03131",
    "blue":   "#1971c2",
    "orange": "#e8590c",
    "gray":   "#868e96",
    "black":  "#1e1e1e",
}

SIZE_PRESETS = {
    "small":  {"font_size": 14, "min_w": 100, "min_h": 40},
    "normal": {"font_size": 18, "min_w": 140, "min_h": 55},
    "large":  {"font_size": 22, "min_w": 180, "min_h": 70},
}


# ── YAML parsing ───────────────────────────────────────

def load_diagram(path: str) -> dict:
    """Load a .excli.yaml diagram file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
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
      [src, dst, {label: "...", color: "..."}]
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
    """Remove back-edges to make the graph acyclic (for layering only).

    Uses DFS to detect back-edges. Returns edges without the back-edges.
    """
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
    """Assign each node to a layer (column) using longest-path layering.

    This ensures that nodes appear as far right as their dependencies allow,
    creating a natural left-to-right flow. Handles cycles by ignoring back-edges.
    """
    # Break cycles first so Kahn's algorithm works
    dag_edges = _break_cycles(node_ids, edges)

    # Build adjacency
    successors: dict[str, list[str]] = defaultdict(list)
    predecessors: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for e in dag_edges:
        src, dst = e["from"], e["to"]
        if src in in_degree and dst in in_degree:
            successors[src].append(dst)
            predecessors[dst].append(src)
            in_degree[dst] += 1

    # Longest path from sources (Kahn-style)
    layer: dict[str, int] = {}
    queue = deque()
    for nid in node_ids:
        if in_degree[nid] == 0:
            queue.append(nid)
            layer[nid] = 0

    while queue:
        node = queue.popleft()
        for succ in successors[node]:
            # Longest path: take max layer from all predecessors + 1
            candidate = layer[node] + 1
            if succ not in layer or candidate > layer[succ]:
                layer[succ] = candidate
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Nodes not reached (cycles or isolated) go to layer 0
    for nid in node_ids:
        if nid not in layer:
            layer[nid] = 0

    return layer


def _order_within_layers(
    node_ids: list[str],
    layers: dict[str, int],
    edges: list[dict],
) -> dict[int, list[str]]:
    """Group nodes by layer and order them to reduce edge crossings."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid in node_ids:
        by_layer[layers[nid]].append(nid)

    # Simple heuristic: order by median position of predecessors
    successors: dict[str, list[str]] = defaultdict(list)
    predecessors: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        src, dst = e["from"], e["to"]
        successors[src].append(dst)
        predecessors[dst].append(src)

    # Build position index for layer 0 (preserve input order)
    pos: dict[str, int] = {}
    for layer_num in sorted(by_layer.keys()):
        nodes = by_layer[layer_num]
        if layer_num == 0:
            for i, nid in enumerate(nodes):
                pos[nid] = i
        else:
            # Sort by median predecessor position
            def _median_pred_pos(nid):
                preds = [pos[p] for p in predecessors[nid] if p in pos]
                if not preds:
                    return 0
                preds.sort()
                return preds[len(preds) // 2]

            nodes.sort(key=_median_pred_pos)
            for i, nid in enumerate(nodes):
                pos[nid] = i
        by_layer[layer_num] = nodes

    return dict(by_layer)


# ── Layout computation ─────────────────────────────────

def compute_layout(
    diagram: dict,
    start_x: float = 80,
    start_y: float = 80,
    h_gap: float = 80,
    v_gap: float = 40,
) -> dict[str, dict]:
    """Compute positions and sizes for all nodes.

    Returns {node_id: {x, y, w, h, ...node_props}}.
    """
    nodes_raw = diagram.get("nodes", {})
    edges_raw = diagram.get("edges", [])
    side_raw = diagram.get("side", [])

    node_ids = list(nodes_raw.keys())
    nodes = {k: _parse_node(k, v) for k, v in nodes_raw.items()}

    # Parse only main edges for layout (side connections don't affect layout)
    main_edges = [_parse_edge(e) for e in edges_raw]

    # Filter edges to only include known nodes
    main_edges = [e for e in main_edges if e["from"] in nodes and e["to"] in nodes]

    # Compute layers
    layers = _compute_layers(node_ids, main_edges)
    by_layer = _order_within_layers(node_ids, layers, main_edges)

    # Compute sizes for each node
    sizes: dict[str, tuple[float, float]] = {}
    for nid, node in nodes.items():
        text = node.get("text", nid)
        size_name = node.get("size", "normal")
        preset = SIZE_PRESETS.get(size_name, SIZE_PRESETS["normal"])
        shape = node.get("shape", "rectangle")
        w, h = auto_box_size(text, preset["font_size"], preset["min_w"], preset["min_h"], shape=shape)
        sizes[nid] = (w, h)

    # Find max width per layer and max height per row position
    max_layer = max(by_layer.keys()) if by_layer else 0
    layer_widths: dict[int, float] = {}
    for layer_num, layer_nodes in by_layer.items():
        layer_widths[layer_num] = max(sizes[nid][0] for nid in layer_nodes) if layer_nodes else 0

    # Compute x positions (cumulative layer widths + gaps)
    layer_x: dict[int, float] = {}
    cx = start_x
    for layer_num in range(max_layer + 1):
        layer_x[layer_num] = cx
        cx += layer_widths.get(layer_num, 0) + h_gap

    # Compute y positions (center each layer vertically)
    # First find the tallest layer to center others around it
    layer_heights: dict[int, float] = {}
    for layer_num, layer_nodes in by_layer.items():
        total_h = sum(sizes[nid][1] for nid in layer_nodes) + v_gap * max(0, len(layer_nodes) - 1)
        layer_heights[layer_num] = total_h

    max_total_h = max(layer_heights.values()) if layer_heights else 0

    # Position nodes
    result: dict[str, dict] = {}
    for layer_num, layer_nodes in by_layer.items():
        total_h = layer_heights[layer_num]
        cy = start_y + (max_total_h - total_h) / 2  # center vertically

        for nid in layer_nodes:
            w, h = sizes[nid]
            node = nodes[nid]

            # Center node horizontally within its layer column
            lx = layer_x[layer_num]
            lw = layer_widths[layer_num]
            nx = lx + (lw - w) / 2

            result[nid] = {
                **node,
                "x": nx,
                "y": cy,
                "w": w,
                "h": h,
            }
            cy += h + v_gap

    return result


# ── Render to Excalidraw elements ──────────────────────

def render_diagram(
    diagram: dict,
    do_clear: bool = False,
    start_x: float = 80,
    start_y: float = 80,
) -> list[dict]:
    """Render a diagram dict to Excalidraw canvas. Returns created elements."""
    if do_clear:
        clear_canvas()

    layout = compute_layout(diagram, start_x=start_x, start_y=start_y)

    all_elements: list[dict] = []

    # ── Title ───────────────────────────────────────────
    title = diagram.get("title")
    if title:
        all_elements.append({
            "id": _make_id("title"),
            "type": "text",
            "x": start_x,
            "y": start_y - 45,
            "text": title,
            "fontSize": 28,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": DEFAULT_STROKE,
        })

    # ── Nodes ───────────────────────────────────────────
    for nid, props in layout.items():
        text = props.get("text", nid)
        shape = props.get("shape", "rectangle")
        style = props.get("style", "gray")
        bg = STYLE_COLORS.get(style, style if style.startswith("#") else STYLE_COLORS["gray"])
        size_name = props.get("size", "normal")
        preset = SIZE_PRESETS.get(size_name, SIZE_PRESETS["normal"])

        bid = f"n_{nid}"
        tid = f"t_{nid}"

        box_el, text_el, _, _ = box_elements(
            text=text,
            x=props["x"],
            y=props["y"],
            w=props["w"],
            h=props["h"],
            bg=bg,
            stroke=DEFAULT_STROKE,
            shape=shape,
            font_size=preset["font_size"],
            box_id=bid,
            text_id=tid,
        )
        all_elements.extend([box_el, text_el])

    # ── Main edges ──────────────────────────────────────
    for item in diagram.get("edges", []):
        edge = _parse_edge(item)
        src, dst = edge["from"], edge["to"]
        color_name = edge.get("color", "black")
        stroke = EDGE_COLORS.get(color_name, color_name if color_name.startswith("#") else DEFAULT_STROKE)

        arr = arrow_element(f"n_{src}", f"n_{dst}", stroke=stroke)
        all_elements.append(arr)

        # Edge label
        label = edge.get("label")
        if label:
            # Position label near the midpoint (approximate)
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

    # ── Side connections (dashed) ───────────────────────
    for item in diagram.get("side", []):
        edge = _parse_edge(item)
        src = edge["from"]
        dst_key = edge["to"]
        side_text = edge.get("text", dst_key)
        color_name = edge.get("color", "gray")
        stroke = EDGE_COLORS.get(color_name, EDGE_COLORS["gray"])

        # Create a side node if it's not in the main layout
        if dst_key not in layout:
            # Position below the source node
            src_props = layout.get(src, {})
            if src_props:
                sx = src_props["x"]
                sy = src_props["y"] + src_props["h"] + 80
            else:
                sx, sy = 0, 400

            side_bid = f"n_{dst_key}"
            side_tid = f"t_{dst_key}"
            box_el, text_el, _, _ = box_elements(
                text=side_text,
                x=sx, y=sy,
                bg=STYLE_COLORS["gray"],
                stroke=stroke,
                font_size=14,
                box_id=side_bid,
                text_id=side_tid,
            )
            box_el["strokeStyle"] = "dashed"
            all_elements.extend([box_el, text_el])

        arr = arrow_element(f"n_{src}", f"n_{dst_key}", stroke=stroke, style="dashed")
        all_elements.append(arr)

    # ── Notes block ─────────────────────────────────────
    notes = diagram.get("notes", [])
    if notes:
        # Find the bottom of the diagram
        max_bottom = 0
        for props in layout.values():
            bottom = props["y"] + props["h"]
            if bottom > max_bottom:
                max_bottom = bottom

        notes_y = max_bottom + 100
        notes_text = "\n".join(f"• {note}" for note in notes)

        # Background rectangle for notes
        nw, nh = estimate_text_size(notes_text, 14)
        nw = max(nw + 40, 400)
        nh = nh + 30

        nbg_id = _make_id("nbg")
        ntxt_id = _make_id("ntxt")
        # Position text inside box with padding (left-aligned)
        txt_x = start_x + 20
        txt_y = notes_y + 15

        all_elements.append({
            "id": nbg_id,
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
            "id": ntxt_id,
            "type": "text",
            "x": txt_x,
            "y": txt_y,
            "text": notes_text,
            "fontSize": 14,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "strokeColor": "#e8590c",
            "textAlign": "left",
        })

    # ── Send to canvas ──────────────────────────────────
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
    # Remove edges referencing this node
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
