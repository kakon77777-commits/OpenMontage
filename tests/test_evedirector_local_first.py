from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "evedirector_local_first.py"
SPEC = importlib.util.spec_from_file_location("evedirector_local_first", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_doctor_command_defaults() -> None:
    args = MODULE.parse_args(["doctor"])
    assert args.command == "doctor"
    assert args.project == MODULE.DEFAULT_PROJECT_ID
    assert args.json is False


def test_demo_name_can_be_overridden() -> None:
    args = MODULE.parse_args(["--project", "proj-test", "demo", "--name", "world-in-numbers"])
    assert args.command == "demo"
    assert args.project == "proj-test"
    assert args.name == "world-in-numbers"


def test_required_failure_marks_doctor_not_ready(capsys) -> None:
    checks = [
        MODULE.CheckResult(
            name="required-runtime",
            ok=False,
            required=True,
            detail="missing",
            remediation="install it",
        )
    ]
    assert MODULE.print_checks(checks) is False
    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "Not ready" in output


def test_optional_failure_does_not_block(capsys) -> None:
    checks = [
        MODULE.CheckResult(
            name="optional-runtime",
            ok=False,
            required=False,
            detail="missing",
            remediation="optional install",
        )
    ]
    assert MODULE.print_checks(checks) is True
    output = capsys.readouterr().out
    assert "WARN" in output
    assert "Ready for the zero-key local validation path" in output


def test_json_diagnostics_have_stable_shape(capsys) -> None:
    checks = [
        MODULE.CheckResult(
            name="python",
            ok=True,
            required=True,
            detail="3.11",
        )
    ]
    assert MODULE.print_checks(checks, as_json=True) is True
    output = capsys.readouterr().out
    assert '"ready": true' in output
    assert '"checks"' in output
