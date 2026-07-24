from __future__ import annotations

import copy
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
    AgentContractError,
    dump_yaml,
    load_policy,
    load_yaml,
    relative_or_absolute,
    resolve_path,
    sha256_bytes,
    sha256_text,
    utc_now,
    write_json_atomic,
    write_text_atomic,
)
from .contracts import validate_candidate
from .review import semantic_diff_text
from .runs import resolve_run_dir, write_latest

DEFAULT_PROJECT_FIELDS = {"title", "theme"}
DEFAULT_BLOCKED_CUT_FIELDS = {"type", "in_seconds", "out_seconds", "steps"}
DEFAULT_MIN_SCENE_DURATION_SECONDS = 0.5
DEFAULT_MAX_OPERATIONS = 50
ALLOWED_OPERATION_TYPES = {
    "set_project_field",
    "reorder_scenes",
    "set_scene_duration",
    "set_scene_narration",
    "set_cut_field",
}


def _editor_policy(policy: dict[str, Any]) -> dict[str, Any]:
    raw = policy.get("editor") if isinstance(policy.get("editor"), dict) else {}
    project_fields = {
        str(value) for value in raw.get("allowed_project_fields", DEFAULT_PROJECT_FIELDS)
        if isinstance(value, str) and value
    }
    blocked_cut_fields = {
        str(value) for value in raw.get("blocked_cut_fields", DEFAULT_BLOCKED_CUT_FIELDS)
        if isinstance(value, str) and value
    }
    allowed_cut_fields = {
        str(value) for value in policy.get("allowed_cut_fields", [])
        if isinstance(value, str) and value
    } - blocked_cut_fields
    return {
        "allowed_project_fields": project_fields,
        "allowed_cut_fields": allowed_cut_fields,
        "min_scene_duration_seconds": float(
            raw.get("min_scene_duration_seconds", DEFAULT_MIN_SCENE_DURATION_SECONDS)
        ),
        "max_operations_per_run": int(raw.get("max_operations_per_run", DEFAULT_MAX_OPERATIONS)),
    }


def editor_contract(policy: dict[str, Any]) -> dict[str, Any]:
    contract = _editor_policy(policy)
    return {
        "operation_types": sorted(ALLOWED_OPERATION_TYPES),
        "project_fields": sorted(contract["allowed_project_fields"]),
        "cut_fields": sorted(contract["allowed_cut_fields"]),
        "immutable_scene_fields": ["id", "source_contains", "cut.type"],
        "min_scene_duration_seconds": contract["min_scene_duration_seconds"],
        "max_operations_per_run": contract["max_operations_per_run"],
    }


def _scene_map(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenes = candidate.get("scenes")
    if not isinstance(scenes, list):
        raise AgentContractError("Candidate scenes must be a list.")
    mapping: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            raise AgentContractError("Every scene must be an object.")
        scene_id = str(scene.get("id") or "")
        if not scene_id:
            raise AgentContractError("Every scene must have a non-empty id.")
        if scene_id in mapping:
            raise AgentContractError(f"Duplicate scene id: {scene_id}")
        mapping[scene_id] = scene
    return mapping


def _scalar(value: Any, *, field: str) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise AgentContractError(f"Editor field {field!r} only accepts a scalar value or null.")


def _require_exact_keys(operation: dict[str, Any], allowed: set[str], op_name: str) -> None:
    extra = sorted(set(operation) - allowed)
    missing = sorted(allowed - set(operation))
    if extra:
        raise AgentContractError(f"Operation {op_name!r} contains unsupported keys: {extra}.")
    if missing:
        raise AgentContractError(f"Operation {op_name!r} is missing keys: {missing}.")


def apply_operations(
    source_candidate: dict[str, Any],
    operations: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(operations, list) or not operations:
        raise AgentContractError("At least one editor operation is required.")

    contract = _editor_policy(policy)
    if len(operations) > contract["max_operations_per_run"]:
        raise AgentContractError(
            f"Editor operation count exceeds {contract['max_operations_per_run']}."
        )

    candidate = copy.deepcopy(source_candidate)
    source_ids = [str(scene.get("id") or "") for scene in candidate.get("scenes") or []]
    scenes = _scene_map(candidate)
    durations: dict[str, float] = {}
    for scene_id, scene in scenes.items():
        cut = scene.get("cut")
        if not isinstance(cut, dict):
            raise AgentContractError(f"Scene {scene_id!r} has no cut object.")
        duration = float(cut.get("out_seconds", 0)) - float(cut.get("in_seconds", 0))
        if duration <= 0:
            raise AgentContractError(f"Scene {scene_id!r} has an invalid starting duration.")
        durations[scene_id] = duration

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise AgentContractError(f"Editor operation {index} must be an object.")
        op_name = str(operation.get("op") or "")
        if op_name not in ALLOWED_OPERATION_TYPES:
            raise AgentContractError(f"Unsupported editor operation: {op_name!r}")

        if op_name == "set_project_field":
            _require_exact_keys(operation, {"op", "field", "value"}, op_name)
            field = str(operation["field"])
            if field not in contract["allowed_project_fields"]:
                raise AgentContractError(f"Project field is not editable: {field}")
            value = _scalar(operation["value"], field=field)
            if not isinstance(value, str) or not value.strip():
                raise AgentContractError(f"Project field {field!r} must be a non-empty string.")
            if len(value) > 500:
                raise AgentContractError(f"Project field {field!r} exceeds 500 characters.")
            candidate[field] = value.strip()
            continue

        if op_name == "reorder_scenes":
            _require_exact_keys(operation, {"op", "scene_ids"}, op_name)
            scene_ids = operation["scene_ids"]
            if not isinstance(scene_ids, list) or not all(isinstance(value, str) for value in scene_ids):
                raise AgentContractError("reorder_scenes.scene_ids must be a list of strings.")
            if len(scene_ids) != len(set(scene_ids)):
                raise AgentContractError("reorder_scenes.scene_ids contains duplicates.")
            if set(scene_ids) != set(source_ids):
                raise AgentContractError(
                    "reorder_scenes must contain every existing scene id exactly once."
                )
            candidate["scenes"] = [scenes[scene_id] for scene_id in scene_ids]
            continue

        scene_id = str(operation.get("scene_id") or "")
        if scene_id not in scenes:
            raise AgentContractError(f"Unknown scene id: {scene_id!r}")
        scene = scenes[scene_id]

        if op_name == "set_scene_duration":
            _require_exact_keys(operation, {"op", "scene_id", "duration_seconds"}, op_name)
            try:
                duration = float(operation["duration_seconds"])
            except (TypeError, ValueError) as exc:
                raise AgentContractError("duration_seconds must be numeric.") from exc
            if duration < contract["min_scene_duration_seconds"]:
                raise AgentContractError(
                    f"Scene duration must be at least "
                    f"{contract['min_scene_duration_seconds']} seconds."
                )
            durations[scene_id] = duration
            continue

        if op_name == "set_scene_narration":
            _require_exact_keys(operation, {"op", "scene_id", "value"}, op_name)
            value = operation["value"]
            if not isinstance(value, str) or not value.strip():
                raise AgentContractError("Scene narration must be a non-empty string.")
            if len(value) > int(policy.get("max_narration_characters", 1200)):
                raise AgentContractError("Scene narration exceeds the policy limit.")
            scene["narration"] = value.strip()
            continue

        if op_name == "set_cut_field":
            _require_exact_keys(operation, {"op", "scene_id", "field", "value"}, op_name)
            field = str(operation["field"])
            if field not in contract["allowed_cut_fields"]:
                raise AgentContractError(f"Cut field is not editable: {field}")
            value = _scalar(operation["value"], field=field)
            cut = scene.get("cut")
            if not isinstance(cut, dict):
                raise AgentContractError(f"Scene {scene_id!r} has no cut object.")
            if value is None:
                cut.pop(field, None)
            else:
                if isinstance(value, str) and len(value) > 2000:
                    raise AgentContractError(f"Cut field {field!r} exceeds 2000 characters.")
                cut[field] = value
            continue

    final_ids = [str(scene.get("id") or "") for scene in candidate["scenes"]]
    if set(final_ids) != set(source_ids) or len(final_ids) != len(source_ids):
        raise AgentContractError("Editor operations may not add, remove, or rename scenes.")

    cursor = 0.0
    for scene in candidate["scenes"]:
        scene_id = str(scene["id"])
        cut = scene["cut"]
        cut["in_seconds"] = round(cursor, 3)
        cursor += durations[scene_id]
        cut["out_seconds"] = round(cursor, 3)

    return candidate


def _changed_scene_ids(changes: list[dict[str, Any]]) -> list[str]:
    ids: set[str] = set()
    for change in changes:
        path = change.get("path")
        if not isinstance(path, str) or not path.startswith("/scenes/"):
            continue
        parts = path.split("/", 3)
        if len(parts) >= 3 and parts[2] and parts[2] != "@order":
            ids.add(parts[2])
    return sorted(ids)


def _derived_run_id(seed: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-edit-{sha256_text(seed)[:8]}"


def create_edited_run(
    *,
    run_root: Path,
    source_run_id: str,
    policy_path: Path,
    operations: list[dict[str, Any]],
    editor: str,
    summary: str = "",
) -> dict[str, Any]:
    if not editor.strip():
        raise AgentContractError("Editor identity is required.")

    run_root = resolve_path(run_root)
    source_run_dir = resolve_run_dir(run_root, source_run_id)
    source_audit_path = source_run_dir / "audit.json"
    source_audit = json.loads(source_audit_path.read_text(encoding="utf-8"))
    source_status = str(source_audit.get("status") or "")
    if source_status not in {"awaiting_human", "validated", "applied"}:
        raise AgentContractError(
            f"Run status does not allow derived editing: {source_status!r}"
        )

    spec_path = resolve_path(source_audit["canonical_spec_path"])
    policy_path = resolve_path(policy_path)
    policy = load_policy(policy_path)
    current_bytes = spec_path.read_bytes()
    current_hash = sha256_bytes(current_bytes)

    if source_status == "applied":
        applied_hash = ((source_audit.get("approval") or {}).get("applied_spec_sha256"))
        if not applied_hash or current_hash != applied_hash:
            raise AgentContractError(
                "Canonical spec changed after the applied source run. "
                "Choose a current run before editing."
            )
    elif current_hash != source_audit["hashes"]["baseline_spec_sha256"]:
        raise AgentContractError(
            "Canonical spec changed after the source proposal was created. "
            "Generate or choose a current proposal before editing."
        )

    source_candidate_path = (source_run_dir / source_audit["candidate_path"]).resolve()
    try:
        source_candidate_path.relative_to(source_run_dir.resolve())
    except ValueError as exc:
        raise AgentContractError("Source candidate path escaped its run directory.") from exc
    source_candidate = load_yaml(source_candidate_path)
    baseline = load_yaml(spec_path)
    candidate = apply_operations(source_candidate, operations, policy)
    validation = validate_candidate(baseline, candidate, policy)

    candidate_text = dump_yaml(candidate)
    semantic_text, changes = semantic_diff_text(baseline, candidate)
    raw_diff = "".join(
        difflib.unified_diff(
            current_bytes.decode("utf-8").splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=relative_or_absolute(spec_path),
            tofile="candidate.video_spec.yaml",
        )
    )
    request_payload = {
        "version": "1.0",
        "created_at": utc_now(),
        "source_run_id": source_run_dir.name,
        "editor": editor.strip(),
        "summary": summary.strip(),
        "operations": operations,
    }
    request_text = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
    run_id = _derived_run_id(request_text)
    run_dir = run_root / run_id
    collision = 1
    while run_dir.exists():
        run_dir = run_root / f"{run_id}-{collision}"
        collision += 1
    run_id = run_dir.name
    run_dir.mkdir(parents=True)

    write_json_atomic(run_dir / "edit_request.json", request_payload)
    write_text_atomic(run_dir / "candidate.video_spec.yaml", candidate_text)
    write_text_atomic(run_dir / "candidate.diff", semantic_text)
    write_text_atomic(run_dir / "candidate.unified.diff", raw_diff)

    audit = {
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now(),
        "status": "awaiting_human",
        "provider": "human-editor",
        "model": "constrained-project-graph",
        "endpoint": None,
        "instruction": summary.strip() or f"Constrained edit derived from {source_run_dir.name}.",
        "canonical_spec_path": relative_or_absolute(spec_path),
        "policy_path": relative_or_absolute(policy_path),
        "prompt_template_path": source_audit.get("prompt_template_path"),
        "candidate_path": "candidate.video_spec.yaml",
        "diff_path": "candidate.diff",
        "raw_diff_path": "candidate.unified.diff",
        "parent_run_id": source_run_dir.name,
        "validation": validation,
        "model_metadata": {
            "computed_changed_scene_ids": _changed_scene_ids(changes),
            "editor_operation_count": len(operations),
        },
        "edit": {
            "source_run_id": source_run_dir.name,
            "editor": editor.strip(),
            "summary": summary.strip(),
            "operation_count": len(operations),
            "operations_sha256": sha256_text(request_text),
        },
        "hashes": {
            "baseline_spec_sha256": current_hash,
            "source_sha256": validation["source_sha256"],
            "edit_request_sha256": sha256_text(request_text),
            "parent_candidate_spec_sha256": sha256_text(dump_yaml(source_candidate)),
            "candidate_spec_sha256": sha256_text(candidate_text),
        },
        "semantic_change_count": len(changes),
        "semantic_diff_updated_at": utc_now(),
        "approval": None,
    }
    write_json_atomic(run_dir / "audit.json", audit)
    write_latest(run_root, run_id, audit["status"])

    if sha256_bytes(spec_path.read_bytes()) != current_hash:
        raise RuntimeError("Canonical spec changed during constrained edit creation.")

    return {
        "run_id": run_id,
        "status": audit["status"],
        "run_dir": str(run_dir),
        "source_run_id": source_run_dir.name,
        "candidate": str(run_dir / "candidate.video_spec.yaml"),
        "diff": str(run_dir / "candidate.diff"),
        "raw_diff": str(run_dir / "candidate.unified.diff"),
        "semantic_change_count": len(changes),
        "validation": validation,
        "canonical_spec_unchanged": True,
    }
