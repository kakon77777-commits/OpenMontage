# EveDirector L3 — Local AI Agent Specification Proposals

L3 adds a local-language-model planning boundary on top of the source-grounded L2 video pipeline.

The model is not an editor with direct write access. It is a proposal generator.

```text
Markdown source
    ↓
canonical video_spec.yaml
    ↓
local model proposal
    ↓
candidate.video_spec.yaml
    ↓
policy + L2 source-grounding validation
    ↓
human diff review
    ↓
explicit apply or reject
```

## Security and authority model

The canonical specification is never overwritten by `propose`.

A proposal run writes only under the ignored project workspace:

```text
projects/evedirector-drc-search/agent_runs/<run-id>/
```

Each run contains:

```text
request.json
response.txt
candidate.video_spec.yaml
candidate.diff
candidate.unified.diff
audit.json
```

`candidate.diff` is the primary human-review artifact. It reports semantic paths such as `/scenes/divergence/narration`, so YAML serializer formatting does not make an unchanged scene look modified.

`candidate.unified.diff` preserves the raw serialization-level Unified Diff for lower-level audit and debugging. It may contain formatting noise and should not be the main approval view.

`request.json` contains the complete prompt, including the source excerpt and current specification. It remains local under `projects/`, which is excluded from Git. Do not move it into a public repository without reviewing it.

The candidate must satisfy all of these conditions:

- protected identity and path fields are unchanged;
- top-level keys are unchanged;
- every scene remains anchored to an exact phrase in the Markdown source;
- the timeline is contiguous and within the policy duration;
- only approved Remotion cut types and fields are used;
- no arbitrary asset path, URL, shell command, HTML, or new output path is added;
- the canonical file hash is unchanged between proposal and approval.

The apply command requires both an explicit `--approve` flag and a reviewer identity. A stale proposal cannot be applied after the canonical spec changes.

## Supported local endpoints

### Ollama-compatible chat endpoint

```powershell
$env:EVEDIRECTOR_LOCAL_MODEL = "your-local-model"
.\scripts\evedirector-l3.ps1 `
  -Action propose `
  -Provider ollama `
  -Instruction "Improve pacing without adding unsupported claims." `
  -Json
```

Default base endpoint:

```text
http://127.0.0.1:11434
```

The client appends `/api/chat` when needed.

### OpenAI-compatible local server

This covers local servers that expose `/v1/chat/completions`.

```powershell
.\scripts\evedirector-l3.ps1 `
  -Action propose `
  -Provider openai-compatible `
  -Endpoint "http://127.0.0.1:1234" `
  -Model "your-loaded-local-model" `
  -Instruction "Make the conclusion more concise." `
  -Json
```

An optional local endpoint token may be supplied through `EVEDIRECTOR_LOCAL_API_KEY`. The token is sent as an Authorization bearer header and is not written into the audit files.

## Network boundary

By default, the client accepts only loopback addresses, RFC-private IP addresses, `localhost`, and `host.docker.internal`.

Public hostnames are rejected. HTTP redirects are rejected. Credentials, query parameters, and fragments are not allowed inside endpoint URLs.

`--allow-remote` exists for an explicitly reviewed self-hosted endpoint, but it changes the privacy boundary and should not be the default.

## Review flow

Create a proposal:

```bash
python scripts/evedirector_local_agent.py --json propose \
  --provider ollama \
  --model your-local-model \
  --instruction "Improve clarity and pacing without adding unsupported claims."
```

Inspect the latest proposal:

```bash
python scripts/evedirector_local_agent.py --json status --run-id latest
```

Open `candidate.diff` and `candidate.video_spec.yaml` from the returned run directory. Use `candidate.unified.diff` only when the raw YAML representation must also be inspected.

Validate again after any manual candidate edit:

```bash
python scripts/evedirector_local_agent.py --json validate --run-id latest
```

Validation refreshes the semantic review Diff, so a human edit remains visible before approval.

Apply only after review:

```bash
python scripts/evedirector_local_agent.py --json apply \
  --run-id latest \
  --approve \
  --reviewer "Neo.K"
```

Reject without changing the canonical spec:

```bash
python scripts/evedirector_local_agent.py --json reject \
  --run-id latest \
  --reviewer "Neo.K" \
  --reason "The revised pacing removes an important transition."
```

## Windows wrapper

```powershell
.\scripts\evedirector-l3.ps1 -Action status -Json
.\scripts\evedirector-l3.ps1 -Action validate -RunId latest -Json
.\scripts\evedirector-l3.ps1 -Action apply -RunId latest -Reviewer "Neo.K" -Json
```

The wrapper builds an argument array and never uses `Invoke-Expression`.

## Zero-model contract test

The fixture provider tests the entire proposal boundary without contacting a model:

```bash
python scripts/evedirector_local_agent.py --json propose \
  --provider fixture \
  --response-file /path/to/model-response.json \
  --instruction "Contract test."
```

CI uses this mode and local mock HTTP servers to test both supported provider protocols without sending source material to an external service.

## L3 scope boundary

L3 supplies a safe local planning agent for the existing L2 specification. It does not yet add a graphical workflow editor, infinite canvas editing, timeline drag operations, autonomous asset generation, voice generation, multi-agent orchestration, or automatic approval. Human final authority is preserved.
