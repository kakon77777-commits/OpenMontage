"""EveDirector L5 constrained Project Graph editor API.

The editor never mutates a canonical specification or an existing proposal run.
It converts a small allow-listed operation set into a new derived candidate run,
then delegates validation and later approval to the existing L3/L4 contracts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from lib.paths import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "scripts"
UI_DIR = Path(__file__).resolve().parent / "ui"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evedirector_agent.common import AgentContractError, load_policy, load_yaml  # noqa: E402
from evedirector_agent.editing_guard import create_edited_run, editor_contract  # noqa: E402

from backlot import agent_review as review

router = APIRouter()


def _editor_html() -> HTMLResponse:
    html = (UI_DIR / "agent-edit.html").read_text(encoding="utf-8")
    for asset in ("agent-edit.css", "agent-edit.js", "agent-edit-overlay-guard.js"):
        path = UI_DIR / asset
        if path.is_file():
            html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={int(path.stat().st_mtime)}")
    return HTMLResponse(html)


def _editable_detail(project_id: str, run_id: str) -> dict[str, Any]:
    project_dir = review._safe_project_dir(project_id)
    run_dir = review._safe_run(project_dir, run_id)
    audit = review._read_object(run_dir / "audit.json")
    policy_path = review._repo_file(audit.get("policy_path"), suffixes={".yaml", ".yml"})
    policy = load_policy(policy_path)
    candidate_path = review._candidate_file(run_dir, audit)
    candidate = load_yaml(candidate_path)
    detail = review._detail(project_id, project_dir, run_dir.name)

    editable_scenes: list[dict[str, Any]] = []
    for scene in candidate.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        cut = scene.get("cut") if isinstance(scene.get("cut"), dict) else {}
        try:
            duration = float(cut.get("out_seconds", 0)) - float(cut.get("in_seconds", 0))
        except (TypeError, ValueError):
            duration = 0
        editable_scenes.append({
            "id": scene.get("id"),
            "source_contains": scene.get("source_contains"),
            "narration": scene.get("narration"),
            "cut": cut,
            "duration_seconds": duration,
        })

    detail["editor"] = {
        "contract": editor_contract(policy, candidate),
        "project": {
            "title": candidate.get("title"),
            "theme": candidate.get("theme"),
        },
        "scenes": editable_scenes,
        "source_run_id": run_dir.name,
        "submission_confirmation": f"EDIT {run_dir.name}",
        "canonical_write": False,
        "derived_run_only": True,
    }
    return detail


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, AgentContractError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/p/{project_id}/agent-edit/{run_id}")
async def agent_edit_page(project_id: str, run_id: str) -> HTMLResponse:
    project_dir = review._safe_project_dir(project_id)
    review._safe_run(project_dir, run_id)
    return _editor_html()


@router.get("/api/project/{project_id}/agent-edit/{run_id}")
async def agent_edit_detail(project_id: str, run_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_editable_detail, project_id, run_id)


@router.post("/api/project/{project_id}/agent-edit/{run_id}/derive")
async def agent_edit_derive(project_id: str, run_id: str, request: Request) -> dict[str, Any]:
    project_dir = review._safe_project_dir(project_id)
    run_dir = review._safe_run(project_dir, run_id)
    audit = review._read_object(run_dir / "audit.json")
    body = await review._body(request)
    editor = review._require_action(request, body, "EDIT", run_dir.name)
    operations = body.get("operations")
    if not isinstance(operations, list):
        raise HTTPException(status_code=422, detail="operations must be a JSON list")
    summary = str(body.get("summary") or "").strip()
    if len(summary) > 2000:
        raise HTTPException(status_code=422, detail="edit summary exceeds 2000 characters")
    policy_path = review._repo_file(audit.get("policy_path"), suffixes={".yaml", ".yml"})

    try:
        result = await asyncio.to_thread(
            create_edited_run,
            run_root=project_dir / "agent_runs",
            source_run_id=run_dir.name,
            policy_path=policy_path,
            operations=operations,
            editor=editor,
            summary=summary,
        )
    except Exception as exc:
        raise _translate(exc) from exc

    detail = await asyncio.to_thread(
        review._detail,
        project_id,
        project_dir,
        result["run_id"],
    )
    detail["derived_from"] = run_dir.name
    detail["derived_run_id"] = result["run_id"]
    return detail
