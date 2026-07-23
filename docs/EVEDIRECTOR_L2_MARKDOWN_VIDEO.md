# EveDirector L2 — Source-Grounded Markdown to Video

Phase L2 moves from the generic zero-key demo in L1 to one real EVEMISSLAB
Markdown source and a reproducible OpenMontage video project.

## Selected source

```text
DRC Search：生成式 AI 時代的非線性搜尋、共振式爬蟲與認知地圖生成方法
```

It was selected because its core structure is already visual:

```text
Divergence → Resonance → Compression → Divergence'
```

The repository keeps the production excerpt at:

```text
examples/drc-search-video/source/drc_search_whitepaper_v0_1_excerpt.md
```

The excerpt preserves the propositions used by the video and is explicitly
marked as a production excerpt, not a replacement for the complete paper.

## L2 path

```text
Real Markdown
    ↓
Source anchors
    ↓
Narration script
    ↓
Scene plan
    ↓
Zero-external-asset manifest
    ↓
Edit decisions
    ↓
Remotion props
    ↓
H.264 MP4
    ↓
FFprobe verification
```

L2 deliberately uses no LLM, image API, video API or cloud TTS. The creative
adaptation is a human-reviewable YAML specification. L3 may later let a local
Agent propose that specification while retaining the same contracts.

## Grounding contract

Every scene in `video_spec.yaml` declares a source phrase:

```yaml
source_contains: "a phrase that exists in the Markdown source"
```

Before writing a project, the converter:

1. normalizes Markdown formatting;
2. finds the phrase in the source;
3. records the real one-based source line range;
4. stores a short excerpt;
5. links the anchor to the scene and script section;
6. fails closed when any scene is not grounded.

The result is:

```text
projects/evedirector-drc-search/artifacts/grounding_manifest.json
```

Each script section also carries a `source_ref` back to its grounding record.
The source is copied into the generated project, and a SHA-256 is stored in
`source_manifest.json`.

## Reference video

The first specification is a 75-second English-first explainer with eight
source-grounded scenes:

| Time | Scene | Purpose |
|---|---|---|
| 0–6s | Title | Introduce DRC Search |
| 6–15s | Comparison | Ranked links versus cognitive maps |
| 15–25s | Divergence | A query becomes a semantic seed |
| 25–35s | Resonance | Intent, context, trust and structural value |
| 35–45s | Compression | Maps, matrices and next actions |
| 45–57s | State machine | `D → R → C → D′` |
| 57–67s | Source anchors | Compression must preserve evidence |
| 67–75s | Conclusion | Search becomes an information field |

English on-screen text is used to test the existing Remotion typography without
adding a font-packaging task to L2. The source and grounding records remain
Chinese.

## Repository files

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
│   ├── asset_manifest.json
│   ├── edit_decisions.json
│   ├── remotion_props.json
│   └── render_report.json          # after render
├── checkpoint_script.json
├── checkpoint_scene_plan.json
├── checkpoint_assets.json
├── checkpoint_edit.json
├── checkpoint_compose.json
└── renders/
    └── drc-search.mp4              # after render
```

`asset_manifest.json` is intentionally valid but empty. The video uses checked-in
Remotion components and therefore has no external media assets and zero provider
cost.

## Commands

### Python

```bash
python scripts/markdown_to_video.py validate
python scripts/markdown_to_video.py --force build
python scripts/markdown_to_video.py render
python scripts/markdown_to_video.py board
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

## What `validate` proves

- all eight scene IDs are unique;
- all eight source phrases exist;
- source line ranges are recoverable;
- the 75-second timeline is contiguous;
- no generated project is required.

## What `build` proves

- the source is copied and hashed;
- grounding, script, scene plan, asset manifest, edit decisions and Remotion
  props are generated;
- canonical artifacts pass OpenMontage checkpoint validation;
- standard script, scene-plan, assets, edit and compose checkpoints are written;
- Backlot has a normal project directory to observe.

A build does not prove that Chromium, Remotion or FFmpeg can run on a particular
machine.

## What `render` proves

A render only succeeds when:

- Node/npm/npx are available;
- the Remotion dependencies are present or can be installed;
- `Explainer` accepts the generated props;
- a non-empty H.264 MP4 is created;
- FFprobe finds a readable video stream and positive duration;
- the verified codec, resolution, frame rate, duration and file size are written
  into a schema-valid `render_report.json`;
- the compose checkpoint advances from `in_progress` to `completed`.

Expected output:

```text
projects/evedirector-drc-search/renders/drc-search.mp4
```

## Tests

```bash
python -m pytest tests/test_markdown_to_video.py -q
```

The focused tests cover:

1. a contiguous 75-second timeline;
2. all eight source anchors;
3. fail-closed behavior for invented claims;
4. rejection of timeline gaps;
5. rejection of duplicate scene IDs;
6. generation of all artifacts and checkpoints;
7. alignment of grounding, script and Remotion scene counts;
8. the explicit zero-external-asset contract.

GitHub Actions compiles the converter, runs `validate`, and runs these tests. It
does not launch a Chromium render in CI during L2; MP4 and FFprobe acceptance is
a local runtime check.

## Editing the video

The editable source of truth is:

```text
examples/drc-search-video/video_spec.yaml
```

Do not manually maintain generated JSON under `projects/`.

For every new scene:

1. select a real source phrase;
2. declare `source_contains`;
3. write narration;
4. select a supported Explainer component;
5. preserve a contiguous timeline;
6. run `validate`;
7. inspect `grounding_manifest.json`;
8. render and inspect locally.

## L2 boundaries

L2 does not include:

- automatic AI summarization or scene writing;
- local model inference;
- narration audio;
- generated images or generated motion video;
- Chinese font packaging;
- source citation overlays inside frames;
- Project Graph;
- editable workflow, infinite canvas or timeline UI.

These are later phases, not hidden claims of the current milestone.

## Acceptance criteria

Repository implementation:

1. a real EVEMISSLAB Markdown excerpt exists;
2. eight scenes are grounded to it;
3. `validate` succeeds;
4. focused tests pass;
5. `build` produces all standard artifacts and checkpoints;
6. no API key is read or required.

Local runtime acceptance:

7. Backlot opens the project;
8. Remotion creates `drc-search.mp4`;
9. FFprobe verifies its video stream and duration.

The project must not claim a successful render until items 7–9 have been run on
an actual local runtime.

## Boundary to L3

L3 may introduce a local Agent or local language model to propose excerpts,
narration, scene boundaries, component choices and anchor candidates. It must
still emit the same reviewable specification and pass this L2 grounding
validator. Local AI assistance must not remove source traceability.
