# EveDirector L5 — Constrained Project Graph Editor

L5 turns the L4 review projection into a finite, allow-listed editing workspace.
It does **not** turn Backlot into a general YAML editor and does not grant the
browser direct write access to the canonical video specification.

## Authority model

```text
existing model or human candidate
  -> browser stages finite operations
  -> explicit EDIT <run-id> confirmation
  -> new derived candidate run
  -> source and timeline validation
  -> L4 semantic diff and evidence review
  -> explicit Validate / Apply / Reject
```

The source run, its candidate, and the canonical specification remain unchanged
when the editor submits work. The server creates a new directory under:

```text
projects/<project-id>/agent_runs/<derived-run-id>/
```

The derived run contains:

```text
edit_request.json
candidate.video_spec.yaml
candidate.diff
candidate.unified.diff
audit.json
```

It intentionally does not contain a model `request.json` or `response.txt`.

## Editor page

Open a run in the L4 Review Workbench and use the floating:

```text
EDIT AS DERIVED CANDIDATE
```

Or open directly:

```text
http://127.0.0.1:4750/p/<project-id>/agent-edit/<run-id>
```

The page provides three finite views:

1. Workflow scene order with explicit up/down controls.
2. A contiguous timeline projection based on scene duration.
3. A scene inspector for narration and allow-listed component fields.

This is not an infinite canvas. It does not permit arbitrary nodes, arbitrary
edges, arbitrary JSON paths, or direct file editing.

## Allowed operations

```json
{"op":"set_project_field","field":"title","value":"New title"}
{"op":"reorder_scenes","scene_ids":["scene-b","scene-a"]}
{"op":"set_scene_duration","scene_id":"scene-a","duration_seconds":8}
{"op":"set_scene_narration","scene_id":"scene-a","value":"Revised narration"}
{"op":"set_cut_field","scene_id":"scene-a","field":"subtitle","value":"Revised"}
```

The example policy allows top-level `title` and `theme` editing. Component
fields are derived from `allowed_cut_fields`, minus the explicit blocked list.

## Immutable structure

L5 does not allow browser operations to change:

- scene IDs;
- source anchor queries (`source_contains`);
- cut type;
- direct `in_seconds` or `out_seconds` values;
- terminal `steps` structures;
- protected L3 project identity fields;
- scene count;
- overlays.

A scene reorder must contain every existing scene ID exactly once. A missing,
extra, renamed, or duplicated ID is rejected.

## Timeline rule

The browser edits duration, not raw timestamps. The server rebuilds the entire
scene timeline from zero in current scene order:

```text
scene[0].in = 0
scene[0].out = duration[0]
scene[n].in = scene[n-1].out
scene[n].out = scene[n].in + duration[n]
```

The existing L2/L3 validator then checks continuity and maximum duration again.
This prevents browser-created gaps and overlaps.

## Source rule

Source anchors cannot be edited in L5. Every derived candidate is nevertheless
revalidated against the current Markdown source. The audit bundle receives a
fresh grounding list and source SHA-256.

## Action gate

The editor can always stage changes in the browser. Creating a derived run is
disabled unless Backlot starts with:

```powershell
$env:BACKLOT_ENABLE_AGENT_ACTIONS = "1"
python -m backlot serve --port 4750
```

The request must additionally include:

```http
X-EveDirector-Action: review
Content-Type: application/json
```

And the body must provide:

```json
{
  "reviewer": "Neo.K",
  "summary": "Refine pacing and titles.",
  "confirmation": "EDIT <run-id>",
  "operations": []
}
```

The editor identity is stored in `edit_request.json` and `audit.json`.

## Stale-run protection

For an awaiting or validated source run, its original canonical baseline hash
must still match the canonical specification. For an applied source run, the
current canonical hash must match the recorded applied hash.

If another candidate has changed the canonical specification, L5 rejects the
edit and requires a current source run. It never silently rebases old edits.

## Derived run audit

`audit.json` records:

- `provider: human-editor`;
- `model: constrained-project-graph`;
- parent run ID;
- editor identity;
- operation count and operation digest;
- parent candidate hash;
- new candidate hash;
- canonical baseline hash;
- source hash and grounding results;
- semantic change count;
- changed scene IDs.

The new run enters `awaiting_human`. It must use the existing L4 Validate,
Apply, or Reject gate. L5 submission itself cannot approve or apply a result.

## Policy extension

```yaml
editor:
  allowed_project_fields:
    - title
    - theme
  blocked_cut_fields:
    - type
    - in_seconds
    - out_seconds
    - steps
  min_scene_duration_seconds: 0.5
  max_operations_per_run: 50
```

When the section is absent, conservative defaults are used.

## Scope boundary

L5 does not include:

- adding or deleting scenes;
- changing evidence anchors;
- changing component types;
- editing terminal animation structures;
- overlay editing;
- free node or edge creation;
- drag-and-drop infinite canvas authoring;
- direct canonical writes;
- automatic approval;
- multi-user remote authorization.

Those capabilities require separate contracts rather than expansion of the
current allow-list.
