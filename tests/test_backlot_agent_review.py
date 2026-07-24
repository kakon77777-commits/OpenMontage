from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backlot.agent_review as review_api
import backlot.server as backlot_server
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
            "type", "in_seconds", "out_seconds", "text", "subtitle",
            "backgroundColor",
        ],
        "allowed_overlay_fields": [
            "type", "in_seconds", "out_seconds", "text", "subtitle", "accentColor",
        ],
        "max_duration_seconds": 30,
        "max_scene_count": 5,
        "max_narration_characters": 500,
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
        "project_id": "review-demo",
        "pipeline_type": "animated-explainer",
        "title": "Grounded Review Demo",
        "author": "EveDirector",
        "source_path": str(source_path),
        "theme": "flat-motion-graphics",
        "composition": "Explainer",
        "output_path": str(output_path),
        "language": "en",
        "scenes": [
            {
                "id": "claim",
                "source_contains": "Grounded claim",
                "narration": "The original grounded narration.",
                "cut": {
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 6,
                    "text": "Grounded claim",
                    "subtitle": "Original",
                    "backgroundColor": "#0F172A",
                },
            }
        ],
        "overlays": [],
    }


@pytest.fixture
def review_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(agent_common, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(review_api, "REPO_ROOT", tmp_path)
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "review-demo"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(review_api, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(backlot_server, "PROJECTS_DIR", projects_dir)
    monkeypatch.delenv(review_api.ACTIONS_ENV, raising=False)

    source_path = tmp_path / "examples" / "source.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "# Review Source\n\nGrounded claim is preserved by an exact source anchor.\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "examples" / "video_spec.yaml"
    policy_path = tmp_path / "examples" / "policy.yaml"
    prompt_path = tmp_path / "prompts" / "review.md"
    response_path = tmp_path / "fixture-response.json"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text(
        "Instruction: {instruction}\nProtected: {immutable_fields}\nAllowed: {allowed_cut_types}\n"
        "Spec: {current_spec_json}\nSource: {source_numbered}\n",
        encoding="utf-8",
    )

    baseline = _spec(source_path, project_dir / "renders" / "demo.mp4")
    candidate = copy.deepcopy(baseline)
    candidate["scenes"][0]["narration"] = "The revised narration remains grounded."
    _write_yaml(spec_path, baseline)
    _write_yaml(policy_path, _policy())
    response_path.write_text(
        json.dumps(
            {
                "video_spec": candidate,
                "rationale": "Clarify the claim.",
                "changed_scene_ids": ["claim"],
                "assumptions": [],
                "private_debug": "RAW_RESPONSE_SECRET_MUST_NOT_LEAK",
            }
        ),
        encoding="utf-8",
    )

    result = propose(
        spec_path=spec_path,
        policy_path=policy_path,
        prompt_template_path=prompt_path,
        run_root=project_dir / "agent_runs",
        instruction="Improve the grounded narration.",
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
        "candidate": candidate,
    }


def _action(client: TestClient, run_id: str, action: str, *, reviewer: str = "Neo.K", reason: str = ""):
    return client.post(
        f"/api/project/review-demo/agent-review/{run_id}/{action}",
        headers={"X-EveDirector-Action": "review"},
        json={
            "reviewer": reviewer,
            "reason": reason,
            "confirmation": f"{action.upper()} {run_id}",
        },
    )


def test_review_index_and_detail_are_sanitized(review_env: dict) -> None:
    client = review_env["client"]
    run_id = review_env["run_id"]

    index = client.get("/api/project/review-demo/agent-review")
    assert index.status_code == 200
    assert index.json()["actions_enabled"] is False
    assert index.json()["runs"][0]["run_id"] == run_id

    response = client.get(f"/api/project/review-demo/agent-review/{run_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["semanticChanges"][0]["path"] == "/scenes/claim/narration"
    assert detail["source"]["anchors"][0]["scene_id"] == "claim"
    assert detail["graph"]["nodes"]
    serialized = json.dumps(detail)
    assert "RAW_RESPONSE_SECRET_MUST_NOT_LEAK" not in serialized
    assert "messages" not in detail
    assert "response.txt" not in serialized


def test_review_page_is_mounted(review_env: dict) -> None:
    app = backlot_server.create_app()
    with TestClient(app) as client:
        response = client.get("/p/review-demo/agent-review")
    assert response.status_code == 200
    assert "EveDirector Review" in response.text
    assert "/ui/agent-review.js" in response.text


def test_actions_are_disabled_by_default(review_env: dict) -> None:
    response = _action(review_env["client"], review_env["run_id"], "apply")
    assert response.status_code == 403
    assert review_env["spec_path"].read_bytes() == review_env["baseline_bytes"]


def test_action_requires_custom_header_and_exact_confirmation(
    review_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "1")
    run_id = review_env["run_id"]
    client = review_env["client"]

    missing_header = client.post(
        f"/api/project/review-demo/agent-review/{run_id}/apply",
        json={"reviewer": "Neo.K", "confirmation": f"APPLY {run_id}"},
    )
    assert missing_header.status_code == 403

    wrong_phrase = client.post(
        f"/api/project/review-demo/agent-review/{run_id}/apply",
        headers={"X-EveDirector-Action": "review"},
        json={"reviewer": "Neo.K", "confirmation": "APPLY something-else"},
    )
    assert wrong_phrase.status_code == 422
    assert review_env["spec_path"].read_bytes() == review_env["baseline_bytes"]


def test_validate_then_apply_uses_l3_contract(
    review_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "true")
    client = review_env["client"]
    run_id = review_env["run_id"]

    validated = _action(client, run_id, "validate")
    assert validated.status_code == 200
    assert validated.json()["run"]["status"] == "validated"
    assert review_env["spec_path"].read_bytes() == review_env["baseline_bytes"]

    applied = _action(client, run_id, "apply")
    assert applied.status_code == 200
    assert applied.json()["run"]["status"] == "applied"
    current = yaml.safe_load(review_env["spec_path"].read_text(encoding="utf-8"))
    assert current["scenes"][0]["narration"] == review_env["candidate"]["scenes"][0]["narration"]
    audit = json.loads(
        (review_env["project_dir"] / "agent_runs" / run_id / "audit.json").read_text(encoding="utf-8")
    )
    assert audit["approval"]["reviewer"] == "Neo.K"
    assert audit["approval"]["explicit_approve_flag"] is True


def test_reject_preserves_canonical_spec(
    review_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(review_api.ACTIONS_ENV, "yes")
    response = _action(
        review_env["client"], review_env["run_id"], "reject", reason="Keep the original pacing."
    )
    assert response.status_code == 200
    assert response.json()["run"]["status"] == "rejected"
    assert review_env["spec_path"].read_bytes() == review_env["baseline_bytes"]


def test_detail_rejects_audit_path_escape(review_env: dict) -> None:
    audit_path = review_env["project_dir"] / "agent_runs" / review_env["run_id"] / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["canonical_spec_path"] = "/etc/passwd"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    response = review_env["client"].get(
        f"/api/project/review-demo/agent-review/{review_env['run_id']}"
    )
    assert response.status_code == 403
