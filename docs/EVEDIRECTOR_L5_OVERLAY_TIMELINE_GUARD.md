# EveDirector L5 — Overlay Timeline Guard

L5 treats scene order and scene duration as structural timeline operations.
They are safe only when the candidate has no absolute-time overlays.

## Why the guard exists

The current video specification stores overlays with absolute timestamps:

```yaml
overlays:
  - type: section_title
    in_seconds: 14.8
    out_seconds: 18.8
    text: Divergence
```

These overlays do not yet carry a `scene_id` or another semantic anchor. If L5
reordered scenes or changed scene duration while retaining those absolute
seconds, the resulting candidate could remain schema-valid but display an
overlay over the wrong claim or scene.

Schema validity is not sufficient evidence of semantic alignment.

## L5 rule

When `overlays` is a non-empty list, the public constrained-editor contract
returns:

```json
{
  "timeline_editable": false,
  "timeline_lock_reason": "Structural timeline editing is locked because this candidate contains absolute-time overlays without scene anchors."
}
```

The browser disables:

- scene up/down controls;
- scene-duration input.

The server independently rejects:

```text
reorder_scenes
set_scene_duration
```

Textual and visual-string operations remain available:

- project title and theme;
- narration;
- allow-listed string component fields.

The server also restricts `set_cut_field` values to strings. Null, numeric,
boolean, array, and object values cannot be inserted through the L5 public API.

## Future unlock condition

Structural timeline editing may be reopened after a separate contract defines
how overlays bind to scenes, claims, or timeline anchors. A possible future
shape is:

```yaml
- id: overlay-divergence
  scene_id: divergence
  anchor: scene_start
  offset_seconds: -0.2
  duration_seconds: 4
```

That model must specify:

- behavior when scenes are reordered;
- behavior when scene duration shrinks below the overlay range;
- collision and overlap rules;
- source/evidence inheritance;
- migration from existing absolute timestamps;
- rendering compatibility.

Until then, locking structural timeline edits is safer than silently preserving
incorrect overlay timing.
