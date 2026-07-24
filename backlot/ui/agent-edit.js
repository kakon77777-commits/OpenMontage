import { el, fmtDuration, getJSON } from "/ui/lib.js";

const marker = "/agent-edit/";
const bodyPath = location.pathname.startsWith("/p/") ? location.pathname.slice(3) : "";
const markerIndex = bodyPath.indexOf(marker);
const encodedProject = markerIndex >= 0 ? bodyPath.slice(0, markerIndex) : "";
const encodedRun = markerIndex >= 0 ? bodyPath.slice(markerIndex + marker.length) : "";
const projectId = decodeURIComponent(encodedProject);
const runId = decodeURIComponent(encodedRun);
const encodedProjectId = encodeURIComponent(projectId);
const encodedRunId = encodeURIComponent(runId);
const app = document.getElementById("app");
const EDITOR_KEY = "evedirector.reviewer";

let detail = null;
let original = null;
let working = null;
let selectedSceneId = null;
let loading = true;
let errorText = "";
let editorValue = localStorage.getItem(EDITOR_KEY) || "";
let summaryValue = "";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function currentScene() {
  return (working?.scenes || []).find((scene) => scene.id === selectedSceneId) || null;
}

function originalScene(sceneId) {
  return (original?.scenes || []).find((scene) => scene.id === sceneId) || null;
}

function recomputeTimeline() {
  let cursor = 0;
  for (const scene of working?.scenes || []) {
    const duration = Math.max(0, number(scene.duration_seconds));
    scene.cut.in_seconds = Math.round(cursor * 1000) / 1000;
    cursor += duration;
    scene.cut.out_seconds = Math.round(cursor * 1000) / 1000;
  }
}

function timelineSeconds() {
  const scenes = working?.scenes || [];
  return scenes.length ? number(scenes[scenes.length - 1].cut.out_seconds) : 0;
}

function buildOperations() {
  if (!original || !working) return [];
  const operations = [];
  for (const field of detail.editor.contract.project_fields || []) {
    if (!same(original.project[field], working.project[field])) {
      operations.push({ op: "set_project_field", field, value: working.project[field] });
    }
  }

  const originalOrder = original.scenes.map((scene) => scene.id);
  const workingOrder = working.scenes.map((scene) => scene.id);
  if (!same(originalOrder, workingOrder)) {
    operations.push({ op: "reorder_scenes", scene_ids: workingOrder });
  }

  for (const scene of working.scenes) {
    const before = originalScene(scene.id);
    if (!before) continue;
    if (Math.abs(number(before.duration_seconds) - number(scene.duration_seconds)) > 0.0001) {
      operations.push({
        op: "set_scene_duration",
        scene_id: scene.id,
        duration_seconds: number(scene.duration_seconds),
      });
    }
    if (!same(before.narration, scene.narration)) {
      operations.push({
        op: "set_scene_narration",
        scene_id: scene.id,
        value: scene.narration,
      });
    }
    for (const field of detail.editor.contract.cut_fields || []) {
      if (!same(before.cut[field], scene.cut[field])) {
        operations.push({
          op: "set_cut_field",
          scene_id: scene.id,
          field,
          value: scene.cut[field] ?? null,
        });
      }
    }
  }
  return operations;
}

function statusAllowsEdit() {
  return ["awaiting_human", "validated", "applied"].includes(detail?.run?.status);
}

function inputField(label, value, oninput, options = {}) {
  const input = el(options.multiline ? "textarea" : "input", {
    value: value ?? "",
    type: options.type || (options.multiline ? null : "text"),
    min: options.min,
    step: options.step,
    placeholder: options.placeholder,
  });
  input.addEventListener("input", () => {
    oninput(input.value);
    refreshDynamic();
  });
  return el("label", { class: options.class || "" }, el("span", {}, label), input);
}

function renderTopbar() {
  const enabled = Boolean(detail?.actions_enabled);
  return el("header", { class: "topbar" },
    el("div", { class: "brand" },
      el("div", { class: "mark", "aria-hidden": "true" }, "E"),
      el("div", {},
        el("h1", {}, "EveDirector Constrained Editor"),
        el("p", {}, `${projectId} · ${runId}`),
      ),
    ),
    el("div", { class: "spacer" }),
    el("span", { class: `pill ${enabled ? "enabled" : "locked"}` },
      enabled ? "DERIVED RUNS ENABLED" : "STAGING ONLY"),
    el("a", {
      class: "back-link",
      href: `/p/${encodedProjectId}/agent-review`,
    }, "← Review Workbench"),
  );
}

function moveScene(sceneId, delta) {
  const index = working.scenes.findIndex((scene) => scene.id === sceneId);
  const next = index + delta;
  if (index < 0 || next < 0 || next >= working.scenes.length) return;
  const [scene] = working.scenes.splice(index, 1);
  working.scenes.splice(next, 0, scene);
  recomputeTimeline();
  renderAll();
}

function renderSceneList() {
  const scenes = working?.scenes || [];
  return el("aside", { class: "panel scene-list" },
    el("div", { class: "panel-head" },
      el("h2", {}, "Workflow Scenes"),
      el("span", { class: "pill" }, String(scenes.length)),
    ),
    el("div", { class: "panel-body" },
      ...scenes.map((scene, index) => el("article", {
        class: `scene-card${scene.id === selectedSceneId ? " selected" : ""}`,
        "data-scene-id": scene.id,
        onclick: () => {
          selectedSceneId = scene.id;
          renderAll();
        },
      },
        el("div", { class: "scene-order" },
          el("button", {
            type: "button",
            title: "Move scene earlier",
            disabled: index === 0,
            onclick: (event) => {
              event.stopPropagation();
              moveScene(scene.id, -1);
            },
          }, "↑"),
          el("span", {}, String(index + 1).padStart(2, "0")),
          el("button", {
            type: "button",
            title: "Move scene later",
            disabled: index === scenes.length - 1,
            onclick: (event) => {
              event.stopPropagation();
              moveScene(scene.id, 1);
            },
          }, "↓"),
        ),
        el("div", { class: "scene-copy" },
          el("b", { class: "scene-name" }, scene.cut.title || scene.cut.text || scene.cut.terminalTitle || scene.id),
          el("small", { class: "scene-time" }, `${scene.cut.type} · ${fmtDuration(scene.duration_seconds)}`),
          el("code", {}, scene.id),
        ),
      )),
    ),
  );
}

function timelineBlocks() {
  const scenes = working?.scenes || [];
  const total = Math.max(timelineSeconds(), 0.001);
  return scenes.map((scene) => {
    const width = Math.max(4, (number(scene.duration_seconds) / total) * 100);
    return el("button", {
      type: "button",
      class: `timeline-block${scene.id === selectedSceneId ? " selected" : ""}`,
      style: `width:${width}%`,
      title: `${scene.id}: ${scene.cut.in_seconds}s–${scene.cut.out_seconds}s`,
      onclick: () => {
        selectedSceneId = scene.id;
        renderAll();
      },
    },
      el("b", {}, scene.cut.title || scene.cut.text || scene.id),
      el("small", {}, `${number(scene.cut.in_seconds).toFixed(1)}–${number(scene.cut.out_seconds).toFixed(1)}s`),
    );
  });
}

function operationList() {
  const operations = buildOperations();
  if (!operations.length) return [el("div", { class: "empty" }, "No edits are staged.")];
  return [el("ol", { class: "operations" },
    ...operations.map((operation) => el("li", {},
      el("code", {}, operation.op),
      el("span", {}, operation.scene_id || operation.field || `${operation.scene_ids?.length || 0} scenes`),
    )),
  )];
}

function renderProjectGraph() {
  const scenes = working?.scenes || [];
  const total = Math.max(timelineSeconds(), 0.001);
  return el("main", { class: "panel graph-panel" },
    el("section", { class: "hero" },
      el("span", { class: "eyebrow" }, "DERIVED CANDIDATE WORKSPACE"),
      el("h2", { id: "project-title-preview" }, working?.project.title || "Untitled project"),
      el("p", {}, "Edits are staged locally in the browser. Submission creates a new candidate run; it never writes the canonical specification."),
      el("div", { class: "metrics" },
        el("div", {}, el("span", {}, "Scenes"), el("b", {}, scenes.length)),
        el("div", {}, el("span", {}, "Timeline"), el("b", { id: "metric-timeline" }, fmtDuration(total))),
        el("div", {}, el("span", {}, "Operations"), el("b", { id: "metric-operations" }, buildOperations().length)),
        el("div", {}, el("span", {}, "Source run"), el("b", { title: runId }, runId.slice(-18))),
      ),
    ),
    el("section", { class: "project-fields" },
      inputField("Project title", working?.project.title, (value) => {
        working.project.title = value;
      }),
      inputField("Theme", working?.project.theme, (value) => {
        working.project.theme = value;
      }),
    ),
    el("section", { class: "timeline-section" },
      el("div", { class: "section-head" },
        el("h3", {}, "Finite Timeline Projection"),
        el("span", { id: "timeline-total" }, `${fmtDuration(total)} total`),
      ),
      el("div", { class: "timeline", id: "timeline" }, ...timelineBlocks()),
    ),
    el("section", { class: "operation-preview" },
      el("div", { class: "section-head" },
        el("h3", {}, "Candidate Operations"),
        el("span", { id: "operation-total" }, `${buildOperations().length} staged`),
      ),
      el("div", { id: "operation-list" }, ...operationList()),
    ),
  );
}

function visibleCutFields(scene) {
  const allowed = detail?.editor?.contract?.cut_fields || [];
  const preferred = [
    "title", "text", "subtitle", "leftLabel", "leftValue", "rightLabel",
    "rightValue", "callout_type", "terminalTitle", "prompt", "accentColor",
    "backgroundColor", "color",
  ];
  const fields = new Set(Object.keys(scene.cut || {}));
  for (const field of preferred) {
    if (allowed.includes(field)) fields.add(field);
  }
  return [...fields].filter((field) => allowed.includes(field)).sort();
}

function renderInspector() {
  const scene = currentScene();
  if (!scene) return el("aside", { class: "panel inspector empty" }, "Select a scene.");
  const contract = detail.editor.contract;
  return el("aside", { class: "panel inspector" },
    el("div", { class: "panel-head" },
      el("h2", {}, "Scene Inspector"),
      el("span", { class: "pill" }, scene.cut.type),
    ),
    el("div", { class: "panel-body inspector-body" },
      el("section", { class: "immutable" },
        el("span", {}, "IMMUTABLE ID"),
        el("code", {}, scene.id),
        el("span", {}, "IMMUTABLE SOURCE ANCHOR"),
        el("p", {}, scene.source_contains),
      ),
      inputField("Duration seconds", scene.duration_seconds, (value) => {
        scene.duration_seconds = number(value, scene.duration_seconds);
        recomputeTimeline();
      }, {
        type: "number",
        min: contract.min_scene_duration_seconds,
        step: "0.5",
      }),
      inputField("Narration", scene.narration, (value) => {
        scene.narration = value;
      }, { multiline: true, class: "wide" }),
      el("div", { class: "field-group" },
        el("h3", {}, "Allowed Component Fields"),
        ...visibleCutFields(scene).map((field) => inputField(field, scene.cut[field], (value) => {
          scene.cut[field] = value;
        })),
      ),
      el("div", { class: "notice" },
        "Scene IDs, source anchors, cut type, terminal steps, and direct in/out timestamps cannot be edited. Duration changes are converted into a contiguous timeline server-side."),
    ),
  );
}

async function submitDerivedRun() {
  const operations = buildOperations();
  if (!operations.length) {
    errorText = "No constrained edits are staged.";
    renderAll();
    return;
  }
  const confirmation = `EDIT ${runId}`;
  if (!window.confirm(
    `Create a new derived candidate run?\n\n${operations.length} operations\nConfirmation: ${confirmation}\n\nThe canonical specification will not be modified.`,
  )) return;

  loading = true;
  errorText = "";
  renderAll();
  try {
    const response = await fetch(
      `/api/project/${encodedProjectId}/agent-edit/${encodedRunId}/derive`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-EveDirector-Action": "review",
        },
        body: JSON.stringify({
          reviewer: editorValue.trim(),
          summary: summaryValue.trim(),
          operations,
          confirmation,
        }),
      },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `${response.status} derive`);
    location.href = `/p/${encodedProjectId}/agent-review`;
  } catch (error) {
    errorText = error.message || String(error);
    loading = false;
    renderAll();
  }
}

function renderSubmitBar() {
  const editorInput = el("input", { value: editorValue, placeholder: "Editor identity" });
  editorInput.addEventListener("input", () => {
    editorValue = editorInput.value;
    localStorage.setItem(EDITOR_KEY, editorValue);
    refreshDynamic();
  });
  const summaryInput = el("input", { value: summaryValue, placeholder: "Describe the intended edit" });
  summaryInput.addEventListener("input", () => {
    summaryValue = summaryInput.value;
  });
  return el("footer", { class: "submit-bar" },
    detail.actions_enabled ? null : el("div", { class: "lock-message" },
      "Backlot is in staging-only mode. Restart with BACKLOT_ENABLE_AGENT_ACTIONS=1 to create a derived run."),
    el("label", {}, el("span", {}, "Editor"), editorInput),
    el("label", { class: "summary" }, el("span", {}, "Edit summary"), summaryInput),
    el("div", { class: "submit-meta" },
      el("b", { id: "submit-operation-count" }, `${buildOperations().length} operations`),
      el("small", {}, "new run only · validation required · human approval required"),
    ),
    el("button", {
      type: "button",
      class: "derive",
      id: "derive-button",
      onclick: submitDerivedRun,
    }, "CREATE DERIVED CANDIDATE"),
  );
}

function refreshDynamic() {
  if (!detail || !working) return;
  recomputeTimeline();
  const operations = buildOperations();
  const total = timelineSeconds();

  const title = document.getElementById("project-title-preview");
  if (title) title.textContent = working.project.title || "Untitled project";
  for (const id of ["metric-timeline", "timeline-total"]) {
    const node = document.getElementById(id);
    if (node) node.textContent = id === "timeline-total" ? `${fmtDuration(total)} total` : fmtDuration(total);
  }
  for (const id of ["metric-operations", "operation-total"]) {
    const node = document.getElementById(id);
    if (node) node.textContent = id === "operation-total" ? `${operations.length} staged` : String(operations.length);
  }
  const list = document.getElementById("operation-list");
  if (list) list.replaceChildren(...operationList());
  const timeline = document.getElementById("timeline");
  if (timeline) timeline.replaceChildren(...timelineBlocks());
  const submitCount = document.getElementById("submit-operation-count");
  if (submitCount) submitCount.textContent = `${operations.length} operations`;
  const button = document.getElementById("derive-button");
  if (button) {
    button.disabled = !detail.actions_enabled || !statusAllowsEdit()
      || !operations.length || !editorValue.trim();
  }
  for (const scene of working.scenes) {
    const card = document.querySelector(`[data-scene-id="${CSS.escape(scene.id)}"]`);
    const name = card?.querySelector(".scene-name");
    const time = card?.querySelector(".scene-time");
    if (name) name.textContent = scene.cut.title || scene.cut.text || scene.cut.terminalTitle || scene.id;
    if (time) time.textContent = `${scene.cut.type} · ${fmtDuration(scene.duration_seconds)}`;
  }
}

function renderAll() {
  app.innerHTML = "";
  app.append(renderTopbar());
  if (errorText) app.append(el("div", { class: "error" }, errorText));
  if (loading && !detail) {
    app.append(el("div", { class: "loading" }, "Loading constrained Project Graph…"));
    return;
  }
  if (!detail || !working) {
    app.append(el("div", { class: "loading" }, "Editor data is unavailable."));
    return;
  }
  app.append(
    el("div", { class: "workspace" },
      renderSceneList(),
      renderProjectGraph(),
      renderInspector(),
    ),
    renderSubmitBar(),
  );
  refreshDynamic();
}

async function load() {
  loading = true;
  errorText = "";
  renderAll();
  try {
    detail = await getJSON(`/api/project/${encodedProjectId}/agent-edit/${encodedRunId}`);
    original = clone(detail.editor);
    working = clone(detail.editor);
    selectedSceneId = working.scenes[0]?.id || null;
    recomputeTimeline();
  } catch (error) {
    errorText = error.message || String(error);
  } finally {
    loading = false;
    renderAll();
  }
}

load();
