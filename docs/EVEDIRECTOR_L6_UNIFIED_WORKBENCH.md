# EveDirector L6 — Unified Infinite Canvas, Workflow and Timeline

L6 is the final implementation phase in the current local-first handoff series. It gives one source-grounded Project Graph three synchronized visual projections:

```text
Infinite Canvas
+ Workflow
+ Timeline
+ Inspector
```

All views are driven by the same scene identity model. They do not create parallel project states.

## Route

```text
/p/<project-id>/director/<run-id>
GET /api/project/<project-id>/director/<run-id>
```

The L6 router is read-only. Semantic submissions continue to use L5:

```text
POST /api/project/<project-id>/agent-edit/<run-id>/derive
```

## Shared model

The API verifies that scene identities are identical across:

- `model.scenes`
- `views.canvas`
- `views.workflow`
- `views.timeline`

A divergence raises an error instead of presenting inconsistent views. Every scene remains linked to its L4/L3 source anchor.

## Infinite canvas

The canvas supports pan, zoom, fit-to-content, reset, local node dragging, evidence edges, and source/canonical/candidate/validation/human-gate nodes.

Canvas positions are stored only in browser local storage:

```text
evedirector.canvas.<project-id>.<run-id>
```

Moving a node creates no editor Operation and modifies no YAML, Run, Audit, or canonical specification. Arbitrary node and edge creation remain disabled.

## Workflow and timeline

The workflow lane and timeline use the same `working.scenes` array as the canvas.

When the L5 timeline contract is editable:

- workflow controls can move scenes earlier or later;
- timeline duration inputs stage `set_scene_duration` operations;
- the browser recomputes a contiguous preview timeline;
- the server repeats L5/L3 validation before creating a Derived Run.

When absolute-time overlays are present, both structural controls are locked by the L5 Overlay Timeline Guard, and forged requests are rejected server-side.

## Inspector

The inspector exposes only the L5 policy allow-list:

- project title and theme;
- scene narration;
- allow-listed string cut fields;
- source line evidence.

It does not expose raw model responses, prompt messages, tokens, environment values, direct YAML editing, source-anchor editing, cut-type editing, terminal-step editing, or overlay editing.

## Semantic Operations

The browser compares the shared working model with the original and emits only L5 operations:

```json
{"op":"set_project_field","field":"title","value":"New title"}
{"op":"reorder_scenes","scene_ids":["scene-b","scene-a"]}
{"op":"set_scene_duration","scene_id":"scene-a","duration_seconds":8}
{"op":"set_scene_narration","scene_id":"scene-a","value":"Revised narration"}
{"op":"set_cut_field","scene_id":"scene-a","field":"subtitle","value":"Revised"}
```

Canvas layout changes are excluded.

## Authority flow

```text
browser-local canvas layout
  -> no semantic authority

shared semantic model
  -> L5 allow-listed Operations
  -> BACKLOT_ENABLE_AGENT_ACTIONS=1
  -> X-EveDirector-Action: review
  -> editor identity
  -> EDIT <run-id>
  -> new Derived Run
  -> L3 source and policy validation
  -> L4 semantic Diff and evidence review
  -> explicit Validate / Apply / Reject
```

The L6 page cannot apply a candidate directly.

## Local launch

```powershell
$env:BACKLOT_ENABLE_AGENT_ACTIONS = "1"
python -m backlot serve --port 4750
```

Open the L4 Review Workbench, select a Run, and choose:

```text
OPEN UNIFIED WORKBENCH ↗
```

## Acceptance criteria

L6 closes when:

1. canvas, workflow, timeline, and model expose identical scene IDs and order;
2. scene selection synchronizes between views;
3. canvas layout persists locally and produces no semantic Operation;
4. workflow ordering and timeline duration emit only L5 Operations;
5. the overlay timeline lock remains effective;
6. source anchors remain attached to scene nodes;
7. the L6 router has no write endpoint;
8. semantic submission creates a new Derived Run through L5;
9. canonical spec and parent Run remain unchanged during derive;
10. L2–L5 regression workflows and zero-key rendering remain valid.

## Scope boundary

L6 does not add arbitrary graph authoring, scene creation/deletion, overlay-to-scene anchors, overlay editing, audio waveforms, keyframes, multi-user collaboration, cloud authorization, direct canonical writes, or automatic approval. These are post-handoff product extensions, not part of the L0–L6 local-first foundation.
