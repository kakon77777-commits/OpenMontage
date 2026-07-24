from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .common import (
    AgentContractError,
    LocalEndpointError,
    SYSTEM_PROMPT,
    sanitized_endpoint,
    validate_endpoint,
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise LocalEndpointError(
            f"Local model endpoint attempted an HTTP redirect ({code}) to {newurl!r}."
        )


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    max_response_bytes: int,
    api_key: str | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read(max_response_bytes + 1)
            if len(raw) > max_response_bytes:
                raise AgentContractError(
                    f"Model response exceeded {max_response_bytes} bytes."
                )
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Local model endpoint returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach local model endpoint: {exc.reason}") from exc

    try:
        decoded = json.loads(raw.decode(charset))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Local model endpoint did not return valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("Local model endpoint returned a non-object JSON payload.")
    return decoded


def default_endpoint(provider: str) -> str:
    if provider == "ollama":
        return "http://127.0.0.1:11434"
    if provider == "openai-compatible":
        return "http://127.0.0.1:1234"
    return ""


def provider_url(provider: str, endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if provider == "ollama":
        return endpoint if endpoint.endswith("/api/chat") else endpoint + "/api/chat"
    if provider == "openai-compatible":
        return (
            endpoint
            if endpoint.endswith("/v1/chat/completions")
            else endpoint + "/v1/chat/completions"
        )
    raise AgentContractError(f"Provider has no HTTP endpoint: {provider}")


def numbered_source(source_text: str) -> str:
    return "\n".join(
        f"{line_number:04d}: {line}"
        for line_number, line in enumerate(source_text.splitlines(), start=1)
    )


def build_messages(
    *,
    instruction: str,
    baseline: dict[str, Any],
    source_text: str,
    policy: dict[str, Any],
    prompt_template: str,
) -> list[dict[str, str]]:
    user_prompt = prompt_template.format(
        instruction=instruction.strip(),
        immutable_fields=json.dumps(policy["immutable_fields"], ensure_ascii=False),
        allowed_cut_types=json.dumps(policy["allowed_cut_types"], ensure_ascii=False),
        current_spec_json=json.dumps(baseline, ensure_ascii=False, indent=2),
        source_numbered=numbered_source(source_text),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def response_content(provider: str, payload: dict[str, Any]) -> str:
    if provider == "ollama":
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("Ollama response has no message.content string.")
        return message["content"]
    if provider == "openai-compatible":
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI-compatible response has no choices.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError(
                "OpenAI-compatible response has no choices[0].message.content string."
            )
        return message["content"]
    raise AgentContractError(f"Unsupported provider response: {provider}")


def call_provider(
    *,
    provider: str,
    endpoint: str | None,
    model: str,
    messages: list[dict[str, str]],
    timeout_seconds: float,
    max_response_bytes: int,
    response_file: Path | None,
    allow_remote: bool,
    api_key: str | None,
) -> tuple[str, str]:
    if provider == "fixture":
        if response_file is None:
            raise AgentContractError("--response-file is required for fixture provider.")
        raw = response_file.read_bytes()
        if len(raw) > max_response_bytes:
            raise AgentContractError(
                f"Fixture response exceeded {max_response_bytes} bytes."
            )
        return raw.decode("utf-8"), "fixture://local-file"

    if not model.strip():
        raise AgentContractError("--model is required for a local model provider.")
    base_endpoint = endpoint or default_endpoint(provider)
    validate_endpoint(base_endpoint, allow_remote=allow_remote)
    url = provider_url(provider, base_endpoint)

    if provider == "ollama":
        request_payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
    elif provider == "openai-compatible":
        request_payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
    else:
        raise AgentContractError(f"Unsupported provider: {provider}")

    raw_payload = post_json(
        url,
        request_payload,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        api_key=api_key,
    )
    return response_content(provider, raw_payload), sanitized_endpoint(url)


def extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        last_fence = text.rfind("```")
        if first_newline != -1 and last_fence > first_newline:
            text = text[first_newline + 1 : last_fence].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AgentContractError("Model response contains no JSON object.")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AgentContractError(
                f"Model response JSON could not be parsed: {exc}"
            ) from exc
    if not isinstance(payload, dict):
        raise AgentContractError("Model response must be a JSON object.")
    return payload


def candidate_from_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(payload.get("video_spec"), dict):
        return payload["video_spec"], {
            "rationale": payload.get("rationale", ""),
            "changed_scene_ids": payload.get("changed_scene_ids", []),
            "assumptions": payload.get("assumptions", []),
        }
    if {"version", "project_id", "scenes"}.issubset(payload):
        return payload, {"rationale": "", "changed_scene_ids": [], "assumptions": []}
    raise AgentContractError(
        "Response must contain a video_spec object or be a complete video spec."
    )


def changed_scene_ids(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> list[str]:
    before = {
        str(scene.get("id")): scene
        for scene in baseline.get("scenes", [])
        if isinstance(scene, dict)
    }
    after = {
        str(scene.get("id")): scene
        for scene in candidate.get("scenes", [])
        if isinstance(scene, dict)
    }
    changed = set(before) ^ set(after)
    for scene_id in set(before) & set(after):
        if before[scene_id] != after[scene_id]:
            changed.add(scene_id)
    return sorted(changed)
