"""excli — CLI wrapper for Excalidraw MCP server.

Usage:
  excli render diagram.excli.yaml    Render diagram from YAML (supports TB/LR, sections, manual pos)
  excli flow "A -> B -> C"           Build a linear flowchart
  excli batch elements.json          Batch-create raw elements from JSON
  excli update ID --bg "#fff"        Update element properties
  excli group ID1 ID2 ID3            Group elements together
  excli node add KEY TEXT --in FILE  Add node to diagram
  excli edge add SRC DST --in FILE   Add edge to diagram
  excli box "Title" --at 100,200     Create a labeled box
  excli list / describe / clear      Canvas operations
  excli export png out.png           Export to image
  excli snapshot save/restore NAME   Manage snapshots
"""

import json
import sys

import click

from excli import backend as api
from excli.elements import make_box, make_arrow, make_text
from excli.flow import build_flow_from_text, PALETTES


def _output(data, as_json: bool, compact: bool = False):
    """Print data as JSON or human-readable."""
    if compact:
        if isinstance(data, list):
            summary = [{"id": el.get("id", "?"), "type": el.get("type", "?"), **( {"text": el["text"]} if "text" in el else {})} for el in data]
            click.echo(json.dumps(summary, ensure_ascii=False))
        else:
            click.echo(json.dumps(data, ensure_ascii=False))
    elif as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if isinstance(data, list):
            for item in data:
                _print_element(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"  {k}: {v}")
        else:
            click.echo(str(data))


def _print_element(el: dict):
    """Pretty-print a single element."""
    eid = el.get("id", "?")[:12]
    etype = el.get("type", "?")
    text = el.get("text", "")
    x, y = el.get("x", 0), el.get("y", 0)
    label = f' "{text}"' if text else ""
    click.echo(f"  [{etype:10s}] {eid}{label}  @({x:.0f}, {y:.0f})")


def _parse_coords(value: str) -> tuple[float, float]:
    """Parse 'x,y' string to tuple."""
    parts = value.split(",")
    if len(parts) != 2:
        raise click.BadParameter(f"Expected x,y format, got: {value}")
    return float(parts[0].strip()), float(parts[1].strip())


# ── Main CLI group ──────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON for agents")
@click.option("-c", "--compact", is_flag=True, help="Compact output: [{id, type, text?}] only")
@click.pass_context
def cli(ctx, as_json, compact):
    """excli — Excalidraw CLI for AI agents and humans."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    ctx.obj["compact"] = compact
    if ctx.invoked_subcommand is None:
        click.echo(cli.get_help(ctx))


# ── render ─────────────────────────────────────────────

@cli.command()
@click.argument("file", default="-")
@click.option("--replace", is_flag=True, help="Clear canvas before rendering")
@click.option("--dry-run", is_flag=True, help="Show what would be created without rendering")
@click.option("--direction", type=click.Choice(["LR", "TB"]), default=None, help="Override layout direction")
@click.option("--layout", type=click.Choice(["auto", "manual", "grid"]), default=None, help="Override layout mode")
@click.option("--zoom-fit/--no-zoom-fit", default=True, help="Auto zoom-to-fit after render (default: on)")
@click.pass_context
def render(ctx, file, replace, dry_run, direction, layout, zoom_fit):
    """Render a diagram from a .excli.yaml file (use '-' for stdin).

    Supports: direction (LR/TB), sections, manual positions, grid layout.
    """
    from excli.diagram import (
        load_diagram, load_diagram_from_string, render_diagram, compute_layout, compute_sections,
    )

    if file == "-":
        diagram = load_diagram_from_string(sys.stdin.read())
    else:
        import os
        if not os.path.exists(file):
            click.echo(f"File not found: {file}", err=True)
            sys.exit(1)
        diagram = load_diagram(file)

    # CLI overrides
    if direction:
        diagram["direction"] = direction
    if layout:
        diagram["layout"] = layout

    nodes = diagram.get("nodes", {})
    edges = diagram.get("edges", [])
    notes = diagram.get("notes", [])
    sections = diagram.get("sections", {})

    if dry_run:
        computed = compute_layout(diagram)
        click.echo(f"Diagram: {len(nodes)} nodes, {len(edges)} edges, {len(notes)} notes, {len(sections)} sections")
        click.echo(f"Direction: {diagram.get('direction', 'LR')}, Layout: {diagram.get('layout', 'auto')}")
        click.echo("Layout:")
        for nid, props in computed.items():
            click.echo(f'  {nid:15s} "{props.get("text", nid)}"  @({props["x"]:.0f}, {props["y"]:.0f})  {props["w"]:.0f}x{props["h"]:.0f}')
        if sections:
            sec_boxes = compute_sections(sections, computed)
            click.echo("Sections:")
            for sec in sec_boxes:
                click.echo(f'  {sec["id"]:15s} "{sec["title"]}"  @({sec["x"]:.0f}, {sec["y"]:.0f})  {sec["w"]:.0f}x{sec["h"]:.0f}')
        return

    result = render_diagram(diagram, do_clear=replace)

    if zoom_fit:
        api.set_viewport(scroll_to_content=True)

    click.echo(f"Rendered {len(nodes)} nodes, {len(edges)} edges → {len(result)} elements")
    if sections:
        click.echo(f"  + {len(sections)} sections")
    if notes:
        click.echo(f"  + {len(notes)} notes")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── node ───────────────────────────────────────────────

@cli.group()
def node():
    """Add/remove nodes in a diagram file."""
    pass


@node.command("add")
@click.argument("key")
@click.argument("text")
@click.option("--in", "file", required=True, type=click.Path(exists=True), help="Diagram YAML file")
@click.option("--style", default="gray", help="Color style name")
@click.option("--shape", type=click.Choice(["rectangle", "ellipse", "diamond"]), default="rectangle")
@click.option("--size", type=click.Choice(["small", "normal", "large"]), default="normal")
@click.option("--connect-from", default=None, help="Add edge from this existing node")
@click.option("--connect-to", default=None, help="Add edge to this existing node")
def node_add(key, text, file, style, shape, size, connect_from, connect_to):
    """Add a node to a diagram YAML file."""
    from excli.diagram import load_diagram, save_diagram, add_node, add_edge

    diagram = load_diagram(file)
    node_props = {"text": text, "style": style}
    if shape != "rectangle":
        node_props["shape"] = shape
    if size != "normal":
        node_props["size"] = size
    add_node(diagram, key, **node_props)

    if connect_from:
        add_edge(diagram, connect_from, key)
    if connect_to:
        add_edge(diagram, key, connect_to)

    save_diagram(file, diagram)
    click.echo(f'Added node "{key}" to {file}')
    if connect_from:
        click.echo(f"  + edge {connect_from} -> {key}")
    if connect_to:
        click.echo(f"  + edge {key} -> {connect_to}")


@node.command("remove")
@click.argument("key")
@click.option("--in", "file", required=True, type=click.Path(exists=True), help="Diagram YAML file")
def node_remove(key, file):
    """Remove a node and its edges from a diagram YAML file."""
    from excli.diagram import load_diagram, save_diagram, remove_node

    diagram = load_diagram(file)
    remove_node(diagram, key)
    save_diagram(file, diagram)
    click.echo(f'Removed node "{key}" from {file}')


# ── edge ───────────────────────────────────────────────

@cli.group()
def edge():
    """Add/remove edges in a diagram file."""
    pass


@edge.command("add")
@click.argument("src")
@click.argument("dst")
@click.option("--in", "file", required=True, type=click.Path(exists=True), help="Diagram YAML file")
@click.option("--label", default=None, help="Edge label")
@click.option("--color", default=None, help="Edge color name")
def edge_add(src, dst, file, label, color):
    """Add an edge to a diagram YAML file."""
    from excli.diagram import load_diagram, save_diagram, add_edge

    diagram = load_diagram(file)
    kwargs = {}
    if label:
        kwargs["label"] = label
    if color:
        kwargs["color"] = color
    add_edge(diagram, src, dst, **kwargs)
    save_diagram(file, diagram)
    click.echo(f"Added edge {src} -> {dst} in {file}")


@edge.command("remove")
@click.argument("src")
@click.argument("dst")
@click.option("--in", "file", required=True, type=click.Path(exists=True), help="Diagram YAML file")
def edge_remove(src, dst, file):
    """Remove an edge from a diagram YAML file."""
    from excli.diagram import load_diagram, save_diagram, remove_edge

    diagram = load_diagram(file)
    remove_edge(diagram, src, dst)
    save_diagram(file, diagram)
    click.echo(f"Removed edge {src} -> {dst} from {file}")


# ── flow ────────────────────────────────────────────────

@cli.command()
@click.argument("notation")
@click.option("-d", "--direction", type=click.Choice(["horizontal", "vertical", "h", "v"]), default="horizontal")
@click.option("-p", "--palette", type=click.Choice(list(PALETTES.keys())), default="default")
@click.option("--clear", is_flag=True, help="Clear canvas before drawing")
@click.pass_context
def flow(ctx, notation, direction, palette, clear):
    """Build a linear flowchart from notation: "A -> B -> C" """
    d = "horizontal" if direction in ("horizontal", "h") else "vertical"
    result = build_flow_from_text(notation, direction=d, palette=palette, do_clear=clear)
    click.echo(f"Created flow with {len(result)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── box ─────────────────────────────────────────────────

@cli.command()
@click.argument("text")
@click.option("--at", "coords", default="100,100", help="Position as x,y")
@click.option("--size", default=None, help="Size as WxH (auto-sized if omitted)")
@click.option("--bg", default="transparent", help="Background color")
@click.option("--shape", type=click.Choice(["rectangle", "ellipse", "diamond"]), default="rectangle")
@click.pass_context
def box(ctx, text, coords, size, bg, shape):
    """Create a labeled box (rectangle/ellipse/diamond with text)."""
    x, y = _parse_coords(coords)
    w, h = None, None
    if size:
        parts = size.lower().split("x")
        w, h = float(parts[0]), float(parts[1])
    result = make_box(text, x=x, y=y, w=w, h=h, bg=bg, shape=shape)
    click.echo(f"Created {shape} with label")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── text ────────────────────────────────────────────────

@cli.command()
@click.argument("content")
@click.option("--at", "coords", default="100,100", help="Position as x,y")
@click.option("--size", "font_size", default=20, type=float, help="Font size")
@click.option("--color", default="#1e1e1e")
@click.pass_context
def text(ctx, content, coords, font_size, color):
    """Add a text element."""
    x, y = _parse_coords(coords)
    result = make_text(content, x=x, y=y, size=font_size, color=color)
    click.echo("Created text")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── connect ─────────────────────────────────────────────

@cli.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--label", default=None, help="Arrow label text")
@click.pass_context
def connect(ctx, from_id, to_id, label):
    """Create an arrow between two elements."""
    result = make_arrow(from_id, to_id, label=label)
    click.echo(f"Connected {from_id[:8]}.. -> {to_id[:8]}..")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── mermaid ─────────────────────────────────────────────

@cli.command()
@click.argument("diagram")
@click.pass_context
def mermaid(ctx, diagram):
    """Convert Mermaid diagram to Excalidraw elements."""
    result = api.from_mermaid(diagram)
    click.echo("Mermaid diagram sent to canvas")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── list ────────────────────────────────────────────────

@cli.command("list")
@click.option("-t", "--type", "el_type", default=None, help="Filter by type")
@click.pass_context
def list_cmd(ctx, el_type):
    """List all elements on canvas."""
    if el_type:
        elements = api.search_elements(el_type)
    else:
        elements = api.list_elements()
    click.echo(f"Canvas: {len(elements)} elements")
    _output(elements, ctx.obj["json"])


# ── describe ────────────────────────────────────────────

@cli.command()
@click.pass_context
def describe(ctx):
    """Summarize what's on the canvas."""
    elements = api.list_elements()
    if not elements:
        click.echo("Canvas is empty")
        return

    types: dict[str, int] = {}
    texts: list[str] = []
    for el in elements:
        t = el.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
        if el.get("text"):
            texts.append(el["text"])

    if ctx.obj["json"]:
        _output({"total": len(elements), "types": types, "labels": texts[:20]}, True, compact=ctx.obj["compact"])
    else:
        click.echo(f"Total: {len(elements)} elements")
        for t, c in types.items():
            click.echo(f"  {t}: {c}")
        if texts:
            click.echo("Labels:")
            for t in texts[:20]:
                click.echo(f'  - "{t}"')


# ── clear ───────────────────────────────────────────────

@cli.command()
@click.confirmation_option(prompt="Clear entire canvas?")
@click.pass_context
def clear(ctx):
    """Clear all elements from canvas."""
    result = api.clear_canvas()
    click.echo("Canvas cleared")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── export ──────────────────────────────────────────────

@cli.command()
@click.argument("fmt", type=click.Choice(["png", "svg"]))
@click.argument("output", required=False)
@click.option("--no-bg", is_flag=True, help="Transparent background")
@click.pass_context
def export(ctx, fmt, output, no_bg):
    """Export canvas to PNG or SVG."""
    result = api.export_image(fmt=fmt, background=not no_bg)
    if result.get("success") and result.get("data") and output:
        import base64
        data = result["data"]
        if "," in data:
            data = data.split(",", 1)[1]
        raw = base64.b64decode(data)
        with open(output, "wb") as f:
            f.write(raw)
        click.echo(f"Exported {fmt.upper()} to {output} ({len(raw):,} bytes)")
    elif result.get("success"):
        click.echo(f"Export ready ({fmt.upper()})")
        _output(result, ctx.obj["json"], compact=ctx.obj["compact"])
    else:
        click.echo(f"Export failed: {result.get('error', 'unknown')}", err=True)
        sys.exit(1)


# ── snapshot ────────────────────────────────────────────

@cli.group()
def snapshot():
    """Manage canvas snapshots (save/restore/list)."""
    pass


@snapshot.command("save")
@click.argument("name")
def snapshot_save(name):
    """Save current canvas as a named snapshot."""
    result = api.snapshot_save(name)
    click.echo(f'Snapshot "{name}" saved ({result.get("elementCount", 0)} elements)')


@snapshot.command("list")
def snapshot_list():
    """List all snapshots."""
    snaps = api.snapshot_list()
    if not snaps:
        click.echo("No snapshots")
        return
    for s in snaps:
        click.echo(f'  {s["name"]} — {s["elementCount"]} elements ({s["createdAt"]})')


@snapshot.command("restore")
@click.argument("name")
def snapshot_restore(name):
    """Restore canvas from a snapshot."""
    api.snapshot_restore(name)
    click.echo(f'Snapshot "{name}" restored')


# ── health ──────────────────────────────────────────────

@cli.command()
@click.pass_context
def health(ctx):
    """Check Excalidraw server status."""
    result = api.health()
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── zoom ────────────────────────────────────────────────

@cli.command()
@click.option("--fit", is_flag=True, help="Zoom to fit all elements")
@click.option("--level", type=float, default=None, help="Set zoom level (0.1-10)")
@click.pass_context
def zoom(ctx, fit, level):
    """Control canvas viewport."""
    result = api.set_viewport(scroll_to_content=fit, zoom=level)
    click.echo("Viewport updated")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── delete ──────────────────────────────────────────────

@cli.command()
@click.argument("element_id")
@click.pass_context
def delete(ctx, element_id):
    """Delete an element by ID."""
    result = api.delete_element(element_id)
    click.echo(f"Deleted {element_id[:12]}")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── scene (import/export .excalidraw files) ─────────────

@cli.group()
def scene():
    """Import/export .excalidraw scene files for collaboration."""
    pass


@scene.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Add to canvas instead of replacing")
@click.pass_context
def scene_import(ctx, file, merge):
    """Import a .excalidraw file onto the canvas."""
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    if not elements:
        click.echo("No elements found in file", err=True)
        sys.exit(1)

    if not merge:
        api.clear_canvas()

    result = api.batch_create(elements)
    click.echo(f"Imported {len(elements)} elements from {file}")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


@scene.command("export")
@click.argument("output", type=click.Path())
@click.pass_context
def scene_export(ctx, output):
    """Export canvas to a .excalidraw JSON file."""
    elements = api.list_elements()
    if not elements:
        click.echo("Canvas is empty, nothing to export", err=True)
        sys.exit(1)

    scene_data = {
        "type": "excalidraw",
        "version": 2,
        "source": "excli",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(scene_data, f, indent=2, ensure_ascii=False)

    click.echo(f"Exported {len(elements)} elements to {output}")


# ── batch ──────────────────────────────────────────────

@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--clear", is_flag=True, help="Clear canvas before creating")
@click.pass_context
def batch(ctx, file, clear):
    """Batch-create elements from a JSON file.

    File should contain a JSON array of Excalidraw elements,
    or an object with an "elements" key. Full MCP flexibility, one call.
    """
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data if isinstance(data, list) else data.get("elements", [])

    if not elements:
        click.echo("No elements found in file", err=True)
        sys.exit(1)

    if clear:
        api.clear_canvas()

    result = api.batch_create(elements)
    click.echo(f"Created {len(result)} elements from {file}")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── update ─────────────────────────────────────────────

@cli.command()
@click.argument("element_id")
@click.option("--bg", default=None, help="Background color")
@click.option("--stroke", default=None, help="Stroke color")
@click.option("--at", "coords", default=None, help="Position as x,y")
@click.option("--size", default=None, help="Size as WxH")
@click.option("--text", "new_text", default=None, help="Text content")
@click.option("--opacity", default=None, type=int, help="Opacity (0-100)")
@click.option("--font-size", default=None, type=float, help="Font size")
@click.option("--stroke-style", type=click.Choice(["solid", "dashed", "dotted"]), default=None)
@click.pass_context
def update(ctx, element_id, bg, stroke, coords, size, new_text, opacity, font_size, stroke_style):
    """Update an element's properties by ID."""
    updates: dict = {}
    if bg:
        updates["backgroundColor"] = bg
    if stroke:
        updates["strokeColor"] = stroke
    if coords:
        x, y = _parse_coords(coords)
        updates["x"] = x
        updates["y"] = y
    if size:
        parts = size.lower().split("x")
        updates["width"] = float(parts[0])
        updates["height"] = float(parts[1])
    if new_text:
        updates["text"] = new_text
    if opacity is not None:
        updates["opacity"] = opacity
    if font_size is not None:
        updates["fontSize"] = font_size
    if stroke_style:
        updates["strokeStyle"] = stroke_style

    if not updates:
        click.echo("No updates specified", err=True)
        sys.exit(1)

    result = api.update_element(element_id, updates)
    click.echo(f"Updated {element_id[:12]} ({len(updates)} properties)")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── group / ungroup ────────────────────────────────────

@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.pass_context
def group(ctx, element_ids):
    """Group elements together by their IDs."""
    result = api.group_elements(list(element_ids))
    click.echo(f"Grouped {len(element_ids)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


@cli.command()
@click.argument("group_id")
@click.pass_context
def ungroup(ctx, group_id):
    """Ungroup elements by group ID."""
    result = api.ungroup_elements(group_id)
    click.echo(f"Ungrouped {group_id[:12]}")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── template ──────────────────────────────────────────

@cli.group()
def template():
    """Use diagram templates (pipeline, layers, decision, comparison)."""
    pass


@template.command("list")
@click.pass_context
def template_list(ctx):
    """List available templates."""
    from excli.templates import list_templates

    templates = list_templates()
    if not templates:
        click.echo("No templates found")
        return
    for t in templates:
        vars_str = ", ".join(f"{k}={v}" for k, v in t.get("vars", {}).items())
        click.echo(f'  {t["name"]:15s} {t["description"]}')
        if vars_str:
            click.echo(f'  {"":15s} vars: {vars_str}')


@template.command("use")
@click.argument("name")
@click.option("--vars", "vars_str", default="", help='Variables as key=val,key2=val2')
@click.option("--replace", is_flag=True, help="Clear canvas before rendering")
@click.option("--dry-run", is_flag=True, help="Show diagram without rendering")
@click.pass_context
def template_use(ctx, name, vars_str, replace, dry_run):
    """Use a template to create a diagram."""
    from excli.templates import use_template
    from excli.diagram import render_diagram, compute_layout

    # Parse vars: "steps=A,B,C layers=X,Y" or "steps=A,B,C"
    variables: dict[str, str] = {}
    if vars_str:
        for part in vars_str.split(" "):
            if "=" in part:
                k, v = part.split("=", 1)
                variables[k.strip().upper()] = v.strip()

    diagram = use_template(name, variables)

    if dry_run:
        computed = compute_layout(diagram)
        nodes = diagram.get("nodes", {})
        edges = diagram.get("edges", [])
        click.echo(f"Template '{name}': {len(nodes)} nodes, {len(edges)} edges")
        click.echo("Layout:")
        for nid, props in computed.items():
            click.echo(f'  {nid:15s} "{props.get("text", nid)}"  @({props["x"]:.0f}, {props["y"]:.0f})  {props["w"]:.0f}x{props["h"]:.0f}')
        return

    result = render_diagram(diagram, do_clear=replace)
    api.set_viewport(scroll_to_content=True)
    click.echo(f"Template '{name}' → {len(result)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── align ─────────────────────────────────────────────

@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.option("--to", "alignment", required=True,
              type=click.Choice(["left", "center", "right", "top", "middle", "bottom"]),
              help="Alignment direction")
@click.pass_context
def align(ctx, element_ids, alignment):
    """Align elements to a common edge or center."""
    result = api.align_elements(list(element_ids), alignment)
    click.echo(f"Aligned {len(element_ids)} elements to {alignment}")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── distribute ────────────────────────────────────────

@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.option("--axis", required=True, type=click.Choice(["horizontal", "vertical"]),
              help="Distribution axis")
@click.pass_context
def distribute(ctx, element_ids, axis):
    """Distribute elements evenly along an axis."""
    result = api.distribute_elements(list(element_ids), axis)
    click.echo(f"Distributed {len(element_ids)} elements {axis}ly")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── duplicate ─────────────────────────────────────────

@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.option("--offset", default="40,40", help="Offset as x,y")
@click.pass_context
def duplicate(ctx, element_ids, offset):
    """Duplicate elements with an offset."""
    ox, oy = _parse_coords(offset)
    result = api.duplicate_elements(list(element_ids), offset_x=ox, offset_y=oy)
    click.echo(f"Duplicated {len(element_ids)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── lock / unlock ─────────────────────────────────────

@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.pass_context
def lock(ctx, element_ids):
    """Lock elements to prevent editing."""
    result = api.lock_elements(list(element_ids))
    click.echo(f"Locked {len(element_ids)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


@cli.command()
@click.argument("element_ids", nargs=-1, required=True)
@click.pass_context
def unlock(ctx, element_ids):
    """Unlock elements."""
    result = api.unlock_elements(list(element_ids))
    click.echo(f"Unlocked {len(element_ids)} elements")
    _output(result, ctx.obj["json"], compact=ctx.obj["compact"])


# ── Entry point ─────────────────────────────────────────

def main():
    cli()


if __name__ == "__main__":
    main()
