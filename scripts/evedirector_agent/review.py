from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import runs as core
from .common import dump_yaml, load_yaml, resolve_path, utc_now, write_json_atomic, write_text_atomic


def _semantic_changes(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if type(before) is not type(after):
        return [{"path": path or "/", "before": before, "after": after}]

    if isinstance(before, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{key}"
            if key not in before:
                changes.append({"path": child, "before": None, "after": after[key]})
            elif key not in after:
                changes.append({"path": child, "before": before[key], "after": None})
            else:
                changes.extend(_semantic_changes(before[key], after[key], child))
        return changes

    if isinstance(before, list):
        if path == "/scenes" and all(
            isinstance(item, dict) and "id" in item for item in before + after
        ):
            changes: list[dict[str, Any]] = []
            before_map = {str(item["id"]): item for item in before}
            after_map = {str(item["id"]): item for item in after}
            before_order = [str(item["id"]) for item in before]
            after_order = [str(item["id"]) for item in after]
            if before_order != after_order:
                changes.append(
                    {"path": "/scenes/@order", "before": before_order, "after": after_order}
                )
            for scene_id in sorted(set(before_map) | set(after_map)):
                scene_path = f"/scenes/{scene_id}"
                if scene_id not in before_map:
                    changes.append(
                        {"path": scene_path, "before": None, "after": after_map[scene_id]}
                    )
                elif scene_id not in after_map:
                    changes.append(
                        {"path": scene_path, "before": before_map[scene_id], "after": None}
                    )
                else:
                    changes.extend(
                        _semantic_changes(before_map[scene_id], after_map[scene_id], scene_path)
                    )
            return changes

        changes: list[dict[str, Any]] = []
        common = min(len(before), len(after))
        for index in range(common):
            changes.extend(_semantic_changes(before[index], after[index], f"{path}/{index}"))
        for index in range(common, len(before)):
            changes.append({"path": f"{path}/{index}", "before": before[index], "after": None})
        for index in range(common, len(after)):
            changes.append({"path": f"{path}/{index}", "before": None, "after": after[index]})
        return changes

    if before != after:
        return [{"path": path or "/", "before": before, "after": after}]
    return []


def _display(value: Any) -> str:
    if value is None:
        return "<missing>"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def semantic_diff_text(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    changes = _semantic_changes(baseline, candidate)
    lines = [
        "EveDirector semantic candidate diff",
        f"changed_paths: {len(changes)}",
        "",
    ]
    if not changes:
        lines.append("(no semantic changes)")
    for change in changes:
        lines.extend(
            [
                f"~ {change['path']}",
                f"- {_display(change['before'])}",
                f"+ {_display(change['after'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n", changes


def _refresh_review_files(run_dir: Path) -> dict[str, Any]:
    audit_path = run_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    baseline = load_yaml(resolve_path(audit["canonical_spec_path"]))
    candidate = load_yaml(run_dir / audit["candidate_path"])

    semantic_text, changes = semantic_diff_text(baseline, candidate)
    semantic_path = run_dir / "candidate.diff"
    raw_path = run_dir / "candidate.unified.diff"

    if semantic_path.exists() and not raw_path.exists():
        semantic_path.replace(raw_path)
    write_text_atomic(semantic_path, semantic_text)

    audit["diff_path"] = semantic_path.name
    audit["raw_diff_path"] = raw_path.name
    audit["semantic_change_count"] = len(changes)
    audit["semantic_diff_updated_at"] = utc_now()
    write_json_atomic(audit_path, audit)
    return audit


def propose(**kwargs: Any) -> dict[str, Any]:
    result = core.propose(**kwargs)
    run_dir = Path(result["run_dir"])
    audit = _refresh_review_files(run_dir)
    result["diff"] = str(run_dir / audit["diff_path"])
    result["raw_diff"] = str(run_dir / audit["raw_diff_path"])
    result["semantic_change_count"] = audit["semantic_change_count"]
    return result


def validate_run(**kwargs: Any) -> dict[str, Any]:
    result = core.validate_run(**kwargs)
    run_dir = Path(result["run_dir"])
    audit = _refresh_review_files(run_dir)
    result["diff"] = str(run_dir / audit["diff_path"])
    result["raw_diff"] = str(run_dir / audit["raw_diff_path"])
    result["semantic_change_count"] = audit["semantic_change_count"]
    return result


def run_status(**kwargs: Any) -> dict[str, Any]:
    result = core.run_status(**kwargs)
    run_dir = Path(result["run_dir"])
    audit = _refresh_review_files(run_dir)
    result["diff"] = str(run_dir / audit["diff_path"])
    result["raw_diff"] = str(run_dir / audit["raw_diff_path"])
    result["semantic_change_count"] = audit["semantic_change_count"]
    return result


apply_run = core.apply_run
reject_run = core.reject_run
