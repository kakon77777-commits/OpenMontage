"""Source-grounded Markdown to OpenMontage/Remotion project builder.

Phase L2 deliberately does not use an LLM or paid media API. A human-curated YAML
spec selects claims from a real Markdown source. Every scene must resolve to a
source line before artifacts or render props are written.

Default example:

    python scripts/markdown_to_video.py build
    python scripts/markdown_to_video.py render
    python scripts/markdown_to_video.py board
    python scripts/markdown_to_video.py all

The output is an OpenMontage project under projects/evedirector-drc-search/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = REPO_ROOT / "examples" / "drc-search-video" / "video_spec.yaml"
COMPOSER_DIR = REPO_ROOT / "remotion-composer"

sys.path.insert(0, str(REPO_ROOT))

from lib.checkpoint import PROJECTS_DIR, init_project, write_checkpoint  # noqa: E402


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Spec must be a YAML object: {path}")
    return data


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def normalize_text(value: str) -> str:
    value = re.sub(r"[`*_>#]", "", value)
    return " ".join(value.split()).casefold()


def source_title(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError("Markdown source has no level-one title")


def locate_claim(lines: list[str], needle: str) -> dict[str, Any]:
    wanted = normalize_text(needle)
    if not wanted:
        raise ValueError("source_contains cannot be empty")

    for index, line in enumerate(lines):
        if wanted in normalize_text(line):
            start = index + 1
            excerpt_lines = [line.strip()]
            cursor = index + 1
            while cursor < len(lines) and len(excerpt_lines) < 3:
                candidate = lines[cursor].strip()
                if candidate and not candidate.startswith("#"):
                    excerpt_lines.append(candidate)
                cursor += 1
            return {
                "line_start": start,
                "line_end": start + len(excerpt_lines) - 1,
                "excerpt": " ".join(excerpt_lines),
                "query": needle,
            }
    raise ValueError(f"Source claim not found: {needle!r}")


def validate_timeline(scenes: list[dict[str, Any]]) -> float:
    if not scenes:
        raise ValueError("Spec must contain at least one scene")

    previous_end = 0.0
    for scene in scenes:
        cut = scene.get("cut")
        if not isinstance(cut, dict):
            raise ValueError(f"Scene {scene.get('id')} has no cut object")
        start = float(cut["in_seconds"])
        end = float(cut["out_seconds"])
        if start != previous_end:
            raise ValueError(
                f"Timeline must be contiguous: scene {scene.get('id')} starts at {start}, "
                f"expected {previous_end}"
            )
        if end <= start:
            raise ValueError(f"Scene {scene.get('id')} has non-positive duration")
        previous_end = end
    return previous_end


def prepare_project(spec: dict[str, Any], *, force: bool = False) -> dict[str, Path]:
    source_path = resolve_repo_path(spec["source_path"])
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    source_text = source_path.read_text(encoding="utf-8")
    lines = source_text.splitlines()
    scenes = spec.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("Spec scenes must be a list")
    total_duration = validate_timeline(scenes)

    project_id = str(spec["project_id"])
    project_dir = PROJECTS_DIR / project_id
    if force and project_dir.exists():
        shutil.rmtree(project_dir)

    project_dir = init_project(
        project_id,
        title=str(spec["title"]),
        pipeline_type=str(spec.get("pipeline_type", "animated-explainer")),
        style_playbook=str(spec.get("theme", "flat-motion-graphics")),
    )
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    copied_source = source_dir / source_path.name
    shutil.copy2(source_path, copied_source)

    grounding_scenes: list[dict[str, Any]] = []
    script_sections: list[dict[str, Any]] = []
    scene_plan_scenes: list[dict[str, Any]] = []
    remotion_cuts: list[dict[str, Any]] = []
    edit_cuts: list[dict[str, Any]] = []

    for scene in scenes:
        scene_id = str(scene["id"])
        cut = dict(scene["cut"])
        grounding = locate_claim(lines, str(scene["source_contains"]))
        grounding["scene_id"] = scene_id
        grounding_scenes.append(grounding)

        start = float(cut["in_seconds"])
        end = float(cut["out_seconds"])
        narration = str(scene["narration"]).strip()
        script_sections.append(
            {
                "id": scene_id,
                "text": narration,
                "start_seconds": start,
                "end_seconds": end,
            }
        )

        description = str(cut.get("title") or cut.get("text") or scene_id)
        scene_plan_scenes.append(
            {
                "id": scene_id,
                "type": "diagram" if cut.get("type") in {"terminal_scene", "comparison"} else "text_card",
                "description": description,
                "start_seconds": start,
                "end_seconds": end,
                "script_section_id": scene_id,
                "narrative_role": (
                    "establish_context" if start == 0 else "resolution" if end == total_duration else "deliver_payload"
                ),
                "information_role": narration,
                "required_assets": [],
            }
        )

        cut.setdefault("source", "")
        cut["id"] = scene_id
        remotion_cuts.append(cut)
        edit_cuts.append(
            {
                "id": scene_id,
                "source": "",
                "in_seconds": start,
                "out_seconds": end,
                "layer": "primary",
                "reason": f"Source-grounded scene from {source_path.name}",
            }
        )

    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    source_manifest = {
        "version": "1.0",
        "project_id": project_id,
        "source": {
            "title": source_title(lines),
            "author": spec.get("author"),
            "original_path": str(source_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "project_copy": str(copied_source.relative_to(project_dir)).replace("\\", "/"),
            "sha256": source_hash,
            "line_count": len(lines),
        },
    }
    grounding_manifest = {
        "version": "1.0",
        "source_sha256": source_hash,
        "policy": "Every scene must resolve source_contains to a concrete source line.",
        "scenes": grounding_scenes,
    }
    script = {
        "version": "1.0",
        "title": str(spec["title"]),
        "total_duration_seconds": total_duration,
        "sections": script_sections,
    }
    scene_plan = {
        "version": "1.0",
        "style_playbook": str(spec.get("theme", "flat-motion-graphics")),
        "scenes": scene_plan_scenes,
        "metadata": {
            "source_grounding_manifest": "artifacts/grounding_manifest.json",
            "source_sha256": source_hash,
        },
    }
    edit_decisions = {
        "version": "1.0",
        "cuts": edit_cuts,
        "render_runtime": "remotion",
        "renderer_family": "explainer-data",
        "composition_mode": "templated",
    }
    remotion_props = {
        "theme": str(spec.get("theme", "flat-motion-graphics")),
        "cuts": remotion_cuts,
        "overlays": spec.get("overlays", []),
        "captions": [],
        "audio": {},
    }

    artifact_dir = project_dir / "artifacts"
    artifacts = {
        "source_manifest.json": source_manifest,
        "grounding_manifest.json": grounding_manifest,
        "script.json": script,
        "scene_plan.json": scene_plan,
        "edit_decisions.json": edit_decisions,
        "remotion_props.json": remotion_props,
    }
    for filename, payload in artifacts.items():
        (artifact_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    pipeline_type = str(spec.get("pipeline_type", "animated-explainer"))
    theme = str(spec.get("theme", "flat-motion-graphics"))
    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "script",
        "completed",
        {"script": script},
        pipeline_type=pipeline_type,
        style_playbook=theme,
        human_approved=True,
        metadata={"grounding_manifest": "artifacts/grounding_manifest.json"},
    )
    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "scene_plan",
        "completed",
        {"scene_plan": scene_plan},
        pipeline_type=pipeline_type,
        style_playbook=theme,
        human_approved=True,
    )
    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "edit",
        "completed",
        {"edit_decisions": edit_decisions},
        pipeline_type=pipeline_type,
        style_playbook=theme,
        human_approved=True,
    )
    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "compose",
        "in_progress",
        {},
        pipeline_type=pipeline_type,
        style_playbook=theme,
        metadata={"props_path": "artifacts/remotion_props.json"},
    )

    return {
        "project_dir": project_dir,
        "source": copied_source,
        "props": artifact_dir / "remotion_props.json",
        "grounding": artifact_dir / "grounding_manifest.json",
        "output": resolve_repo_path(spec["output_path"]),
    }


def find_command(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(f"Required command not found: {', '.join(names)}")


def render_project(spec: dict[str, Any], paths: dict[str, Path]) -> Path:
    npx = find_command("npx.cmd", "npx", "npx.exe")
    if not (COMPOSER_DIR / "node_modules").is_dir():
        npm = find_command("npm.cmd", "npm", "npm.exe")
        subprocess.run([npm, "install"], cwd=COMPOSER_DIR, check=True)

    output = paths["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        npx,
        "remotion",
        "render",
        "src/index.tsx",
        str(spec.get("composition", "Explainer")),
        str(output),
        "--props",
        str(paths["props"]),
        "--codec",
        "h264",
    ]
    subprocess.run(command, cwd=COMPOSER_DIR, check=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Render did not create a non-empty file: {output}")

    duration = validate_timeline(spec["scenes"])
    render_report = {
        "version": "1.0",
        "outputs": [
            {
                "path": str(output.relative_to(paths["project_dir"])).replace("\\", "/"),
                "format": "mp4",
                "resolution": "1920x1080",
                "duration_seconds": duration,
            }
        ],
    }
    (paths["project_dir"] / "artifacts" / "render_report.json").write_text(
        json.dumps(render_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_checkpoint(
        PROJECTS_DIR,
        str(spec["project_id"]),
        "compose",
        "completed",
        {"render_report": render_report},
        pipeline_type=str(spec.get("pipeline_type", "animated-explainer")),
        style_playbook=str(spec.get("theme", "flat-motion-graphics")),
        human_approved=True,
        metadata={"rendered_on": date.today().isoformat(), "zero_key": True},
    )
    return output


def open_board(project_id: str) -> None:
    subprocess.run([sys.executable, "-m", "backlot", "open", project_id], cwd=REPO_ROOT, check=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--force", action="store_true", help="Replace the generated project directory.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result metadata.")
    parser.add_argument("command", choices=["validate", "build", "render", "board", "all"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    spec_path = resolve_repo_path(args.spec)
    spec = load_yaml(spec_path)

    if args.command == "validate":
        source = resolve_repo_path(spec["source_path"])
        lines = source.read_text(encoding="utf-8").splitlines()
        validate_timeline(spec["scenes"])
        refs = [locate_claim(lines, scene["source_contains"]) for scene in spec["scenes"]]
        payload = {"valid": True, "source": str(source), "scene_count": len(refs)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "L2 spec is source-grounded and valid.")
        return 0

    if args.command == "board":
        open_board(str(spec["project_id"]))
        return 0

    paths = prepare_project(spec, force=args.force)
    result: dict[str, Any] = {
        "project_id": spec["project_id"],
        "project_dir": str(paths["project_dir"]),
        "grounding_manifest": str(paths["grounding"]),
        "rendered": False,
    }

    if args.command in {"render", "all"}:
        output = render_project(spec, paths)
        result["rendered"] = True
        result["output"] = str(output)

    if args.command == "all":
        open_board(str(spec["project_id"]))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"L2 project ready: {paths['project_dir']}")
        print(f"Grounding manifest: {paths['grounding']}")
        if result["rendered"]:
            print(f"Rendered MP4: {result['output']}")
        else:
            print(f"Render command: {sys.executable} scripts/markdown_to_video.py render")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
