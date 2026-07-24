from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import AgentContractError, load_policy, load_yaml, resolve_path
from .editing import (
    create_edited_run as _create_edited_run,
    editor_contract as _base_editor_contract,
)
from .runs import resolve_run_dir

STRUCTURAL_TIMELINE_OPERATIONS = {"reorder_scenes", "set_scene_duration"}


def timeline_is_editable(candidate: dict[str, Any]) -> bool:
    """Return whether scene-order/duration edits are safe for this candidate.

    L5 does not yet define an Overlay -> Scene anchor contract. Existing overlays
    use absolute seconds, so changing scene order or duration could preserve schema
    validity while silently severing semantic alignment. Structural timeline edits
    are therefore locked whenever any overlay exists.
    """
    overlays = candidate.get("overlays")
    return not (isinstance(overlays, list) and len(overlays) > 0)


def editor_contract(
    policy: dict[str, Any], candidate: dict[str, Any] | None = None
) -> dict[str, Any]:
    contract = _base_editor_contract(policy)
    editable = True if candidate is None else timeline_is_editable(candidate)
    contract["timeline_editable"] = editable
    contract["timeline_lock_reason"] = None if editable else (
        "Structural timeline editing is locked because this candidate contains "
        "absolute-time overlays without scene anchors."
    )
    return contract


def validate_guarded_operations(
    candidate: dict[str, Any], operations: list[dict[str, Any]], policy: dict[str, Any]
) -> None:
    if not isinstance(operations, list):
        raise AgentContractError("Editor operations must be a list.")

    timeline_editable = timeline_is_editable(candidate)
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise AgentContractError(f"Editor operation {index} must be an object.")
        op_name = str(operation.get("op") or "")
        if not timeline_editable and op_name in STRUCTURAL_TIMELINE_OPERATIONS:
            raise AgentContractError(
                "Structural timeline editing is locked while absolute-time overlays exist. "
                "Create an Overlay-to-Scene anchor contract before reordering scenes or "
                "changing scene duration."
            )
        if op_name == "set_cut_field":
            value = operation.get("value")
            if not isinstance(value, str):
                raise AgentContractError(
                    "Editable cut fields accept string values only; null, numeric, boolean, "
                    "array, and object values are not allowed."
                )
            if len(value) > 2000:
                raise AgentContractError("Editable cut field exceeds 2000 characters.")


def create_edited_run(
    *,
    run_root: Path,
    source_run_id: str,
    policy_path: Path,
    operations: list[dict[str, Any]],
    editor: str,
    summary: str = "",
) -> dict[str, Any]:
    """Guard the public L5 derive path, then delegate run creation to L5 core."""
    resolved_root = resolve_path(run_root)
    source_run_dir = resolve_run_dir(resolved_root, source_run_id)
    audit = json.loads((source_run_dir / "audit.json").read_text(encoding="utf-8"))
    candidate_path = (source_run_dir / str(audit["candidate_path"])).resolve()
    try:
        candidate_path.relative_to(source_run_dir.resolve())
    except ValueError as exc:
        raise AgentContractError("Source candidate path escaped its run directory.") from exc
    candidate = load_yaml(candidate_path)
    policy = load_policy(resolve_path(policy_path))
    validate_guarded_operations(candidate, operations, policy)
    return _create_edited_run(
        run_root=resolved_root,
        source_run_id=source_run_dir.name,
        policy_path=resolve_path(policy_path),
        operations=operations,
        editor=editor,
        summary=summary,
    )
