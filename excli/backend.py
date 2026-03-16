"""HTTP client for the Excalidraw Express server on localhost:3000."""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

DEFAULT_URL = "http://localhost:3000"


def _base_url() -> str:
    return os.environ.get("EXCALIDRAW_URL", DEFAULT_URL).rstrip("/")


def _request(method: str, path: str, data: dict | list | None = None, params: dict | None = None) -> dict:
    """Make an HTTP request to the Excalidraw server. Returns parsed JSON."""
    url = f"{_base_url()}{path}"
    if params:
        url += "?" + urlencode(params)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(error_body)
            msg = err.get("error", error_body)
        except json.JSONDecodeError:
            msg = error_body
        raise RuntimeError(f"Excalidraw API {e.code}: {msg}") from e
    except URLError as e:
        raise RuntimeError(
            f"Cannot connect to Excalidraw server at {_base_url()}.\n"
            f"Make sure the canvas is running:\n"
            f"  cd ~/tools/mcp_excalidraw && npm run canvas\n"
            f"  Then open http://localhost:3000 in a browser.\n"
            f"Error: {e.reason}"
        ) from e


# ── Health ──────────────────────────────────────────────

def health() -> dict:
    return _request("GET", "/health")


# ── Elements CRUD ───────────────────────────────────────

def list_elements() -> list[dict]:
    resp = _request("GET", "/api/elements")
    return resp.get("elements", [])


def get_element(element_id: str) -> dict:
    resp = _request("GET", f"/api/elements/{element_id}")
    return resp.get("element", {})


def create_element(element: dict) -> dict:
    resp = _request("POST", "/api/elements", data=element)
    return resp.get("element", {})


def update_element(element_id: str, updates: dict) -> dict:
    resp = _request("PUT", f"/api/elements/{element_id}", data=updates)
    return resp.get("element", {})


def delete_element(element_id: str) -> dict:
    return _request("DELETE", f"/api/elements/{element_id}")


def batch_create(elements: list[dict]) -> list[dict]:
    resp = _request("POST", "/api/elements/batch", data={"elements": elements})
    return resp.get("elements", [])


def clear_canvas() -> dict:
    return _request("DELETE", "/api/elements/clear")


def search_elements(element_type: str | None = None) -> list[dict]:
    params = {}
    if element_type:
        params["type"] = element_type
    resp = _request("GET", "/api/elements/search", params=params)
    return resp.get("elements", [])


# ── Mermaid ─────────────────────────────────────────────

def from_mermaid(diagram: str, config: dict | None = None) -> dict:
    payload: dict = {"mermaidDiagram": diagram}
    if config:
        payload["config"] = config
    return _request("POST", "/api/elements/from-mermaid", data=payload)


# ── Export ──────────────────────────────────────────────

def export_image(fmt: str = "png", background: bool = True) -> dict:
    return _request("POST", "/api/export/image", data={"format": fmt, "background": background})


# ── Snapshots ───────────────────────────────────────────

def snapshot_save(name: str) -> dict:
    return _request("POST", "/api/snapshots", data={"name": name})


def snapshot_list() -> list[dict]:
    resp = _request("GET", "/api/snapshots")
    return resp.get("snapshots", [])


def snapshot_restore(name: str) -> dict:
    resp = _request("GET", f"/api/snapshots/{name}")
    snapshot = resp.get("snapshot", {})
    if not snapshot:
        raise RuntimeError(f'Snapshot "{name}" not found')
    # Restore by syncing elements back
    elements = snapshot.get("elements", [])
    return _request("POST", "/api/elements/sync", data={
        "elements": elements,
        "timestamp": snapshot.get("createdAt", "")
    })


# ── Batch update ───────────────────────────────────────

def batch_update(updates: list[dict]) -> list[dict]:
    """Update multiple elements at once.

    Each item: {"id": "...", ...props_to_update}.
    Falls back to sequential updates if batch endpoint doesn't exist.
    """
    results = []
    for item in updates:
        eid = item.pop("id", None)
        if eid and item:
            results.append(update_element(eid, item))
    return results


# ── Group / Ungroup ────────────────────────────────────

def group_elements(element_ids: list[str]) -> dict:
    """Group elements together."""
    return _request("POST", "/api/elements/group", data={"elementIds": element_ids})


def ungroup_elements(group_id: str) -> dict:
    """Ungroup a group of elements."""
    return _request("POST", "/api/elements/ungroup", data={"groupId": group_id})


# ── Viewport ────────────────────────────────────────────

def set_viewport(scroll_to_content: bool = False, zoom: float | None = None) -> dict:
    payload: dict = {}
    if scroll_to_content:
        payload["scrollToContent"] = True
    if zoom is not None:
        payload["zoom"] = zoom
    return _request("POST", "/api/viewport", data=payload)


# ── Align / Distribute / Duplicate / Lock ──────────────

def align_elements(element_ids: list[str], alignment: str) -> dict:
    """Align elements (left|center|right|top|middle|bottom)."""
    return _request("POST", "/api/elements/align", data={
        "elementIds": element_ids,
        "alignment": alignment,
    })


def distribute_elements(element_ids: list[str], axis: str) -> dict:
    """Distribute elements evenly (horizontal|vertical)."""
    return _request("POST", "/api/elements/distribute", data={
        "elementIds": element_ids,
        "axis": axis,
    })


def duplicate_elements(element_ids: list[str], offset_x: float = 40, offset_y: float = 40) -> list[dict]:
    """Duplicate elements with offset."""
    resp = _request("POST", "/api/elements/duplicate", data={
        "elementIds": element_ids,
        "offset": {"x": offset_x, "y": offset_y},
    })
    return resp.get("elements", [])


def lock_elements(element_ids: list[str]) -> dict:
    """Lock elements to prevent editing."""
    return _request("POST", "/api/elements/lock", data={"elementIds": element_ids})


def unlock_elements(element_ids: list[str]) -> dict:
    """Unlock elements."""
    return _request("POST", "/api/elements/unlock", data={"elementIds": element_ids})
