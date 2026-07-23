# EveDirector L2 — Source-Grounded Markdown to Video

This document defines Phase L2 of the EVEMISSLAB OpenMontage fork.

L1 established a zero-key local runtime floor. L2 moves from a generic demo to
one real EVEMISSLAB Markdown source and turns it into an auditable OpenMontage
project that can be rendered by the existing Remotion composer.

## Selected source

The first source is:

```text
DRC Search：生成式 AI 時代的非線性搜尋、共振式爬蟲與認知地圖生成方法
```

The source was selected because its central structure is already visual:

```text
Divergence → Resonance → Compression → Divergence'
```

It can be represented with motion graphics, comparison cards, callouts and a
state-machine terminal scene without requiring actors, stock footage, generated
images or a paid video provider.

The repository contains a source excerpt at:

```text
examples/drc-search-video/source/drc_search_whitepaper_v0_1_excerpt.md
```

The excerpt preserves the original core propositions used in the video and is
explicitly marked as a production excerpt rather than a replacement for the
full paper.

## L2 goal

L2 proves this path:

```text
Real Markdown source
    ↓
Source anchors
    ↓
Narration script
    ↓
Scene plan
    ↓
Edit decisions
    ↓
Remotion props
    ↓
OpenMontage project
    ↓
H.264 MP4
```

L2 does not use an LLM, image-generation API, video-generation API or cloud TTS.
The creative adaptation is stored in a reviewable YAML specification.

## Why the conversion is specification-driven

A fully automatic Markdown summarizer would introduce an untested intelligence
layer before L3. L2 therefore uses two separate inputs:

1. a real Markdown source;
2. a human-reviewable `video_spec.yaml` describing which source claims become
   scenes and how those scenes are rendered.

This keeps the first conversion deterministic. L3 can later replace or assist
the specification authoring step with a local Agent while retaining the same
contracts.

## Grounding contract

Every scene in `video_spec.yaml` must declare:

```yaml
source_contains: "a phrase that exists in the Markdown source"
```

Before any artifacts are written, the converter:

1. normalizes Markdown formatting;
2. finds the phrase in the source;
3. records its one-based line position;
4. stores a short excerpt;
5. links that record to the scene ID;
6. fails the entire build when any scene cannot be grounded.

The resulting file is:

```text
projects/evedirector-drc-search/artifacts/grounding_manifest.json
```

It contains:

- source SHA-256;
- scene ID;
- matching query;
- source line range;
- source excerpt.

The source itself is copied into the generated project so the project remains
reviewable even when the original example directory later changes.

## Source integrity

The converter writes:

```text
artifacts/source_manifest.json
```

The manifest records:

- title;
- author;
- original repository path;
- project-local copy path;
- SHA-256;
- source line count.

A later pipeline can compare hashes and determine whether the source changed
after the video plan was created.

## DRC Search video structure

The reference implementation is a 75-second English-first explainer with eight
source-grounded scenes:

| Time | Scene | Purpose |
|---|---|---|
| 0–6s | DRC Search title | Establish the topic |
| 6–15s | Traditional Search vs DRC | State the problem and contrast |
| 15–25s | Divergence | Query as a semantic seed |
| 25–35s | Resonance | Intent, trust, context and structural value |
| 35–45s | Compression | Maps, comparisons and actions instead of a flat summary |
| 45–57s | Recursive state machine | Show `D → R → C → D′` |
| 57–67s | Source anchors | Preserve evidence and traceability |
| 67–75s | Conclusion | Search becomes an information field |

The current on-screen language is English because it is a stable first test for
the existing Space Grotesk/Remotion composition. The source and grounding
records remain Chinese. Multilingual typography and narration belong to later
local production refinement, not to this contract test.

## Files

```text
examples/drc-search-video/
├── source/
│   └── drc_search_whitepaper_v0_1_excerpt.md
└── video_spec.yaml

scripts/
├── markdown_to_video.py
└── evedirector-l2.ps1

tests/
└── test_markdown_to_video.py
```

Generated project:

```text
projects/evedirector-drc-search/
├── project.json
├── source/
│   └── drc_search_whitepaper_v0_1_excerpt.md
├── artifacts/
│   ├── source_manifest.json
│   ├── grounding_manifest.json
│   ├── script.json
│   ├── scene_plan.json
│   ├── edit_decisions.json
│   ├── remotion_props.json
│   └── render_report.json          # after render
├── checkpoint_script.json
├── checkpoint_scene_plan.json
├── checkpoint_edit.json
├── checkpoint_compose.json
└── renders/
    └── drc-search.mp4              # after render
```

## Commands

### Cross-platform Python

Validate every source anchor and timeline without writing a project:

```bash
python scripts/markdown_to_video.py validate
```

Build OpenMontage artifacts and checkpoints:

```bash
python scripts/markdown_to_video.py --force build
```

Build and render the MP4:

```bash
python scripts/markdown_to_video.py render
```

Open the generated project in Backlot:

```bash
python scripts/markdown_to_video.py board
```

Build, render and open Backlot:

```bash
python scripts/markdown_to_video.py --force all
```

Machine-readable output:

```bash
python scripts/markdown_to_video.py --json validate
python scripts/markdown_to_video.py --json build
```

### Windows PowerShell

```powershell
.\scripts\evedirector-l2.ps1 validate
.\scripts\evedirector-l2.ps1 build -Force
.\scripts\evedirector-l2.ps1 render
.\scripts\evedirector-l2.ps1 board
.\scripts\evedirector-l2.ps1 all -Force
```

### Make

```bash
make l2-validate
make l2-build
make l2-render
make l2-board
make l2-all
```

## What `build` proves

A successful build proves that:

- the Markdown source exists;
- every planned scene resolves to the source;
- the timeline is contiguous;
- the source hash and line anchors are recorded;
- the script artifact is schema-valid;
- the scene plan artifact is schema-valid;
- the edit decisions artifact is schema-valid;
- OpenMontage checkpoints can represent the project;
- the existing Backlot can observe the production state.

It does not prove that Chromium, Remotion or FFmpeg can render on a particular
machine.

## What `render` proves

A successful render additionally proves that:

- Node/npm/npx are available;
- Remotion dependencies can be installed;
- the existing `Explainer` composition accepts the generated props;
- the selected components render together;
- an actual non-empty H.264 MP4 is created;
- a schema-valid render report and completed compose checkpoint can be written.

The expected output is:

```text
projects/evedirector-drc-search/renders/drc-search.mp4
```

## Tests

Focused contract tests cover:

1. the default video is exactly 75 seconds;
2. the timeline has no gaps or overlaps;
3. all eight scenes resolve to source anchors;
4. a fabricated claim fails closed;
5. generated artifacts and checkpoints exist;
6. grounding, script and Remotion cut counts remain aligned.

Run:

```bash
python -m pytest tests/test_markdown_to_video.py -q
```

The GitHub Actions workflow also compiles the converter, validates the source
anchors and runs the focused tests. It deliberately does not render Chromium in
CI during this phase; the real MP4 render remains a local runtime acceptance
check.

## Editing the first video

Change wording or visuals in:

```text
examples/drc-search-video/video_spec.yaml
```

Do not edit generated JSON under `projects/` as the source of truth. Generated
project files are reproducible and are ignored by Git.

When adding a scene:

1. choose a source phrase;
2. add `source_contains`;
3. add narration;
4. add a supported Explainer cut;
5. keep `in_seconds` contiguous;
6. run `validate`;
7. inspect the grounding manifest;
8. render locally.

## Current limitations

L2 intentionally does not provide:

- automatic AI summarization;
- automatic scene writing;
- local model inference;
- generated narration audio;
- Chinese font packaging;
- generated images or video;
- source citation overlays inside the final frame;
- editable timeline UI;
- infinite canvas;
- Project Graph.

Those are not defects hidden behind the milestone. They define the boundary
between L2 and later phases.

## L2 acceptance criteria

The implementation portion of L2 is complete when:

1. a real EVEMISSLAB Markdown source is checked in as the selected production
   excerpt;
2. the video specification contains eight grounded scenes;
3. `validate` succeeds;
4. focused tests pass;
5. `build` produces all artifacts and checkpoints;
6. Backlot can open the project;
7. the local Remotion runtime creates `drc-search.mp4`;
8. the output can be inspected by FFmpeg;
9. no API key is used.

Items 1–5 are repository contract checks. Items 6–8 are local runtime checks.
The implementation must not claim a successful MP4 render until the file exists
and is inspected on an actual runtime.

## Boundary to L3

L3 may introduce a local Agent or local language model to propose:

- source excerpts;
- narration;
- scene boundaries;
- component selection;
- source anchor candidates.

It must emit or update the same reviewable video specification and pass the same
grounding validator. Local AI assistance must not remove the source contract
established in L2.
