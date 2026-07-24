from __future__ import annotations

import pytest

from evedirector_agent.common import AgentContractError
from evedirector_agent.editing_guard import (
    editor_contract,
    timeline_is_editable,
    validate_guarded_operations,
)


def _policy() -> dict:
    return {
        "version": 1,
        "immutable_fields": ["version", "project_id"],
        "allowed_cut_types": ["callout"],
        "allowed_cut_fields": [
            "type", "in_seconds", "out_seconds", "title", "text", "steps"
        ],
        "max_duration_seconds": 60,
        "max_scene_count": 10,
        "max_narration_characters": 500,
        "editor": {
            "allowed_project_fields": ["title"],
            "blocked_cut_fields": ["type", "in_seconds", "out_seconds", "steps"],
            "min_scene_duration_seconds": 0.5,
            "max_operations_per_run": 20,
        },
        "network": {},
        "apply": {},
    }


def _candidate(*, overlays: bool) -> dict:
    return {
        "version": 1,
        "project_id": "guard-demo",
        "title": "Guard demo",
        "scenes": [
            {
                "id": "scene-a",
                "source_contains": "Grounded claim",
                "narration": "Grounded narration.",
                "cut": {
                    "type": "callout",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "title": "Grounded title",
                    "text": "Grounded text",
                },
            }
        ],
        "overlays": [
            {
                "type": "section_title",
                "in_seconds": 1,
                "out_seconds": 3,
                "text": "Absolute overlay",
            }
        ] if overlays else [],
    }


def test_overlay_candidate_declares_structural_timeline_lock() -> None:
    candidate = _candidate(overlays=True)
    contract = editor_contract(_policy(), candidate)
    assert timeline_is_editable(candidate) is False
    assert contract["timeline_editable"] is False
    assert "absolute-time overlays" in contract["timeline_lock_reason"]


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "reorder_scenes", "scene_ids": ["scene-a"]},
        {"op": "set_scene_duration", "scene_id": "scene-a", "duration_seconds": 7},
    ],
)
def test_overlay_candidate_rejects_structural_timeline_operations(operation: dict) -> None:
    with pytest.raises(AgentContractError, match="Structural timeline editing is locked"):
        validate_guarded_operations(_candidate(overlays=True), [operation], _policy())


def test_overlay_candidate_still_allows_text_editing() -> None:
    validate_guarded_operations(
        _candidate(overlays=True),
        [{
            "op": "set_cut_field",
            "scene_id": "scene-a",
            "field": "title",
            "value": "Revised grounded title",
        }],
        _policy(),
    )


@pytest.mark.parametrize("value", [None, 3, True, [], {}])
def test_cut_field_guard_accepts_strings_only(value: object) -> None:
    with pytest.raises(AgentContractError, match="string values only"):
        validate_guarded_operations(
            _candidate(overlays=False),
            [{
                "op": "set_cut_field",
                "scene_id": "scene-a",
                "field": "title",
                "value": value,
            }],
            _policy(),
        )


def test_candidate_without_overlays_keeps_timeline_editing_available() -> None:
    candidate = _candidate(overlays=False)
    contract = editor_contract(_policy(), candidate)
    assert timeline_is_editable(candidate) is True
    assert contract["timeline_editable"] is True
    assert contract["timeline_lock_reason"] is None
    validate_guarded_operations(
        candidate,
        [{"op": "set_scene_duration", "scene_id": "scene-a", "duration_seconds": 7}],
        _policy(),
    )
