from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .common import (
    DEFAULT_POLICY,
    DEFAULT_PROMPT_TEMPLATE,
    DEFAULT_RUN_ROOT,
    DEFAULT_SPEC,
)
from .runs import apply_run, propose, reject_run, run_status, validate_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EveDirector L3 local-agent proposal and approval boundary."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--prompt-template", type=Path, default=DEFAULT_PROMPT_TEMPLATE)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("propose")
    p.add_argument("--instruction", required=True)
    p.add_argument(
        "--provider",
        choices=["ollama", "openai-compatible", "fixture"],
        default=os.environ.get("EVEDIRECTOR_LOCAL_PROVIDER", "ollama"),
    )
    p.add_argument("--endpoint", default=os.environ.get("EVEDIRECTOR_LOCAL_ENDPOINT"))
    p.add_argument("--model", default=os.environ.get("EVEDIRECTOR_LOCAL_MODEL", ""))
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--response-file", type=Path)
    p.add_argument("--allow-remote", action="store_true")
    p.add_argument("--api-key-env", default="EVEDIRECTOR_LOCAL_API_KEY")

    p = subparsers.add_parser("validate")
    p.add_argument("--run-id", default="latest")

    p = subparsers.add_parser("apply")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--approve", action="store_true")
    p.add_argument("--reviewer", required=True)

    p = subparsers.add_parser("reject")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--reason", required=True)

    p = subparsers.add_parser("status")
    p.add_argument("--run-id", default="latest")
    return parser.parse_args(argv)


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"L3 run: {payload.get('run_id')}")
    print(f"Status: {payload.get('status')}")
    if payload.get("candidate"):
        print(f"Candidate: {payload['candidate']}")
    if payload.get("diff"):
        print(f"Diff: {payload['diff']}")
    if payload.get("canonical_spec"):
        print(f"Canonical spec: {payload['canonical_spec']}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "propose":
        result = propose(
            spec_path=args.spec,
            policy_path=args.policy,
            prompt_template_path=args.prompt_template,
            run_root=args.run_root,
            instruction=args.instruction,
            provider=args.provider,
            endpoint=args.endpoint,
            model=args.model,
            timeout_seconds=args.timeout,
            response_file=args.response_file,
            allow_remote=args.allow_remote,
            api_key=os.environ.get(args.api_key_env) or None,
        )
    elif args.command == "validate":
        result = validate_run(
            run_root=args.run_root, run_id=args.run_id, policy_path=args.policy
        )
    elif args.command == "apply":
        result = apply_run(
            run_root=args.run_root,
            run_id=args.run_id,
            policy_path=args.policy,
            approve=args.approve,
            reviewer=args.reviewer,
        )
    elif args.command == "reject":
        result = reject_run(
            run_root=args.run_root,
            run_id=args.run_id,
            reviewer=args.reviewer,
            reason=args.reason,
        )
    else:
        result = run_status(run_root=args.run_root, run_id=args.run_id)
    emit(result, as_json=args.json)
    return 0
