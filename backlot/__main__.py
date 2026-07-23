"""Backlot CLI.

    python -m backlot open [project-id]              # start server if needed, open browser
    python -m backlot serve [--host HOST] [--port N] # run the server in the foreground

``open`` is idempotent and non-fatal by design: agents call it at pipeline
initialization and must continue the production even if it fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from backlot import DEFAULT_PORT


def _port() -> int:
    """Resolve the listening port for both local and hosted runtimes.

    ``BACKLOT_PORT`` remains the project-specific setting. ``PORT`` is accepted
    as a deployment-platform fallback because many container hosts inject it.
    """
    raw = os.environ.get("BACKLOT_PORT") or os.environ.get("PORT") or DEFAULT_PORT
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def _host() -> str:
    """Resolve the bind host while preserving localhost as the safe default."""
    return os.environ.get("BACKLOT_HOST", "127.0.0.1")


def _server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _spawn_server(port: int) -> None:
    """Start the server as a detached background process for local ``open``."""
    cmd = [
        sys.executable,
        "-m",
        "backlot",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def cmd_open(project_id: str | None) -> int:
    port = _port()
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"backlot: could not start server ({exc}) — continuing without the board")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print("backlot: server did not come up in time — continuing without the board")
            return 1
    url = f"http://127.0.0.1:{port}/"
    if project_id:
        url = f"http://127.0.0.1:{port}/p/{project_id}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"backlot: {url}")
    return 0


def cmd_serve(port: int, host: str) -> int:
    import uvicorn

    uvicorn.run("backlot.server:app", host=host, port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backlot", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_open = sub.add_parser("open", help="open the board in the browser (starts server if needed)")
    p_open.add_argument("project_id", nargs="?", default=None)

    p_serve = sub.add_parser("serve", help="run the Backlot server in the foreground")
    p_serve.add_argument("--host", default=_host())
    p_serve.add_argument("--port", type=int, default=_port())

    args = parser.parse_args(argv)
    if args.command == "open":
        return cmd_open(args.project_id)
    if args.command == "serve":
        return cmd_serve(args.port, args.host)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
