from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backlot.agent_review as review_api
import evedirector_agent.common as agent_common
from evedirector_agent.review import propose


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _policy() -> dict:
    return {
        "version": 1,
        "candidate_only": True,
        "source_grounding": "required",
        "exact_top_level_keys": True,
        "immutable_fields": [
            "version", "project_id", "pipeline_type", "author", "source_path",
            "composition", "output_path", "language",
        ],
        "allowed_cut_types": ["hero_title"],
        "allowed_cut_fields": [
            "type", "in_seconds", "out_seconds", "text", "subtitle", "backgroundColor",
        ],
        "allowed_overlay_fields": [
            "type", "in_seconds", "out_seconds", "text", "subtitle", "accentColor",
        ],
        "max_duration_seconds": 30,
        "max_scene_count": 5,
        "max_narration_characters": 500,
        "editor": {
            "allowed_project_fields": ["title", "theme"],
            "blocked_cut_fields": ["type", "in_seconds", "out_seconds", "steps"],
            "min_scene_duration_seconds": 0.5,
            "max_operations_per_run": 20,
        },
        "network": {
            "local_only_default": True,
            "allowed_schemes": ["http", "https"],
            "block_redirects": True,
            "max_response_bytes": 1024 * 1024,
        },
        "apply": {
            "require_approve_flag": True,
            "require_reviewer": True,
            "reject_stale_baseline": True,
        },
    }


def _spec(source_path: Path, output_path: Path) -> dict:
    return {
        "version": 1,
        "project_id": "director-demo",
        "pipeline_type": "animated-explainer",
        "title": "Unified Workbench Demo",
        "author": "EveDirector",
        "source_path": str(source_path),
        "theme": "flat-motion-graphics",
        "composition": "Explainer",
        "output_path": str(output_path),
        "language": "en",
        "scenes": [
            {
                "id": "first",
                "source_contains": "First grounded claim",
                "narration": "The first grounded narration.",
                "cut": {
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "text": "First grounded claim",
                    "subtitle": "One",
                    "backgroundColor": "#0F172A",
                },
            },
            {
                "id": "second",
                "source_contains": "Second grounded claim",
                "narration": "The second grounded narration.",
                "cut": {
                    "type": "hero_title",
                    "in_seconds": 5,
                    "out_seconds": 11,
                    "text": "Second grounded claim",
                    "subtitle": "Two",
                    "backgroundColor": "#0F172A",
                },
            },
        ],
        "overlays": [
            {
                "type": "section_title",
                "in_seconds": 1,
                "out_seconds": 3,
                "text": "Absolute overlay",
                "subtitle": "Locks structure",
                "accentColor": "#22D3EE",
            }
        ],
    }


@pytest.fixture
def director_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(agent_common, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(review_api, "REPO_ROOT", tmp_path)
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "director-demo"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(review_api, "PROJECTS_DIR", projects_dir)
    monkeypatch.delenv(review_api.ACTIONS_ENV, raising=False)

    source_path = tmp_path / "examples" / "source.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "# Director Source\n\nFirst grounded claim is exact.\n\nSecond grounded claim is exact.\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "examples" / "video_spec.yaml"
    policy_path = tmp_path / "examples" / "policy.yaml"
    prompt_path = tmp_path / "prompts" / "director.md"
    response_path = tmp_path / "fixture-response.json"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text(
        "Instruction: {instruction}\nProtected: {immutable_fields}\nAllowed: {allowed_cut_types}\n"
        "Spec: {current_spec_json}\nSource: {source_numbered}\n",
        encoding="utf-8",
    )

    baseline = _spec(source_path, project_dir / "renders" / "demo.mp4")
    candidate = copy.deepcopy(baseline)
    candidate["scenes"][0]["narration"] = "The clarified first narration remains grounded."
    _write_yaml(spec_path, baseline)
    _write_yaml(policy_path, _policy())
    response_path.write_text(
        json.dumps(
            {
                "video_spec": candidate,
                "rationale": "Clarify the first scene.",
                "changed_scene_ids": ["first"],
                "assumptions": [],
                "private_debug": "UNIFIED_SECRET_MUST_NOT_LEAK",
            }
        ),
        encoding="utf-8",
    )

    result = propose(
        spec_path=spec_path,
        policy_path=policy_path,
        prompt_template_path=prompt_path,
        run_root=project_dir / "agent_runs",
        instruction="Clarify the first grounded narration.",
        provider="fixture",
        endpoint=None,
        model="",
        timeout_seconds=5,
        response_file=response_path,
        allow_remote=False,
        api_key=None,
    )

    app = FastAPI()
    app.include_router(review_api.router)
    return {
        "client": TestClient(app),
        "project_dir": project_dir,
        "spec_path": spec_path,
        "run_id": result["run_id"],
        "baseline_bytes": spec_path.read_bytes(),
    }


def test_unified_api_projects_one_scene_identity_across_all_views(director_env: dict) -> None:
    payload = director_env["client"].get(
        f"/api/project/director-demo/director/{director_env['run_id']}"
    ).json()
    model_ids = [scene["id"] for scene in payload["model"]["scenes"]]
    workflow_ids = [scene["id"] for scene in payload["views"]["workflow"]]
    timeline_ids = [scene["id"] for scene in payload["views"]["timeline"]]
    canvas_ids = [node["scene_id"] for node in payload["views"]["canvas"]["nodes"] if node.get("scene_id")]
    assert model_ids == workflow_ids == timeline_ids == canvas_ids == ["first", "second"]


def test_unified_api_preserves_evidence_and_minimizes_data(director_env: dict) -> None:
    payload = director_env["client"].get(
        f"/api/project/director-demo/director/{director_env['run_id']}"
    ).json()
    serialized = json.dumps(payload)
    scene_nodes = [node for node in payload["views"]["canvas"]["nodes"] if node.get("scene_id")]
    assert all(node["source_anchor"] for node in scene_nodes)
    assert payload["source"]["anchors"][0]["line_start"] >= 1
    assert "UNIFIED_SECRET_MUST_NOT_LEAK" not in serialized
    assert "messages" not in payload
    assert "response.txt" not in serialized


def test_canvas_layout_is_local_only_and_router_has_no_write_endpoint(director_env: dict) -> None:
    client = director_env["client"]
    payload = client.get(f"/api/project/director-demo/director/{director_env['run_id']}").json()
    canvas = payload["views"]["canvas"]
    assert canvas["layout_persistence"] == "browser-local-only"
    assert canvas["arbitrary_node_creation"] is False
    assert canvas["arbitrary_edge_creation"] is False
    assert payload["authority"]["canonical_write"] is False
    assert payload["authority"]["derived_run_only"] is True
    assert "/agent-edit/" in payload["authority"]["derive_endpoint"]
    missing_write = client.post(
        f"/api/project/director-demo/director/{director_env['run_id']}/derive", json={}
    )
    assert missing_write.status_code in {404, 405}


def test_overlay_lock_is_shared_by_workflow_and_timeline(director_env: dict) -> None:
    payload = director_env["client"].get(
        f"/api/project/director-demo/director/{director_env['run_id']}"
    ).json()
    contract = payload["model"]["contract"]
    assert contract["timeline_editable"] is False
    assert contract["overlay_count"] == 1
    assert "absolute-time overlays" in contract["timeline_lock_reason"]


def test_unified_page_is_mounted(director_env: dict) -> None:
    response = director_env["client"].get(
        f"/p/director-demo/director/{director_env['run_id']}"
    )
    assert response.status_code == 200
    assert "EveDirector Unified Workbench" in response.text
    assert "/ui/director.js" in response.text


def test_semantic_submission_reuses_l5_derived_run_gate(
    director_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "1")
    run_id = director_env["run_id"]
    response = director_env["client"].post(
        f"/api/project/director-demo/agent-edit/{run_id}/derive",
        headers={"X-EveDirector-Action": "review"},
        json={
            "reviewer": "Neo.K",
            "summary": "Clarify the second scene through the unified workbench.",
            "confirmation": f"EDIT {run_id}",
            "operations": [
                {
                    "op": "set_scene_narration",
                    "scene_id": "second",
                    "value": "The second narration was edited through the shared model.",
                }
            ],
        },
    )
    assert response.status_code == 200
    derived_run = response.json()["derived_run_id"]
    assert derived_run != run_id
    assert director_env["spec_path"].read_bytes() == director_env["baseline_bytes"]
    derived = director_env["client"].get(f"/api/project/director-demo/director/{derived_run}")
    assert derived.status_code == 200
    second = next(scene for scene in derived.json()["model"]["scenes"] if scene["id"] == "second")
    assert second["narration"].startswith("The second narration was edited")
    assert derived.json()["run"]["provider"] == "human-editor"
