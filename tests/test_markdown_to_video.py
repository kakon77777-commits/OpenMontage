from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "markdown_to_video.py"
SPEC = importlib.util.spec_from_file_location("markdown_to_video", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def default_spec() -> dict:
    return MODULE.load_yaml(MODULE.DEFAULT_SPEC)


def test_default_timeline_is_contiguous_and_75_seconds() -> None:
    spec = default_spec()
    assert MODULE.validate_timeline(spec["scenes"]) == 75


def test_every_default_scene_resolves_to_source() -> None:
    spec = default_spec()
    source = MODULE.resolve_repo_path(spec["source_path"])
    lines = source.read_text(encoding="utf-8").splitlines()

    refs = [MODULE.locate_claim(lines, scene["source_contains"]) for scene in spec["scenes"]]

    assert len(refs) == 8
    assert all(ref["line_start"] >= 1 for ref in refs)
    assert all(ref["excerpt"] for ref in refs)


def test_missing_claim_fails_closed() -> None:
    with pytest.raises(ValueError, match="Source claim not found"):
        MODULE.locate_claim(["# Real source", "A grounded statement."], "invented statement")


def test_non_contiguous_timeline_is_rejected() -> None:
    scenes = [
        {"id": "a", "cut": {"in_seconds": 0, "out_seconds": 4}},
        {"id": "b", "cut": {"in_seconds": 5, "out_seconds": 8}},
    ]
    with pytest.raises(ValueError, match="Timeline must be contiguous"):
        MODULE.validate_timeline(scenes)


def test_build_writes_grounding_and_openmontage_artifacts(tmp_path, monkeypatch) -> None:
    spec = default_spec()
    monkeypatch.setattr(MODULE, "PROJECTS_DIR", tmp_path)

    original_init = MODULE.init_project

    def local_init(project_id: str, **kwargs):
        return original_init(project_id, pipeline_dir=tmp_path, **kwargs)

    monkeypatch.setattr(MODULE, "init_project", local_init)
    paths = MODULE.prepare_project(spec, force=True)

    artifact_dir = paths["project_dir"] / "artifacts"
    expected = {
        "source_manifest.json",
        "grounding_manifest.json",
        "script.json",
        "scene_plan.json",
        "edit_decisions.json",
        "remotion_props.json",
    }
    assert expected.issubset({path.name for path in artifact_dir.iterdir()})

    grounding = json.loads((artifact_dir / "grounding_manifest.json").read_text(encoding="utf-8"))
    props = json.loads((artifact_dir / "remotion_props.json").read_text(encoding="utf-8"))
    script = json.loads((artifact_dir / "script.json").read_text(encoding="utf-8"))

    assert len(grounding["scenes"]) == len(props["cuts"]) == len(script["sections"]) == 8
    assert grounding["source_sha256"]
    assert (paths["project_dir"] / "checkpoint_script.json").is_file()
    assert (paths["project_dir"] / "checkpoint_scene_plan.json").is_file()
    assert (paths["project_dir"] / "checkpoint_edit.json").is_file()
    assert (paths["project_dir"] / "checkpoint_compose.json").is_file()
