"""Template engine for common diagram patterns.

Templates are YAML files with ${PLACEHOLDER} variables that expand
into nodes and edges, saving agent tokens by avoiding full YAML generation.
"""

import os
import re
import yaml

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def list_templates() -> list[dict]:
    """List available templates with name and description."""
    result = []
    tpl_dir = _TEMPLATES_DIR
    if not os.path.isdir(tpl_dir):
        return result
    for fname in sorted(os.listdir(tpl_dir)):
        if not fname.endswith(".yaml"):
            continue
        path = os.path.join(tpl_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            result.append({
                "name": fname.replace(".yaml", ""),
                "description": data.get("description", ""),
                "vars": data.get("vars", {}),
            })
    return result


def _expand_vars(text: str, variables: dict[str, str]) -> str:
    """Replace ${VAR} placeholders in text."""
    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))
    return re.sub(r"\$\{(\w+)\}", _replacer, text)


def _generate_chain(items: list[str], prefix: str = "s") -> dict:
    """Generate nodes + edges for a linear chain of items."""
    nodes: dict[str, str] = {}
    edges: list[list[str]] = []
    palette = ["blue", "green", "yellow", "pink", "purple", "mint", "cyan", "orange"]

    for i, item in enumerate(items):
        key = f"{prefix}{i}"
        nodes[key] = {"text": item, "style": palette[i % len(palette)]}
        if i > 0:
            edges.append([f"{prefix}{i - 1}", key])

    return {"nodes": nodes, "edges": edges}


def use_template(name: str, variables: dict[str, str]) -> dict:
    """Load a template and expand it with variables.

    Variables can contain comma-separated lists which expand into
    node chains (e.g., steps=A,B,C → 3 nodes + 2 edges).
    """
    path = os.path.join(_TEMPLATES_DIR, f"{name}.yaml")
    if not os.path.exists(path):
        raise ValueError(f"Template '{name}' not found in {_TEMPLATES_DIR}")

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Expand simple string vars first
    expanded = _expand_vars(raw, variables)
    data = yaml.safe_load(expanded)

    if not isinstance(data, dict):
        raise ValueError(f"Template '{name}' did not produce a valid diagram dict")

    # Handle auto-generation directives
    generate = data.pop("generate", {})
    for gen_key, gen_cfg in generate.items():
        var_name = gen_cfg.get("from_var", gen_key)
        var_value = variables.get(var_name, "")
        items = [s.strip() for s in var_value.split(",") if s.strip()]
        prefix = gen_cfg.get("prefix", gen_key[0])
        gen_type = gen_cfg.get("type", "chain")

        if gen_type == "chain" and items:
            chain = _generate_chain(items, prefix=prefix)
            existing_nodes = data.get("nodes", {})
            existing_nodes.update(chain["nodes"])
            data["nodes"] = existing_nodes

            existing_edges = data.get("edges", [])
            existing_edges.extend(chain["edges"])
            data["edges"] = existing_edges

    # Remove template metadata
    data.pop("description", None)
    data.pop("vars", None)

    return data
