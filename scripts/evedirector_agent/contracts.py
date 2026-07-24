from __future__ import annotations

from typing import Any

from .common import (
    AgentContractError,
    l2_module,
    relative_or_absolute,
    sha256_bytes,
)


def validate_overlays(
    overlays: Any,
    total_duration: float,
    allowed_fields: set[str] | None = None,
) -> None:
    if overlays is None:
        return
    if not isinstance(overlays, list):
        raise AgentContractError("overlays must be a list.")
    for index, overlay in enumerate(overlays):
        if not isinstance(overlay, dict):
            raise AgentContractError(f"Overlay {index} must be an object.")
        if allowed_fields and not set(overlay).issubset(allowed_fields):
            unsupported = sorted(set(overlay) - allowed_fields)
            raise AgentContractError(
                f"Overlay {index} uses unsupported fields: {unsupported}."
            )
        start = float(overlay["in_seconds"])
        end = float(overlay["out_seconds"])
        if start < 0 or end <= start or end > total_duration + 1e-9:
            raise AgentContractError(
                f"Overlay {index} is outside the validated timeline."
            )


def validate_candidate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if policy.get("exact_top_level_keys", True) and set(candidate) != set(baseline):
        added = sorted(set(candidate) - set(baseline))
        removed = sorted(set(baseline) - set(candidate))
        raise AgentContractError(
            f"Candidate top-level keys changed; added={added}, removed={removed}."
        )

    for field in policy["immutable_fields"]:
        if candidate.get(field) != baseline.get(field):
            raise AgentContractError(f"Protected field changed: {field}")

    scenes = candidate.get("scenes")
    if not isinstance(scenes, list):
        raise AgentContractError("Candidate scenes must be a list.")
    if not 1 <= len(scenes) <= int(policy["max_scene_count"]):
        raise AgentContractError(
            f"Candidate scene count must be between 1 and {policy['max_scene_count']}."
        )

    allowed_scene_keys = {"id", "source_contains", "narration", "cut"}
    allowed_cut_types = set(map(str, policy["allowed_cut_types"]))
    allowed_cut_fields = set(map(str, policy.get("allowed_cut_fields", [])))
    for scene in scenes:
        if not isinstance(scene, dict):
            raise AgentContractError("Every scene must be an object.")
        if set(scene) != allowed_scene_keys:
            raise AgentContractError(
                f"Scene {scene.get('id')!r} must contain exactly "
                f"{sorted(allowed_scene_keys)}."
            )
        narration = scene.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise AgentContractError(
                f"Scene {scene.get('id')!r} has empty narration."
            )
        if len(narration) > int(policy.get("max_narration_characters", 1200)):
            raise AgentContractError(
                f"Scene {scene.get('id')!r} narration exceeds the policy limit."
            )
        cut = scene.get("cut")
        if not isinstance(cut, dict):
            raise AgentContractError(f"Scene {scene.get('id')!r} has no cut object.")
        if cut.get("type") not in allowed_cut_types:
            raise AgentContractError(
                f"Scene {scene.get('id')!r} uses unsupported cut type "
                f"{cut.get('type')!r}."
            )
        if allowed_cut_fields and not set(cut).issubset(allowed_cut_fields):
            unsupported = sorted(set(cut) - allowed_cut_fields)
            raise AgentContractError(
                f"Scene {scene.get('id')!r} uses unsupported cut fields: {unsupported}."
            )

    l2 = l2_module()
    total_duration = float(l2.validate_timeline(scenes))
    if total_duration > float(policy["max_duration_seconds"]):
        raise AgentContractError(
            f"Candidate duration {total_duration}s exceeds "
            f"{policy['max_duration_seconds']}s."
        )

    source_path = l2.resolve_repo_path(candidate["source_path"])
    if not source_path.is_file():
        raise AgentContractError(f"Source file does not exist: {source_path}")
    lines = source_path.read_text(encoding="utf-8").splitlines()
    grounding = []
    for scene in scenes:
        try:
            anchor = l2.locate_claim(lines, str(scene["source_contains"]))
        except ValueError as exc:
            raise AgentContractError(str(exc)) from exc
        grounding.append(
            {
                "scene_id": scene["id"],
                "line_start": anchor["line_start"],
                "line_end": anchor["line_end"],
                "query": anchor["query"],
            }
        )

    validate_overlays(
        candidate.get("overlays", []),
        total_duration,
        set(map(str, policy.get("allowed_overlay_fields", []))),
    )
    return {
        "valid": True,
        "scene_count": len(scenes),
        "timeline_seconds": total_duration,
        "grounding": grounding,
        "source_path": relative_or_absolute(source_path),
        "source_sha256": sha256_bytes(source_path.read_bytes()),
    }
