<h1 align="center">EveDirector</h1>

<p align="center"><strong>A source-grounded video production workbench where the model proposes and the human decides.</strong></p>

<p align="center">
  <a href="#the-authority-model">Authority Model</a> &nbsp;·&nbsp;
  <a href="#the-l0l6-stack">L0–L6 Stack</a> &nbsp;·&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;·&nbsp;
  <a href="#the-unified-workbench">Unified Workbench</a> &nbsp;·&nbsp;
  <a href="#safety-boundaries">Safety Boundaries</a> &nbsp;·&nbsp;
  <a href="#upstream-openmontage">Upstream</a>
</p>

> **This is a fork.** EveDirector is built on [**calesthio/OpenMontage**](https://github.com/calesthio/OpenMontage)
> and inherits its pipelines, tool registry, checkpoint contracts, Backlot board and Remotion composer.
> Licensed under [GNU AGPLv3](LICENSE), the same as upstream. The complete upstream README —
> provider matrix, pipeline catalogue, style system and credits — is preserved verbatim at
> [`docs/UPSTREAM_README.md`](docs/UPSTREAM_README.md).
>
> EveDirector is an EVEMISSLAB project. It does not speak for the upstream project,
> and upstream sponsors do not sponsor this fork.

---

## What EveDirector adds

OpenMontage lets an AI assistant produce video. EveDirector answers a narrower, harder question:

**when a model edits your video, what stops it from inventing the content — and who signs off?**

The answer is a hard separation between *proposing* and *deciding*. A local model may only ever
write a **candidate run**. Every scene in that candidate must resolve to a concrete line in a real
source document. A human reads the semantic diff alongside the source evidence, then explicitly
validates, rejects, or applies. Nothing else can touch the canonical spec.

That constraint is the product. The canvas, workflow, timeline and inspector are four projections
of one grounded scene model — not four editors racing each other for authority.

---

## The authority model

```text
Markdown source document
  → source-anchored candidate run          (L3, local model only, never the canonical spec)
  → semantic diff + per-scene evidence     (L4, raw prompts and responses never reach the API)
  → allow-listed operations                (L5, constrained editor — derive, never mutate)
  → new derived run                        (re-validated against source and policy)
  → explicit human Validate / Apply / Reject
  → re-render + FFprobe verification
```

Two things are deliberately *not* authority:

- **Canvas layout** lives only in browser local storage. Dragging a node reorganises your thinking;
  it produces no operation, no run, no audit entry, and cannot enter the video spec.
- **The L6 page itself** is read-only. It has no apply endpoint. Semantic edits are delegated back
  to the L5 derive endpoint, which re-runs every L3 validation server-side.

Writes require all of: `BACKLOT_ENABLE_AGENT_ACTIONS=1`, the `X-EveDirector-Action: review` header,
a non-empty reviewer identity, and an explicit `VALIDATE` / `APPLY` / `REJECT` / `EDIT` intent for a
named run id. A stale candidate cannot be applied.

---

## The L0–L6 stack

| Layer | What it establishes | Documentation |
|---|---|---|
| **L0 / L1** | Environment doctor, Backlot contracts, zero-key Remotion render | [`EVEDIRECTOR_LOCAL_FIRST.md`](docs/EVEDIRECTOR_LOCAL_FIRST.md) |
| **L2** | Real Markdown → scene plan → Remotion → MP4, every scene source-anchored | [`EVEDIRECTOR_L2_MARKDOWN_VIDEO.md`](docs/EVEDIRECTOR_L2_MARKDOWN_VIDEO.md) |
| **L3** | Local model candidates, policy, source anchoring, semantic diff, audit ledger | [`EVEDIRECTOR_L3_LOCAL_AGENT.md`](docs/EVEDIRECTOR_L3_LOCAL_AGENT.md) |
| **L4** | Visual review workbench — evidence, diff, Validate / Apply / Reject | [`EVEDIRECTOR_L4_REVIEW_WORKBENCH.md`](docs/EVEDIRECTOR_L4_REVIEW_WORKBENCH.md) |
| **L5** | Constrained project-graph and workflow editing via derived runs | [`EVEDIRECTOR_L5_CONSTRAINED_EDITOR.md`](docs/EVEDIRECTOR_L5_CONSTRAINED_EDITOR.md) |
| **L5+** | Overlay timeline guard — structural edits locked until overlays are scene-anchored | [`EVEDIRECTOR_L5_OVERLAY_TIMELINE_GUARD.md`](docs/EVEDIRECTOR_L5_OVERLAY_TIMELINE_GUARD.md) |
| **L6** | Unified infinite canvas + workflow + timeline + inspector over one scene model | [`EVEDIRECTOR_L6_UNIFIED_WORKBENCH.md`](docs/EVEDIRECTOR_L6_UNIFIED_WORKBENCH.md) |

Hosted / containerised deployment is documented separately in
[`docs/WEB_RUNTIME.md`](docs/WEB_RUNTIME.md) (`Dockerfile.web`, `docker-compose.web.yml`).

The original Traditional Chinese acceptance report and local handoff manual are kept as project
records in [`docs/EVEDIRECTOR_L6_ACCEPTANCE_REPORT_zh-TW.md`](docs/EVEDIRECTOR_L6_ACCEPTANCE_REPORT_zh-TW.md)
and [`docs/EVEDIRECTOR_L0-L6_HANDOFF_zh-TW.md`](docs/EVEDIRECTOR_L0-L6_HANDOFF_zh-TW.md), each with a
note marking which of their branch instructions `main` has since superseded.

---

## Quick start

### Prerequisites

Python 3.10+, Node.js, npm/npx, and FFmpeg + FFprobe on `PATH`.

### Diagnose the machine

```bash
python scripts/evedirector_local_first.py doctor
```

On Windows PowerShell:

```powershell
.\scripts\evedirector-local-first.ps1 doctor
```

The doctor reports on Python, Node, npm/npx, FFmpeg/FFprobe, the required Python packages, the
Remotion composer, the Backlot simulator, and the zero-key demo props. Fix everything it marks
`[FAIL]` before going further — a green doctor is the precondition for every layer above it.

Then run the full L1 zero-key validation:

```bash
make local-first
```

### Build a real video from a real document

```bash
make l2-validate   # every scene must resolve to a source line
make l2-build      # project, grounding manifest, OpenMontage artifacts
make l2-render     # Remotion → MP4 → FFprobe verification
```

Output lands in `projects/evedirector-drc-search/renders/drc-search.mp4` with a verification
report at `projects/evedirector-drc-search/artifacts/render_report.json`.

The reference render is zero-key — no cloud API was used: **h264, 1920×1080, 30 fps,
76.05 s, 11,042,313 bytes, 0 warnings.**

### Start Backlot

Read-only:

```bash
python -m backlot serve --port 4750
```

To permit guarded agent and editor writes:

```powershell
$env:BACKLOT_ENABLE_AGENT_ACTIONS = "1"
python -m backlot serve --port 4750
```

Bind locally only. Do not expose this to the public internet before reading
[Safety boundaries](#safety-boundaries).

---

## The unified workbench

With Backlot running:

| View | Route |
|---|---|
| Review workbench (L4) | `/p/<project-id>/agent-review` |
| Constrained editor (L5) | `/p/<project-id>/agent-edit/<run-id>` |
| Unified workbench (L6) | `/p/<project-id>/director/<run-id>` |

For the reference project that is
`http://127.0.0.1:4750/p/evedirector-drc-search/agent-review`.

The L6 API refuses to render at all unless scene identity and ordering agree across
`model.scenes`, `views.canvas`, `views.workflow` and `views.timeline`. Four views that disagree
about what the video *is* would be worse than no views, so the contract fails loudly instead.

The inspector exposes only the L5 allow-list: project title, theme, scene narration, and permitted
string cut fields. Scene ids, source anchors, cut types, terminal steps, overlays, raw prompts and
raw model responses are never editable and never leave the server.

---

## Safety boundaries

These hold across every layer and should not be relaxed by widening an allow-list:

- A model cannot modify the canonical spec. Neither can a browser.
- Every candidate scene must anchor to a real source line.
- A stale candidate cannot be applied.
- Reviewer identity cannot be blank; apply must be explicit.
- Raw prompts and raw model responses never enter the review API.
- Canvas layout never enters the semantic spec.
- Structural timeline edits stay locked while overlays use absolute seconds.
- Local model endpoints are restricted to `localhost`, loopback, and private-network addresses.

Never paste an API key into a conversation, a commit, or a command history.

## Deliberately out of scope

Overlay→scene anchoring, an overlay editor, adding or deleting scenes, arbitrary graph nodes and
edges, audio waveforms, a keyframe editor, provider/asset/TTS APIs, multi-user collaboration,
remote deployment, private MCP, and cost or organisational permissions.

Each of these needs its own data model, permission surface and regression tests. None of them
should arrive as a loosened allow-list.

---

## Testing

The EveDirector contract suite runs without API keys:

```bash
python -m pytest tests/test_evedirector_local_first.py tests/test_markdown_to_video.py tests/test_evedirector_local_agent.py tests/test_backlot_agent_review.py tests/test_evedirector_constrained_editor.py tests/test_evedirector_editor_guard.py tests/test_evedirector_unified_workbench.py tests/test_text_encoding_contract.py -q
```

Each layer also has its own acceptance workflow under
[`.github/workflows/`](.github/workflows), including a full zero-key render and FFprobe check.

`tests/test_text_encoding_contract.py` exists because the Linux CI runners are UTF-8 by default and
structurally cannot observe a locale-dependent decode failure. It asserts every text-mode read and
write in production code declares `encoding="utf-8"`, which is what keeps the pipeline working on a
Windows host with a CJK code page.

The inherited upstream suites still apply:

```bash
make test-contracts
make test
```

---

## Upstream OpenMontage

Everything below EveDirector — the twelve pipelines, the tool registry, the provider matrix, the
style system, the platform output profiles, the quality gates and the Backlot board — comes from
OpenMontage. That reference is preserved in full at
[`docs/UPSTREAM_README.md`](docs/UPSTREAM_README.md), along with
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/PROVIDERS.md`](docs/PROVIDERS.md) and
[`AGENT_GUIDE.md`](AGENT_GUIDE.md).

If OpenMontage is useful to you, star and support
[the upstream project](https://github.com/calesthio/OpenMontage) — EveDirector exists because that
foundation was there.

---

## License

[GNU AGPLv3](LICENSE), inherited from OpenMontage.

The AGPL network clause is not incidental here: if you run a modified EveDirector as a hosted
service, your users are entitled to your source. [`docs/WEB_RUNTIME.md`](docs/WEB_RUNTIME.md)
covers what that obliges when deploying the container runtime.
