"""EveDirector L6 unified infinite-canvas/workflow/timeline projection.

This router is deliberately read-only. Semantic writes remain delegated to the
L5 ``agent-edit/.../derive`` endpoint, which creates a new candidate run and
reuses the L3/L4 validation and approval contracts.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backlot import agent_edit
from backlot import agent_review as review
from evedirector_agent.common import load_yaml

UI_DIR = Path(__file__).resolve().parent / "ui"
router = APIRouter()


def _director_html() -> HTMLResponse:
    html = (UI_DIR / "director.html").read_text(encoding="utf-8")
    for asset in ("director.css", "director.js"):
        path = UI_DIR / asset
        if path.is_file():
            html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={int(path.stat().st_mtime)}")
    return HTMLResponse(html)


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    return next((node for node in nodes if node.get("id") == node_id), None)


def _unified_detail(project_id: str, run_id: str) -> dict[str, Any]:
    detail = agent_edit._editable_detail(project_id, run_id)
    editor = detail["editor"]
    project_dir = review._safe_project_dir(project_id)
    run_dir = review._safe_run(project_dir, run_id)
    audit = review._read_object(run_dir / "audit.json")
    candidate = load_yaml(review._candidate_file(run_dir, audit))
    overlays = candidate.get("overlays")
    overlay_count = len(overlays) if isinstance(overlays, list) else 0
    contract = {**(editor.get("contract") or {}), "overlay_count": overlay_count}
    scenes = editor.get("scenes") or []
    scene_ids = [str(scene.get("id") or "") for scene in scenes]
    graph = detail.get("graph") or {"nodes": [], "edges": []}
    graph_nodes = graph.get("nodes") or []

    canvas_nodes: list[dict[str, Any]] = []
    for node_id in ("source", "canonical", "candidate", "validation", "gate"):
        node = _node_by_id(graph_nodes, node_id)
        if node:
            canvas_nodes.append({**node, "semantic_editable": False})

    workflow: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        scene_id = str(scene.get("id") or "")
        cut = scene.get("cut") if isinstance(scene.get("cut"), dict) else {}
        graph_node = _node_by_id(graph_nodes, f"scene:{scene_id}") or {}
        anchor = next(
            (
                item
                for item in detail.get("source", {}).get("anchors", [])
                if item.get("scene_id") == scene_id
            ),
            None,
        )
        scene_view = {
            "id": scene_id,
            "index": index,
            "label": graph_node.get("label") or cut.get("title") or cut.get("text") or scene_id,
            "type": cut.get("type"),
            "duration_seconds": scene.get("duration_seconds"),
            "in_seconds": cut.get("in_seconds"),
            "out_seconds": cut.get("out_seconds"),
            "changed": bool(graph_node.get("status") == "changed"),
            "source_anchor": anchor,
        }
        workflow.append(scene_view)
        timeline.append(scene_view)
        canvas_nodes.append(
            {
                "id": f"scene:{scene_id}",
                "type": "scene",
                "label": scene_view["label"],
                "status": "changed" if scene_view["changed"] else "grounded",
                "scene_id": scene_id,
                "semantic_editable": True,
                "source_anchor": anchor,
            }
        )

    if scene_ids != [item["id"] for item in workflow] or scene_ids != [item["id"] for item in timeline]:
        raise RuntimeError("Unified view scene identity diverged between graph, workflow, and timeline.")

    return {
        "version": "1.0",
        "project_id": project_id,
        "run_id": run_id,
        "actions_enabled": detail.get("actions_enabled", False),
        "run": detail.get("run"),
        "source": detail.get("source"),
        "semanticChanges": detail.get("semanticChanges", []),
        "authority": {
            "canonical_write": False,
            "derived_run_only": True,
            "derive_endpoint": f"/api/project/{project_id}/agent-edit/{run_id}/derive",
            "confirmation": editor.get("submission_confirmation"),
            "action_header": "X-EveDirector-Action: review",
        },
        "model": {
            "project": editor.get("project"),
            "scenes": scenes,
            "contract": contract,
        },
        "views": {
            "canvas": {
                "nodes": canvas_nodes,
                "edges": graph.get("edges") or [],
                "layout_persistence": "browser-local-only",
                "arbitrary_node_creation": False,
                "arbitrary_edge_creation": False,
            },
            "workflow": workflow,
            "timeline": timeline,
            "inspector": {
                "project_fields": contract.get("project_fields", []),
                "cut_fields": contract.get("cut_fields", []),
                "immutable_scene_fields": contract.get("immutable_scene_fields", []),
            },
        },
    }


@router.get("/p/{project_id}/director/{run_id}")
async def director_page(project_id: str, run_id: str) -> HTMLResponse:
    project_dir = review._safe_project_dir(project_id)
    review._safe_run(project_dir, run_id)
    return _director_html()


@router.get("/api/project/{project_id}/director/{run_id}")
async def director_detail(project_id: str, run_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_unified_detail, project_id, run_id)
