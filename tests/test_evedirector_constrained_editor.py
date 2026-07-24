from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backlot.agent_edit as edit_api
import backlot.agent_review as review_api
import backlot.server as backlot_server
import evedirector_agent.common as agent_common
from evedirector_agent.common import AgentContractError
from evedirector_agent.editing import apply_operations
from evedirector_agent.review import propose


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


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
            "type", "in_seconds", "out_seconds", "text", "subtitle",
            "backgroundColor",
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
        "project_id": "edit-demo",
        "pipeline_type": "animated-explainer",
        "title": "Constrained Editor Demo",
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
                "narration": "The first claim is grounded.",
                "cut": {
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "text": "First",
                    "subtitle": "Original first",
                    "backgroundColor": "#0F172A",
                },
            },
            {
                "id": "second",
                "source_contains": "Second grounded claim",
                "narration": "The second claim is grounded.",
                "cut": {
                    "type": "hero_title",
                    "in_seconds": 5,
                    "out_seconds": 11,
                    "text": "Second",
                    "subtitle": "Original second",
                    "backgroundColor": "#0F172A",
                },
            },
        ],
        "overlays": [],
    }


@pytest.fixture
def edit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(agent_common, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(review_api, "REPO_ROOT", tmp_path)
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "edit-demo"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(review_api, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(backlot_server, "PROJECTS_DIR", projects_dir)
    monkeypatch.delenv(review_api.ACTIONS_ENV, raising=False)

    source_path = tmp_path / "examples" / "source.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "# Editor Source\n\n"
        "First grounded claim remains attached to its evidence.\n\n"
        "Second grounded claim remains attached to its evidence.\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "examples" / "video_spec.yaml"
    policy_path = tmp_path / "examples" / "policy.yaml"
    prompt_path = tmp_path / "prompts" / "editor.md"
    response_path = tmp_path / "fixture-response.json"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text(
        "Instruction: {instruction}\nProtected: {immutable_fields}\n"
        "Allowed: {allowed_cut_types}\nSpec: {current_spec_json}\n"
        "Source: {source_numbered}\n",
        encoding="utf-8",
    )

    baseline = _spec(source_path, project_dir / "renders" / "demo.mp4")
    model_candidate = copy.deepcopy(baseline)
    model_candidate["scenes"][0]["narration"] = "The model clarified the first grounded claim."
    _write_yaml(spec_path, baseline)
    _write_yaml(policy_path, _policy())
    response_path.write_text(
        json.dumps({
            "video_spec": model_candidate,
            "rationale": "Clarify one scene.",
            "changed_scene_ids": ["first"],
            "assumptions": [],
        }),
        encoding="utf-8",
    )

    result = propose(
        spec_path=spec_path,
        policy_path=policy_path,
        prompt_template_path=prompt_path,
        run_root=project_dir / "agent_runs",
        instruction="Clarify the first scene.",
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
        "policy_path": policy_path,
        "run_id": result["run_id"],
        "baseline_bytes": spec_path.read_bytes(),
        "model_candidate": model_candidate,
    }


def _derive(
    client: TestClient,
    run_id: str,
    operations: list[dict],
    *,
    editor: str = "Neo.K",
    confirmation: str | None = None,
):
    return client.post(
        f"/api/project/edit-demo/agent-edit/{run_id}/derive",
        headers={"X-EveDirector-Action": "review"},
        json={
            "reviewer": editor,
            "summary": "Refine pacing and titles.",
            "operations": operations,
            "confirmation": confirmation or f"EDIT {run_id}",
        },
    )


def _operations() -> list[dict]:
    return [
        {"op": "set_project_field", "field": "title", "value": "Edited Graph Demo"},
        {"op": "reorder_scenes", "scene_ids": ["second", "first"]},
        {"op": "set_scene_duration", "scene_id": "second", "duration_seconds": 7},
        {
            "op": "set_scene_narration",
            "scene_id": "first",
            "value": "A human refined the first grounded narration.",
        },
        {
            "op": "set_cut_field",
            "scene_id": "first",
            "field": "subtitle",
            "value": "Human refinement",
        },
    ]


def test_apply_operations_preserves_identity_and_rebuilds_timeline(edit_env: dict) -> None:
    candidate = apply_operations(
        edit_env["model_candidate"],
        _operations(),
        _policy(),
    )
    assert candidate["title"] == "Edited Graph Demo"
    assert [scene["id"] for scene in candidate["scenes"]] == ["second", "first"]
    assert candidate["scenes"][0]["cut"]["in_seconds"] == 0
    assert candidate["scenes"][0]["cut"]["out_seconds"] == 7
    assert candidate["scenes"][1]["cut"]["in_seconds"] == 7
    assert candidate["scenes"][1]["cut"]["out_seconds"] == 12
    assert candidate["scenes"][1]["source_contains"] == "First grounded claim"
    assert candidate["scenes"][1]["cut"]["type"] == "hero_title"


@pytest.mark.parametrize(
    "operations, message",
    [
        ([{"op": "reorder_scenes", "scene_ids": ["first"]}], "every existing scene"),
        ([{"op": "set_cut_field", "scene_id": "first", "field": "type", "value": "x"}], "not editable"),
        ([{"op": "set_cut_field", "scene_id": "first", "field": "steps", "value": []}], "not editable"),
        ([{"op": "set_scene_duration", "scene_id": "first", "duration_seconds": 0.1}], "at least"),
        ([{"op": "remove_scene", "scene_id": "first"}], "Unsupported"),
    ],
)
def test_editor_rejects_unsafe_operations(
    edit_env: dict, operations: list[dict], message: str
) -> None:
    with pytest.raises(AgentContractError, match=message):
        apply_operations(edit_env["model_candidate"], operations, _policy())


def test_editor_detail_is_sanitized_and_declares_contract(edit_env: dict) -> None:
    response = edit_env["client"].get(
        f"/api/project/edit-demo/agent-edit/{edit_env['run_id']}"
    )
    assert response.status_code == 200
    payload = response.json()
    contract = payload["editor"]["contract"]
    assert "reorder_scenes" in contract["operation_types"]
    assert "type" not in contract["cut_fields"]
    assert "steps" not in contract["cut_fields"]
    assert payload["editor"]["derived_run_only"] is True
    serialized = json.dumps(payload)
    assert "messages" not in serialized
    assert "response.txt" not in serialized


def test_editor_page_is_mounted(edit_env: dict) -> None:
    app = backlot_server.create_app()
    with TestClient(app) as client:
        response = client.get(
            f"/p/edit-demo/agent-edit/{edit_env['run_id']}"
        )
    assert response.status_code == 200
    assert "EveDirector Constrained Editor" in response.text
    assert "/ui/agent-edit.js" in response.text


def test_derive_is_disabled_by_default(edit_env: dict) -> None:
    response = _derive(edit_env["client"], edit_env["run_id"], _operations())
    assert response.status_code == 403
    assert edit_env["spec_path"].read_bytes() == edit_env["baseline_bytes"]


def test_derive_requires_exact_confirmation(
    edit_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "1")
    response = _derive(
        edit_env["client"],
        edit_env["run_id"],
        _operations(),
        confirmation="EDIT wrong-run",
    )
    assert response.status_code == 422
    assert edit_env["spec_path"].read_bytes() == edit_env["baseline_bytes"]


def test_derive_creates_new_reviewable_run_without_canonical_write(
    edit_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "true")
    response = _derive(edit_env["client"], edit_env["run_id"], _operations())
    assert response.status_code == 200
    payload = response.json()
    derived_id = payload["derived_run_id"]
    assert derived_id != edit_env["run_id"]
    assert payload["run"]["status"] == "awaiting_human"
    assert payload["derived_from"] == edit_env["run_id"]
    assert edit_env["spec_path"].read_bytes() == edit_env["baseline_bytes"]

    derived_dir = edit_env["project_dir"] / "agent_runs" / derived_id
    audit = json.loads((derived_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["provider"] == "human-editor"
    assert audit["parent_run_id"] == edit_env["run_id"]
    assert audit["edit"]["editor"] == "Neo.K"
    assert audit["edit"]["operation_count"] == len(_operations())
    assert audit["validation"]["scene_count"] == 2
    assert len(audit["validation"]["grounding"]) == 2
    assert not (derived_dir / "request.json").exists()
    assert not (derived_dir / "response.txt").exists()
    assert (derived_dir / "edit_request.json").is_file()
    assert (derived_dir / "candidate.diff").is_file()
    assert (derived_dir / "candidate.unified.diff").is_file()

    candidate = yaml.safe_load(
        (derived_dir / "candidate.video_spec.yaml").read_text(encoding="utf-8")
    )
    assert [scene["id"] for scene in candidate["scenes"]] == ["second", "first"]
    assert candidate["scenes"][1]["cut"]["in_seconds"] == 7


def test_derived_run_can_use_existing_validate_and_apply_gate(
    edit_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "yes")
    derived = _derive(edit_env["client"], edit_env["run_id"], _operations())
    derived_id = derived.json()["derived_run_id"]

    validated = edit_env["client"].post(
        f"/api/project/edit-demo/agent-review/{derived_id}/validate",
        headers={"X-EveDirector-Action": "review"},
        json={"reviewer": "Neo.K", "confirmation": f"VALIDATE {derived_id}"},
    )
    assert validated.status_code == 200
    assert validated.json()["run"]["status"] == "validated"
    assert edit_env["spec_path"].read_bytes() == edit_env["baseline_bytes"]

    applied = edit_env["client"].post(
        f"/api/project/edit-demo/agent-review/{derived_id}/apply",
        headers={"X-EveDirector-Action": "review"},
        json={"reviewer": "Neo.K", "confirmation": f"APPLY {derived_id}"},
    )
    assert applied.status_code == 200
    current = yaml.safe_load(edit_env["spec_path"].read_text(encoding="utf-8"))
    assert current["title"] == "Edited Graph Demo"
    assert [scene["id"] for scene in current["scenes"]] == ["second", "first"]


def test_derive_rejects_stale_canonical_baseline(
    edit_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "on")
    current = yaml.safe_load(edit_env["spec_path"].read_text(encoding="utf-8"))
    current["title"] = "Changed elsewhere"
    _write_yaml(edit_env["spec_path"], current)

    response = _derive(edit_env["client"], edit_env["run_id"], _operations())
    assert response.status_code == 409
    assert "Canonical spec changed" in response.json()["detail"]
