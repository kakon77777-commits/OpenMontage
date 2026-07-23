"""EveDirector local-first validation harness for OpenMontage.

This entry point proves the local execution path before any paid AI provider is
configured. It deliberately separates four questions:

1. Is the machine capable of running OpenMontage?
2. Does the Backlot project/checkpoint/event contract work?
3. Can the Remotion composer produce a real MP4 without API keys?
4. Can the generated project be opened in the local Backlot board?

Examples:

    python scripts/evedirector_local_first.py doctor
    python scripts/evedirector_local_first.py smoke
    python scripts/evedirector_local_first.py demo --name code-to-screen
    python scripts/evedirector_local_first.py board
    python scripts/evedirector_local_first.py all

No secret values are read or printed by this script.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT_ID = "evedirector-local-smoke"
DEFAULT_DEMO = "code-to-screen"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    detail: str
    remediation: str | None = None


def _command_path(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _version_line(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return output[0] if output else f"exit={result.returncode}"


def _module_check(module: str, package_hint: str, required: bool = True) -> CheckResult:
    ok = importlib.util.find_spec(module) is not None
    return CheckResult(
        name=f"python:{module}",
        ok=ok,
        required=required,
        detail="installed" if ok else "missing",
        remediation=None if ok else f"Install with: python -m pip install {package_hint}",
    )


def collect_checks() -> list[CheckResult]:
    checks: list[CheckResult] = []

    py_ok = sys.version_info >= (3, 10)
    checks.append(
        CheckResult(
            name="python",
            ok=py_ok,
            required=True,
            detail=f"{sys.version.split()[0]} at {sys.executable}",
            remediation=None if py_ok else "Install Python 3.10 or newer.",
        )
    )

    commands = [
        ("node", ("node", "node.exe"), ["--version"], True, "Install Node.js 18+."),
        ("npm", ("npm.cmd", "npm", "npm.exe"), ["--version"], True, "Install npm with Node.js."),
        ("npx", ("npx.cmd", "npx", "npx.exe"), ["--version"], True, "Install npx with Node.js."),
        ("ffmpeg", ("ffmpeg", "ffmpeg.exe"), ["-version"], True, "Install FFmpeg and add it to PATH."),
        ("git", ("git", "git.exe"), ["--version"], False, "Install Git for updates and contribution workflows."),
    ]
    for label, names, args, required, remediation in commands:
        path = _command_path(*names)
        checks.append(
            CheckResult(
                name=label,
                ok=path is not None,
                required=required,
                detail=_version_line([path, *args]) if path else "not found on PATH",
                remediation=None if path else remediation,
            )
        )

    checks.extend(
        [
            _module_check("yaml", "pyyaml"),
            _module_check("pydantic", "pydantic"),
            _module_check("jsonschema", "jsonschema"),
            _module_check("PIL", "Pillow"),
            _module_check("fastapi", "fastapi"),
            _module_check("uvicorn", "uvicorn"),
        ]
    )

    paths = [
        ("remotion composer", REPO_ROOT / "remotion-composer" / "package.json", True),
        ("zero-key demo props", REPO_ROOT / "remotion-composer" / "public" / "demo-props", True),
        ("Backlot simulator", REPO_ROOT / "scripts" / "backlot_simulate_run.py", True),
        ("environment file", REPO_ROOT / ".env", False),
    ]
    for label, path, required in paths:
        exists = path.exists()
        checks.append(
            CheckResult(
                name=label,
                ok=exists,
                required=required,
                detail=str(path.relative_to(REPO_ROOT)) if exists else "missing",
                remediation=(
                    None
                    if exists
                    else (
                        "Run the setup procedure from the repository root."
                        if required
                        else "Optional: copy .env.example to .env only when cloud providers are needed."
                    )
                ),
            )
        )

    node_modules = REPO_ROOT / "remotion-composer" / "node_modules"
    checks.append(
        CheckResult(
            name="Remotion dependencies",
            ok=node_modules.is_dir(),
            required=False,
            detail="installed" if node_modules.is_dir() else "not installed yet",
            remediation=(
                None
                if node_modules.is_dir()
                else "The demo command will run npm install automatically, or run make setup first."
            ),
        )
    )

    return checks


def print_checks(checks: Iterable[CheckResult], as_json: bool = False) -> bool:
    checks = list(checks)
    if as_json:
        payload = {
            "ready": not any(c.required and not c.ok for c in checks),
            "checks": [asdict(c) for c in checks],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("EveDirector local-first doctor")
        print(f"Repository: {REPO_ROOT}")
        print()
        for check in checks:
            marker = "OK" if check.ok else ("FAIL" if check.required else "WARN")
            requirement = "required" if check.required else "optional"
            print(f"[{marker:4}] {check.name} ({requirement}) — {check.detail}")
            if check.remediation and not check.ok:
                print(f"       {check.remediation}")
        print()
        required_failures = [c for c in checks if c.required and not c.ok]
        if required_failures:
            print(f"Not ready: {len(required_failures)} required check(s) failed.")
        else:
            print("Ready for the zero-key local validation path.")
    return not any(c.required and not c.ok for c in checks)


def run(command: list[str], *, label: str) -> None:
    print()
    print(f"==> {label}")
    print("    " + " ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def simulate(project_id: str, fast: bool = True) -> None:
    command = [sys.executable, "scripts/backlot_simulate_run.py", "--project", project_id]
    if fast:
        command.append("--fast")
    run(command, label="Writing a schema-valid Backlot production run")


def render_demo(name: str) -> None:
    run(
        [sys.executable, "render_demo.py", name],
        label=f"Rendering zero-key Remotion demo: {name}",
    )


def open_board(project_id: str) -> None:
    run(
        [sys.executable, "-m", "backlot", "open", project_id],
        label=f"Opening Backlot board for {project_id}",
    )


def run_smoke(project_id: str) -> None:
    ready = print_checks(collect_checks())
    if not ready:
        raise SystemExit(2)
    run([sys.executable, "render_demo.py", "--list"], label="Discovering zero-key demos")
    simulate(project_id=project_id, fast=True)
    print()
    print("Smoke validation completed.")
    print(f"Board command: {sys.executable} -m backlot open {project_id}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit doctor results as JSON.")
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_ID,
        help=f"Project id used by the Backlot simulator (default: {DEFAULT_PROJECT_ID}).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check local zero-key prerequisites.")
    subparsers.add_parser("smoke", help="Run non-rendering contract and Backlot checks.")

    demo_parser = subparsers.add_parser("demo", help="Render one real MP4 without API keys.")
    demo_parser.add_argument("--name", default=DEFAULT_DEMO, help=f"Demo name (default: {DEFAULT_DEMO}).")

    subparsers.add_parser("board", help="Open the local Backlot board.")

    all_parser = subparsers.add_parser("all", help="Doctor, simulate, render one MP4, then open Backlot.")
    all_parser.add_argument("--name", default=DEFAULT_DEMO, help=f"Demo name (default: {DEFAULT_DEMO}).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "doctor":
        return 0 if print_checks(collect_checks(), as_json=args.json) else 2
    if args.command == "smoke":
        run_smoke(args.project)
        return 0
    if args.command == "demo":
        if not print_checks(collect_checks(), as_json=False):
            return 2
        render_demo(args.name)
        return 0
    if args.command == "board":
        open_board(args.project)
        return 0
    if args.command == "all":
        if not print_checks(collect_checks(), as_json=False):
            return 2
        simulate(args.project, fast=True)
        render_demo(args.name)
        open_board(args.project)
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
