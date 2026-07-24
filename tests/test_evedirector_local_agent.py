from __future__ import annotations

import copy
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evedirector_local_agent.py"
SPEC_PATH = ROOT / "examples" / "drc-search-video" / "video_spec.yaml"
POLICY_PATH = ROOT / "examples" / "drc-search-video" / "local_agent_policy.yaml"
PROMPT_PATH = ROOT / "prompts" / "evedirector_local_video_spec.md"

module_spec = importlib.util.spec_from_file_location("evedirector_local_agent", SCRIPT)
assert module_spec and module_spec.loader
agent = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(agent)


def baseline() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def scene_by_id(value: dict, scene_id: str) -> dict:
    return next(scene for scene in value["scenes"] if scene["id"] == scene_id)


def candidate() -> dict:
    value = copy.deepcopy(baseline())
    scene_by_id(value, "divergence")["narration"] = (
        "Divergence treats a query as a seed and opens multiple grounded directions."
    )
    return value


def response_file(tmp_path: Path, value: dict | None = None) -> Path:
    payload = {
        "video_spec": value or candidate(),
        "rationale": "Clarify the divergence scene.",
        "changed_scene_ids": ["divergence"],
        "assumptions": [],
    }
    path = tmp_path / "response.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_endpoint_policy_blocks_public_hosts() -> None:
    assert agent.endpoint_is_local("http://127.0.0.1:11434")
    assert agent.endpoint_is_local("http://192.168.1.20:1234")
    assert agent.endpoint_is_local("http://host.docker.internal:11434")
    with pytest.raises(agent.LocalEndpointError):
        agent.validate_endpoint("https://example.com/v1")


def test_endpoint_policy_rejects_credentials_and_query_data() -> None:
    with pytest.raises(agent.LocalEndpointError):
        agent.validate_endpoint("http://user:pass@127.0.0.1:11434")
    with pytest.raises(agent.LocalEndpointError):
        agent.validate_endpoint("http://127.0.0.1:11434?token=secret")


def test_extracts_fenced_json() -> None:
    raw = "```json\n" + json.dumps({"video_spec": candidate()}) + "\n```"
    payload = agent.extract_json_object(raw)
    value, metadata = agent.candidate_from_payload(payload)
    assert value["project_id"] == "evedirector-drc-search"
    assert metadata["changed_scene_ids"] == []


def test_candidate_must_preserve_protected_fields() -> None:
    value = candidate()
    value["source_path"] = "other.md"
    with pytest.raises(agent.AgentContractError, match="Protected field"):
        agent.validate_candidate(baseline(), value, policy())


def test_candidate_must_remain_source_grounded() -> None:
    value = candidate()
    scene_by_id(value, "divergence")["source_contains"] = "Not in the source"
    with pytest.raises(agent.AgentContractError, match="Source claim not found"):
        agent.validate_candidate(baseline(), value, policy())


def test_candidate_rejects_unapproved_cut_fields() -> None:
    value = candidate()
    scene_by_id(value, "divergence")["cut"]["source"] = "../../secret.mp4"
    with pytest.raises(agent.AgentContractError, match="unsupported cut fields"):
        agent.validate_candidate(baseline(), value, policy())


def test_fixture_proposal_is_review_only(tmp_path: Path) -> None:
    original = SPEC_PATH.read_bytes()
    result = agent.propose(
        spec_path=SPEC_PATH,
        policy_path=POLICY_PATH,
        prompt_template_path=PROMPT_PATH,
        run_root=tmp_path / "runs",
        instruction="Improve clarity.",
        provider="fixture",
        endpoint=None,
        model="",
        timeout_seconds=5,
        response_file=response_file(tmp_path),
        allow_remote=False,
        api_key=None,
    )

    assert result["status"] == "awaiting_human"
    assert result["canonical_spec_unchanged"] is True
    assert SPEC_PATH.read_bytes() == original
    run_dir = Path(result["run_dir"])
    assert (run_dir / "candidate.video_spec.yaml").is_file()
    assert (run_dir / "candidate.diff").is_file()
    assert (run_dir / "candidate.unified.diff").is_file()
    semantic_diff = (run_dir / "candidate.diff").read_text(encoding="utf-8")
    assert "/scenes/divergence/narration" in semantic_diff
    assert "/scenes/old-vs-drc" not in semantic_diff
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["validation"]["valid"] is True
    assert audit["semantic_change_count"] == 1
    assert audit["status"] == "awaiting_human"


def test_apply_requires_explicit_approval_and_reviewer(tmp_path: Path) -> None:
    temporary_spec = tmp_path / "video_spec.yaml"
    temporary_spec.write_bytes(SPEC_PATH.read_bytes())
    run_root = tmp_path / "runs"
    proposed = agent.propose(
        spec_path=temporary_spec,
        policy_path=POLICY_PATH,
        prompt_template_path=PROMPT_PATH,
        run_root=run_root,
        instruction="Improve clarity.",
        provider="fixture",
        endpoint=None,
        model="",
        timeout_seconds=5,
        response_file=response_file(tmp_path),
        allow_remote=False,
        api_key=None,
    )
    with pytest.raises(agent.AgentContractError, match="explicit --approve"):
        agent.apply_run(
            run_root=run_root,
            run_id=proposed["run_id"],
            policy_path=POLICY_PATH,
            approve=False,
            reviewer="Neo.K",
        )

    applied = agent.apply_run(
        run_root=run_root,
        run_id=proposed["run_id"],
        policy_path=POLICY_PATH,
        approve=True,
        reviewer="Neo.K",
    )
    assert applied["status"] == "applied"
    new_spec = yaml.safe_load(temporary_spec.read_text(encoding="utf-8"))
    assert scene_by_id(new_spec, "divergence")["narration"].startswith(
        "Divergence treats"
    )
    assert Path(applied["backup"]).is_file()


class _ModelHandler(BaseHTTPRequestHandler):
    response_payload: dict = {}
    seen_path = ""
    seen_body: dict = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).seen_path = self.path
        type(self).seen_body = json.loads(self.rfile.read(length))
        raw = json.dumps(type(self).response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        return


@pytest.mark.parametrize(
    ("provider", "path", "wrapper"),
    [
        ("ollama", "/api/chat", lambda content: {"message": {"content": content}}),
        (
            "openai-compatible",
            "/v1/chat/completions",
            lambda content: {"choices": [{"message": {"content": content}}]},
        ),
    ],
)
def test_local_http_adapters(provider: str, path: str, wrapper) -> None:
    content = json.dumps({"video_spec": candidate()}, ensure_ascii=False)
    _ModelHandler.response_payload = wrapper(content)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        raw, endpoint = agent.call_provider(
            provider=provider,
            endpoint=f"http://127.0.0.1:{server.server_port}",
            model="local-test-model",
            messages=[{"role": "user", "content": "test"}],
            timeout_seconds=5,
            max_response_bytes=1024 * 1024,
            response_file=None,
            allow_remote=False,
            api_key=None,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert json.loads(raw)["video_spec"]["project_id"] == "evedirector-drc-search"
    assert _ModelHandler.seen_path == path
    assert endpoint.endswith(path)
    assert _ModelHandler.seen_body["model"] == "local-test-model"
