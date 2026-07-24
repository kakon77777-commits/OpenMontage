# EveDirector L4 — Visual Review Workbench

L4 turns the L3 local-agent audit bundle into a visual, local-first approval surface inside Backlot.

It is not yet the final infinite canvas or drag-editable timeline. It is the authority and evidence layer those future interfaces must preserve.

```text
Markdown source
    ↓
canonical video_spec.yaml
    ↓
local-agent candidate
    ↓
semantic changes + source anchors
    ↓
visual Project Graph / Workflow
    ↓
human validate / apply / reject
```

## What the workbench shows

Open a Backlot project and select **EveDirector Review**.

The workbench presents three synchronized areas:

1. **Proposal Runs** — local-agent run history and current status.
2. **Project Graph** — source, canonical specification, candidate, validation, scene nodes, and the human authority gate.
3. **Evidence & Authority** — semantic changes, exact source-line anchors, reviewer identity, and guarded actions.

The primary graph is deliberately finite and deterministic in L4. Infinite canvas navigation, manual node creation, and drag editing remain later phases.

## Start in read-only mode

```bash
python -m backlot open evedirector-drc-search
```

The board links to:

```text
http://127.0.0.1:4750/p/evedirector-drc-search/agent-review
```

Read access exposes only review-safe data:

- run status and timestamps;
- provider and model label;
- user instruction;
- semantic change paths and before/after values;
- candidate scene summaries;
- source line anchors and excerpts;
- a small Project Graph representation;
- approval or rejection metadata.

The API does **not** return:

- `request.json` messages or the complete prompt;
- `response.txt` or raw model output;
- local endpoint tokens;
- environment variables;
- arbitrary project files.

## Enable guarded actions

Backlot remains read-only unless this environment variable is present when the server starts:

```text
BACKLOT_ENABLE_AGENT_ACTIONS=1
```

PowerShell:

```powershell
$env:BACKLOT_ENABLE_AGENT_ACTIONS = "1"
python -m backlot serve --port 4750
```

Bash:

```bash
BACKLOT_ENABLE_AGENT_ACTIONS=1 python -m backlot serve --port 4750
```

This flag does not bypass L3. It only makes the L3 actions reachable from the local web surface.

## Action contract

Every write request must satisfy all of the following:

- `BACKLOT_ENABLE_AGENT_ACTIONS=1` was set before server startup;
- request method is `POST` with JSON;
- custom header `X-EveDirector-Action: review` is present;
- reviewer identity is non-empty;
- the confirmation string exactly matches the selected run;
- L3 source-grounding and policy validation succeeds;
- the canonical specification still has the baseline SHA-256 recorded by the proposal.

Exact confirmation strings:

```text
VALIDATE <run-id>
APPLY <run-id>
REJECT <run-id>
```

Reject additionally requires a reason.

The browser uses a visible confirmation dialog before sending these strings. The server independently verifies them; hiding or modifying a button cannot bypass the contract.

## API

### List proposal runs

```http
GET /api/project/{project_id}/agent-review
```

### Read one review graph

```http
GET /api/project/{project_id}/agent-review/{run_id}
```

### Revalidate

```http
POST /api/project/{project_id}/agent-review/{run_id}/validate
X-EveDirector-Action: review
Content-Type: application/json

{
  "reviewer": "Neo.K",
  "confirmation": "VALIDATE <run-id>"
}
```

### Apply

```http
POST /api/project/{project_id}/agent-review/{run_id}/apply
X-EveDirector-Action: review
Content-Type: application/json

{
  "reviewer": "Neo.K",
  "confirmation": "APPLY <run-id>"
}
```

### Reject

```http
POST /api/project/{project_id}/agent-review/{run_id}/reject
X-EveDirector-Action: review
Content-Type: application/json

{
  "reviewer": "Neo.K",
  "reason": "Keep the original pacing.",
  "confirmation": "REJECT <run-id>"
}
```

## Path and data boundaries

The review router independently checks:

- project ids cannot contain separators or Windows drive syntax;
- run ids are resolved by the L3 run-root guard;
- candidate files must remain inside their run directory;
- canonical specification and policy files must remain inside the repository;
- source files must be Markdown inside the repository;
- only YAML candidate/spec/policy files are accepted;
- malformed or mismatched audit records fail closed.

Even after these checks, Apply still delegates to L3 `apply_run`, which repeats the stale-baseline and candidate validation checks before replacing the canonical specification.

## Live updates

The workbench subscribes to the existing project SSE feed. A new proposal, validation, approval, or rejection updates files under the project workspace; Backlot's watcher then refreshes the run list and graph.

## L4 acceptance

The focused test suite proves:

- list/detail endpoints return a usable review graph;
- raw response-only data is not exposed;
- the review page is mounted before Backlot's catch-all project route;
- actions are disabled by default;
- missing custom headers and incorrect confirmation strings are rejected;
- Validate preserves the canonical specification;
- Apply changes it only through the L3 contract and records the reviewer;
- Reject records the reason and preserves the canonical specification;
- an audit path that escapes the repository is rejected.

## Scope boundary

L4 does not add:

- direct editing of YAML from the browser;
- arbitrary file browsing;
- automatic model invocation from Backlot;
- infinite canvas authoring;
- drag-and-drop scene or timeline editing;
- asset generation;
- voice generation;
- multi-user accounts or remote authorization;
- automatic approval.

Those capabilities must build on, rather than replace, the evidence and human-authority contract established here.
