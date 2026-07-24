"""EveDirector L4 review API for local-agent proposal runs.

The read API exposes only sanitized review material: audit metadata, semantic
changes, scene summaries, source anchors, and a small project graph. It never
returns the full prompt or raw model response.

Write actions are disabled by default. When explicitly enabled, they still call
L3's validation/apply/reject functions so the canonical source-grounding and
stale-proposal checks cannot be bypassed by the web UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request

from lib.paths import PROJECTS_DIR, REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evedirector_agent.common import (  # noqa: E402
    AgentContractError,
    load_yaml,
    resolve_path,
)
from evedirector_agent.review import (  # noqa: E402
    apply_run,
    reject_run,
    semantic_diff_text,
    validate_run,
)
from evedirector_agent.runs import resolve_run_dir  # noqa: E402

router = APIRouter()
ACTIONS_ENV = "BACKLOT_ENABLE_AGENT_ACTIONS"
ACTION_HEADER = "x-evedirector-action"
ACTION_HEADER_VALUE = "review"


def actions_enabled() -> bool:
    return os.environ.get(ACTIONS_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}


def _safe_project_dir(project_id: str) -> Path:
    if any(char in project_id for char in "/\\:") or project_id in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="invalid project id")
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    return project_dir


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"missing review artifact: {path.name}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"unreadable review artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail=f"review artifact is not an object: {path.name}")
    return payload


def _run_root(project_dir: Path) -> Path:
    return project_dir / "agent_runs"


def _safe_run(project_dir: Path, run_id: str) -> Path:
    try:
        return resolve_run_dir(_run_root(project_dir), run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}") from exc
    except AgentContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _repo_file(value: Any, *, suffixes: set[str]) -> Path:
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=422, detail="audit contains an invalid repository path")
    path = resolve_path(value).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="audit path escapes the repository") from exc
    if path.suffix.casefold() not in suffixes:
        raise HTTPException(status_code=422, detail="audit path has an unsupported file type")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"audit target is missing: {path.name}")
    return path


def _candidate_file(run_dir: Path, audit: dict[str, Any]) -> Path:
    name = audit.get("candidate_path")
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=422, detail="audit has no candidate path")
    path = (run_dir / name).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="candidate path escapes its run directory") from exc
    if path.suffix.casefold() not in {".yaml", ".yml"} or not path.is_file():
        raise HTTPException(status_code=404, detail="candidate specification is missing")
    return path


def _summary(run_dir: Path, audit: dict[str, Any]) -> dict[str, Any]:
    validation = audit.get("validation") if isinstance(audit.get("validation"), dict) else {}
    metadata = audit.get("model_metadata") if isinstance(audit.get("model_metadata"), dict) else {}
    approval = audit.get("approval") if isinstance(audit.get("approval"), dict) else None
    return {
        "run_id": str(audit.get("run_id") or run_dir.name),
        "status": str(audit.get("status") or "unknown"),
        "created_at": audit.get("created_at"),
        "provider": audit.get("provider"),
        "model": audit.get("model"),
        "instruction": audit.get("instruction"),
        "scene_count": validation.get("scene_count"),
        "timeline_seconds": validation.get("timeline_seconds"),
        "source_anchor_count": len(validation.get("grounding") or []),
        "semantic_change_count": int(audit.get("semantic_change_count") or 0),
        "changed_scene_ids": metadata.get("computed_changed_scene_ids") or [],
        "approval": approval,
    }


def _list_runs(project_dir: Path) -> list[dict[str, Any]]:
    root = _run_root(project_dir)
    if not root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for run_dir in root.iterdir():
        if not run_dir.is_dir() or run_dir.name.startswith("."):
            continue
        audit_path = run_dir / "audit.json"
        if not audit_path.is_file():
            continue
        try:
            audit = _read_object(audit_path)
            runs.append(_summary(run_dir, audit))
        except HTTPException:
            runs.append({
                "run_id": run_dir.name,
                "status": "unreadable",
                "created_at": None,
                "semantic_change_count": 0,
                "source_anchor_count": 0,
            })
    runs.sort(key=lambda item: str(item.get("created_at") or item["run_id"]), reverse=True)
    return runs


def _source_excerpt(lines: list[str], start: int, end: int) -> str:
    if start < 1 or end < start:
        return ""
    return " ".join(line.strip() for line in lines[start - 1 : end] if line.strip())


def _detail(project_id: str, project_dir: Path, run_id: str) -> dict[str, Any]:
    run_dir = _safe_run(project_dir, run_id)
    audit = _read_object(run_dir / "audit.json")
    if str(audit.get("run_id") or run_dir.name) != run_dir.name:
        raise HTTPException(status_code=422, detail="audit run id does not match its directory")

    canonical_path = _repo_file(audit.get("canonical_spec_path"), suffixes={".yaml", ".yml"})
    policy_path = _repo_file(audit.get("policy_path"), suffixes={".yaml", ".yml"})
    candidate_path = _candidate_file(run_dir, audit)
    baseline = load_yaml(canonical_path)
    candidate = load_yaml(candidate_path)
    _semantic_text, changes = semantic_diff_text(baseline, candidate)

    source_path = _repo_file(candidate.get("source_path"), suffixes={".md", ".markdown"})
    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    validation = audit.get("validation") if isinstance(audit.get("validation"), dict) else {}
    grounding = validation.get("grounding") if isinstance(validation.get("grounding"), list) else []
    anchors: list[dict[str, Any]] = []
    anchor_by_scene: dict[str, dict[str, Any]] = {}
    for item in grounding:
        if not isinstance(item, dict):
            continue
        scene_id = str(item.get("scene_id") or "")
        start = int(item.get("line_start") or 0)
        end = int(item.get("line_end") or start)
        anchor = {
            "scene_id": scene_id,
            "line_start": start,
            "line_end": end,
            "query": item.get("query"),
            "excerpt": _source_excerpt(source_lines, start, end),
        }
        anchors.append(anchor)
        anchor_by_scene[scene_id] = anchor

    changed_scene_ids = {
        change["path"].split("/", 3)[2]
        for change in changes
        if isinstance(change.get("path"), str) and change["path"].startswith("/scenes/")
        and len(change["path"].split("/", 3)) >= 3
    }
    scenes: list[dict[str, Any]] = []
    for scene in candidate.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        cut = scene.get("cut") if isinstance(scene.get("cut"), dict) else {}
        scene_id = str(scene.get("id") or "")
        scenes.append({
            "id": scene_id,
            "title": cut.get("title") or cut.get("text") or cut.get("terminalTitle") or scene_id,
            "type": cut.get("type"),
            "in_seconds": cut.get("in_seconds"),
            "out_seconds": cut.get("out_seconds"),
            "narration": scene.get("narration"),
            "source_contains": scene.get("source_contains"),
            "changed": scene_id in changed_scene_ids,
            "anchor": anchor_by_scene.get(scene_id),
        })

    nodes: list[dict[str, Any]] = [
        {"id": "source", "type": "source", "label": source_path.name, "status": "grounded"},
        {"id": "canonical", "type": "spec", "label": canonical_path.name, "status": "canonical"},
        {"id": "candidate", "type": "candidate", "label": candidate_path.name, "status": "proposed"},
        {
            "id": "validation",
            "type": "validation",
            "label": f"{len(anchors)} source anchors",
            "status": "valid" if validation.get("valid") else "unknown",
        },
        {"id": "gate", "type": "gate", "label": "Human authority", "status": audit.get("status")},
    ]
    edges: list[dict[str, str]] = [
        {"from": "canonical", "to": "candidate", "label": "model proposal"},
        {"from": "source", "to": "validation", "label": "evidence"},
        {"from": "candidate", "to": "validation", "label": "contract check"},
        {"from": "validation", "to": "gate", "label": "reviewable"},
    ]
    for scene in scenes:
        node_id = f"scene:{scene['id']}"
        nodes.append({
            "id": node_id,
            "type": "scene",
            "label": scene["title"],
            "status": "changed" if scene["changed"] else "grounded",
            "scene_id": scene["id"],
        })
        edges.extend([
            {"from": "source", "to": node_id, "label": "anchors"},
            {"from": node_id, "to": "candidate", "label": "scene"},
        ])

    return {
        "project_id": project_id,
        "actions_enabled": actions_enabled(),
        "action_header": ACTION_HEADER,
        "run": _summary(run_dir, audit),
        "semanticChanges": changes,
        "source": {
            "title": next((line[2:].strip() for line in source_lines if line.startswith("# ")), source_path.name),
            "path": str(source_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "anchors": anchors,
        },
        "candidate": {
            "title": candidate.get("title"),
            "theme": candidate.get("theme"),
            "language": candidate.get("language"),
            "scene_count": len(scenes),
            "timeline_seconds": validation.get("timeline_seconds"),
            "scenes": scenes,
        },
        "graph": {"nodes": nodes, "edges": edges},
        "files": {
            "canonical_spec": str(canonical_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "candidate_spec": candidate_path.name,
            "semantic_diff": str(audit.get("diff_path") or "candidate.diff"),
            "raw_diff": str(audit.get("raw_diff_path") or "candidate.unified.diff"),
            "policy": str(policy_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
    }


def _require_action(request: Request, body: dict[str, Any], verb: str, run_id: str) -> str:
    if not actions_enabled():
        raise HTTPException(
            status_code=403,
            detail=f"agent actions are disabled; set {ACTIONS_ENV}=1 before starting Backlot",
        )
    if request.headers.get(ACTION_HEADER, "").casefold() != ACTION_HEADER_VALUE:
        raise HTTPException(status_code=403, detail=f"missing required {ACTION_HEADER} header")
    reviewer = str(body.get("reviewer") or "").strip()
    if not reviewer:
        raise HTTPException(status_code=422, detail="reviewer is required")
    expected = f"{verb} {run_id}"
    if body.get("confirmation") != expected:
        raise HTTPException(status_code=422, detail=f"confirmation must equal {expected!r}")
    return reviewer


async def _body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    return payload


def _translate_contract_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AgentContractError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/api/project/{project_id}/agent-review")
async def agent_review_index(project_id: str) -> dict[str, Any]:
    project_dir = _safe_project_dir(project_id)
    runs = await asyncio.to_thread(_list_runs, project_dir)
    return {
        "project_id": project_id,
        "actions_enabled": actions_enabled(),
        "action_header": ACTION_HEADER,
        "runs": runs,
    }


@router.get("/api/project/{project_id}/agent-review/{run_id}")
async def agent_review_detail(project_id: str, run_id: str) -> dict[str, Any]:
    project_dir = _safe_project_dir(project_id)
    return await asyncio.to_thread(_detail, project_id, project_dir, run_id)


@router.post("/api/project/{project_id}/agent-review/{run_id}/validate")
async def agent_review_validate(project_id: str, run_id: str, request: Request) -> dict[str, Any]:
    project_dir = _safe_project_dir(project_id)
    run_dir = _safe_run(project_dir, run_id)
    audit = _read_object(run_dir / "audit.json")
    body = await _body(request)
    _require_action(request, body, "VALIDATE", run_dir.name)
    policy_path = _repo_file(audit.get("policy_path"), suffixes={".yaml", ".yml"})
    try:
        await asyncio.to_thread(
            validate_run,
            run_root=_run_root(project_dir),
            run_id=run_dir.name,
            policy_path=policy_path,
        )
    except Exception as exc:
        raise _translate_contract_error(exc) from exc
    return await asyncio.to_thread(_detail, project_id, project_dir, run_dir.name)


@router.post("/api/project/{project_id}/agent-review/{run_id}/apply")
async def agent_review_apply(project_id: str, run_id: str, request: Request) -> dict[str, Any]:
    project_dir = _safe_project_dir(project_id)
    run_dir = _safe_run(project_dir, run_id)
    audit = _read_object(run_dir / "audit.json")
    body = await _body(request)
    reviewer = _require_action(request, body, "APPLY", run_dir.name)
    policy_path = _repo_file(audit.get("policy_path"), suffixes={".yaml", ".yml"})
    try:
        await asyncio.to_thread(
            apply_run,
            run_root=_run_root(project_dir),
            run_id=run_dir.name,
            policy_path=policy_path,
            approve=True,
            reviewer=reviewer,
        )
    except Exception as exc:
        raise _translate_contract_error(exc) from exc
    return await asyncio.to_thread(_detail, project_id, project_dir, run_dir.name)


@router.post("/api/project/{project_id}/agent-review/{run_id}/reject")
async def agent_review_reject(project_id: str, run_id: str, request: Request) -> dict[str, Any]:
    project_dir = _safe_project_dir(project_id)
    run_dir = _safe_run(project_dir, run_id)
    body = await _body(request)
    reviewer = _require_action(request, body, "REJECT", run_dir.name)
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="rejection reason is required")
    try:
        await asyncio.to_thread(
            reject_run,
            run_root=_run_root(project_dir),
            run_id=run_dir.name,
            reviewer=reviewer,
            reason=reason,
        )
    except Exception as exc:
        raise _translate_contract_error(exc) from exc
    return await asyncio.to_thread(_detail, project_id, project_dir, run_dir.name)
