from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
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
    AgentContractError,
)
from .contracts import validate_candidate
from .providers import (
    build_messages,
    call_provider,
    candidate_from_payload,
    changed_scene_ids,
    extract_json_object,
)


def latest_pointer_path(run_root: Path) -> Path:
    return run_root / "latest.json"


def write_latest(run_root: Path, run_id: str, status: str) -> None:
    write_json_atomic(
        latest_pointer_path(run_root),
        {
            "version": "1.0",
            "run_id": run_id,
            "status": status,
            "updated_at": utc_now(),
        },
    )


def resolve_run_dir(run_root: Path, run_id: str) -> Path:
    if run_id == "latest":
        pointer = latest_pointer_path(run_root)
        if not pointer.is_file():
            raise FileNotFoundError(f"No local-agent runs exist under {run_root}")
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        run_id = str(payload["run_id"])

    if not run_id or any(part in {"", ".", ".."} for part in Path(run_id).parts):
        raise AgentContractError(f"Invalid run id: {run_id!r}")
    candidate = (run_root / run_id).resolve()
    root = run_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AgentContractError("Run path escaped the configured run root.") from exc
    if not candidate.is_dir():
        raise FileNotFoundError(candidate)
    return candidate


def proposed_run_id(response_hash: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{response_hash[:8]}"


def propose(
    *,
    spec_path: Path,
    policy_path: Path,
    prompt_template_path: Path,
    run_root: Path,
    instruction: str,
    provider: str,
    endpoint: str | None,
    model: str,
    timeout_seconds: float,
    response_file: Path | None,
    allow_remote: bool,
    api_key: str | None,
) -> dict[str, Any]:
    spec_path = resolve_path(spec_path)
    policy_path = resolve_path(policy_path)
    prompt_template_path = resolve_path(prompt_template_path)
    run_root = resolve_path(run_root)

    baseline_bytes = spec_path.read_bytes()
    baseline_hash = sha256_bytes(baseline_bytes)
    baseline = load_yaml(spec_path)
    policy = load_policy(policy_path)
    source_path = resolve_path(str(baseline["source_path"]))
    source_text = source_path.read_text(encoding="utf-8")
    prompt_template = prompt_template_path.read_text(encoding="utf-8")
    messages = build_messages(
        instruction=instruction,
        baseline=baseline,
        source_text=source_text,
        policy=policy,
        prompt_template=prompt_template,
    )

    raw_response, used_endpoint = call_provider(
        provider=provider,
        endpoint=endpoint,
        model=model,
        messages=messages,
        timeout_seconds=timeout_seconds,
        max_response_bytes=int(policy["network"]["max_response_bytes"]),
        response_file=resolve_path(response_file) if response_file else None,
        allow_remote=allow_remote,
        api_key=api_key,
    )
    response_hash = sha256_text(raw_response)
    payload = extract_json_object(raw_response)
    candidate, model_metadata = candidate_from_payload(payload)
    validation = validate_candidate(baseline, candidate, policy)
    candidate_text = dump_yaml(candidate)
    candidate_hash = sha256_text(candidate_text)

    run_id = proposed_run_id(response_hash)
    run_dir = run_root / run_id
    collision = 1
    while run_dir.exists():
        run_dir = run_root / f"{run_id}-{collision}"
        collision += 1
    run_id = run_dir.name
    run_dir.mkdir(parents=True)

    request_payload = {
        "version": "1.0",
        "created_at": utc_now(),
        "provider": provider,
        "model": model or "fixture",
        "endpoint": used_endpoint,
        "instruction": instruction,
        "messages": messages,
    }
    write_json_atomic(run_dir / "request.json", request_payload)
    write_text_atomic(run_dir / "response.txt", raw_response)
    write_text_atomic(run_dir / "candidate.video_spec.yaml", candidate_text)

    baseline_text = baseline_bytes.decode("utf-8")
    diff = "".join(
        difflib.unified_diff(
            baseline_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=relative_or_absolute(spec_path),
            tofile=f"{run_id}/candidate.video_spec.yaml",
        )
    )
    write_text_atomic(run_dir / "candidate.diff", diff)

    audit = {
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now(),
        "status": "awaiting_human",
        "provider": provider,
        "model": model or "fixture",
        "endpoint": used_endpoint,
        "instruction": instruction,
        "canonical_spec_path": relative_or_absolute(spec_path),
        "policy_path": relative_or_absolute(policy_path),
        "prompt_template_path": relative_or_absolute(prompt_template_path),
        "hashes": {
            "baseline_spec_sha256": baseline_hash,
            "source_sha256": validation["source_sha256"],
            "prompt_sha256": sha256_text(
                json.dumps(messages, ensure_ascii=False, sort_keys=True)
            ),
            "response_sha256": response_hash,
            "candidate_spec_sha256": candidate_hash,
        },
        "candidate_path": "candidate.video_spec.yaml",
        "diff_path": "candidate.diff",
        "validation": validation,
        "model_metadata": {
            **model_metadata,
            "computed_changed_scene_ids": changed_scene_ids(baseline, candidate),
        },
        "approval": None,
    }
    write_json_atomic(run_dir / "audit.json", audit)
    write_latest(run_root, run_id, audit["status"])

    if sha256_bytes(spec_path.read_bytes()) != baseline_hash:
        raise RuntimeError("Canonical spec changed during proposal generation.")

    return {
        "run_id": run_id,
        "status": audit["status"],
        "run_dir": str(run_dir),
        "candidate": str(run_dir / "candidate.video_spec.yaml"),
        "diff": str(run_dir / "candidate.diff"),
        "validation": validation,
        "canonical_spec_unchanged": True,
    }


def validate_run(
    *, run_root: Path, run_id: str, policy_path: Path
) -> dict[str, Any]:
    run_root = resolve_path(run_root)
    run_dir = resolve_run_dir(run_root, run_id)
    audit_path = run_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    spec_path = resolve_path(audit["canonical_spec_path"])
    baseline = load_yaml(spec_path)
    candidate = load_yaml(run_dir / audit["candidate_path"])
    policy = load_policy(resolve_path(policy_path))
    validation = validate_candidate(baseline, candidate, policy)

    current_hash = sha256_text(dump_yaml(candidate))
    original_hash = audit["hashes"]["candidate_spec_sha256"]
    audit["validation"] = validation
    audit["hashes"]["current_candidate_spec_sha256"] = current_hash
    audit["human_modified_candidate"] = current_hash != original_hash
    if audit.get("status") == "awaiting_human":
        audit["status"] = "validated"
    audit["validated_at"] = utc_now()
    write_json_atomic(audit_path, audit)
    write_latest(run_root, audit["run_id"], audit["status"])
    return {
        "run_id": audit["run_id"],
        "status": audit["status"],
        "run_dir": str(run_dir),
        "validation": validation,
    }


def apply_run(
    *,
    run_root: Path,
    run_id: str,
    policy_path: Path,
    approve: bool,
    reviewer: str,
) -> dict[str, Any]:
    if not approve:
        raise AgentContractError("Apply requires the explicit --approve flag.")
    if not reviewer.strip():
        raise AgentContractError("Apply requires a non-empty --reviewer value.")

    run_root = resolve_path(run_root)
    run_dir = resolve_run_dir(run_root, run_id)
    audit_path = run_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") not in {"awaiting_human", "validated"}:
        raise AgentContractError(
            f"Run status does not allow apply: {audit.get('status')!r}"
        )

    spec_path = resolve_path(audit["canonical_spec_path"])
    current_bytes = spec_path.read_bytes()
    current_hash = sha256_bytes(current_bytes)
    if current_hash != audit["hashes"]["baseline_spec_sha256"]:
        raise AgentContractError(
            "Canonical spec changed after this proposal was created. "
            "Generate a new proposal instead of applying a stale candidate."
        )

    baseline = load_yaml(spec_path)
    candidate_path = run_dir / audit["candidate_path"]
    candidate = load_yaml(candidate_path)
    policy = load_policy(resolve_path(policy_path))
    validation = validate_candidate(baseline, candidate, policy)
    current_candidate_hash = sha256_text(dump_yaml(candidate))

    backup_path = run_dir / "baseline.before_apply.yaml"
    write_text_atomic(backup_path, current_bytes.decode("utf-8"))
    candidate_text = dump_yaml(candidate)
    write_text_atomic(spec_path, candidate_text)

    applied_hash = sha256_bytes(spec_path.read_bytes())
    audit["status"] = "applied"
    audit["validation"] = validation
    audit["hashes"]["current_candidate_spec_sha256"] = current_candidate_hash
    audit["human_modified_candidate"] = (
        current_candidate_hash != audit["hashes"]["candidate_spec_sha256"]
    )
    audit["approval"] = {
        "reviewer": reviewer.strip(),
        "approved_at": utc_now(),
        "explicit_approve_flag": True,
        "baseline_backup": backup_path.name,
        "applied_spec_sha256": applied_hash,
    }
    write_json_atomic(audit_path, audit)
    write_latest(run_root, audit["run_id"], audit["status"])
    return {
        "run_id": audit["run_id"],
        "status": audit["status"],
        "reviewer": reviewer.strip(),
        "canonical_spec": str(spec_path),
        "applied_spec_sha256": applied_hash,
        "backup": str(backup_path),
        "validation": validation,
    }


def reject_run(
    *, run_root: Path, run_id: str, reviewer: str, reason: str
) -> dict[str, Any]:
    if not reviewer.strip():
        raise AgentContractError("Reject requires a non-empty --reviewer value.")
    if not reason.strip():
        raise AgentContractError("Reject requires a non-empty --reason value.")

    run_root = resolve_path(run_root)
    run_dir = resolve_run_dir(run_root, run_id)
    audit_path = run_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") == "applied":
        raise AgentContractError("An applied run cannot be retroactively rejected.")
    audit["status"] = "rejected"
    audit["approval"] = {
        "reviewer": reviewer.strip(),
        "rejected_at": utc_now(),
        "reason": reason.strip(),
    }
    write_json_atomic(audit_path, audit)
    write_latest(run_root, audit["run_id"], audit["status"])
    return {
        "run_id": audit["run_id"],
        "status": audit["status"],
        "reviewer": reviewer.strip(),
        "reason": reason.strip(),
    }


def run_status(*, run_root: Path, run_id: str) -> dict[str, Any]:
    run_root = resolve_path(run_root)
    run_dir = resolve_run_dir(run_root, run_id)
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    return {
        "run_id": audit["run_id"],
        "status": audit["status"],
        "created_at": audit["created_at"],
        "provider": audit["provider"],
        "model": audit["model"],
        "instruction": audit["instruction"],
        "run_dir": str(run_dir),
        "candidate": str(run_dir / audit["candidate_path"]),
        "diff": str(run_dir / audit["diff_path"]),
        "validation": audit["validation"],
        "approval": audit.get("approval"),
    }
