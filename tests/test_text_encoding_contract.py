"""Guard the Windows text-encoding contract.

Every text-mode file read or write in production code must declare
``encoding="utf-8"``. Python still resolves a bare ``open()`` through the
process locale, so on a Windows host with a CJK code page (cp950, cp936,
cp932) any UTF-8 schema, manifest or checkpoint fails to decode. The Linux
CI runners are UTF-8 by default and cannot observe this class of failure,
so it is asserted here instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Production code only. Fixtures and generated project directories are excluded.
SCANNED_PACKAGES = ("lib", "schemas", "backlot", "tools", "scripts")

EXCLUDED_PARTS = {"__pycache__", ".venv", "node_modules", "projects"}

TEXT_IO_METHODS = {"read_text", "write_text"}


def _python_sources() -> list[Path]:
    sources: list[Path] = []
    for package in SCANNED_PACKAGES:
        package_dir = REPO_ROOT / package
        if not package_dir.is_dir():
            continue
        for path in sorted(package_dir.rglob("*.py")):
            if EXCLUDED_PARTS.isdisjoint(path.parts):
                sources.append(path)
    return sources


def _declared_mode(call: ast.Call) -> str | None:
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        return str(call.args[1].value)
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return None


def _is_text_io_call(call: ast.Call) -> bool:
    func = call.func
    # Only the builtin ``open``. ``Image.open``, ``os.open``, ``webbrowser.open``
    # and ``opener.open`` are attribute calls with unrelated semantics.
    if isinstance(func, ast.Name) and func.id == "open":
        mode = _declared_mode(call)
        return mode is None or "b" not in mode
    if isinstance(func, ast.Attribute) and func.attr in TEXT_IO_METHODS:
        return True
    return False


def _offenders() -> list[str]:
    found: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_text_io_call(node):
                continue
            if any(keyword.arg == "encoding" for keyword in node.keywords):
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            found.append(f"{relative}:{node.lineno}")
    return found


def test_text_io_always_declares_utf8_encoding() -> None:
    offenders = _offenders()
    assert not offenders, (
        "Text-mode file I/O without encoding=\"utf-8\" breaks on Windows CJK "
        "code pages:\n  " + "\n  ".join(offenders)
    )


def test_scanner_sees_the_production_packages() -> None:
    # A silent path change would turn the guard above into a no-op.
    assert len(_python_sources()) > 50
