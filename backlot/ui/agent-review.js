import { el, fmtDuration, getJSON, subscribe } from "/ui/lib.js";

const suffix = "/agent-review";
const encodedProject = location.pathname.startsWith("/p/") && location.pathname.endsWith(suffix)
  ? location.pathname.slice(3, -suffix.length)
  : "";
const projectId = decodeURIComponent(encodedProject);
const encodedProjectId = encodeURIComponent(projectId);
const app = document.getElementById("app");
const REVIEWER_KEY = "evedirector.reviewer";

let indexState = null;
let detailState = null;
let selectedRun = null;
let loading = true;
let errorText = "";

function textValue(value) {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function statusClass(status) {
  return `status ${String(status || "unknown").replaceAll(" ", "_")}`;
}

function metric(label, value) {
  return el("div", { class: "metric" }, el("span", {}, label), el("b", {}, value ?? "—"));
}

async function loadIndex({ keepSelection = true } = {}) {
  indexState = await getJSON(`/api/project/${encodedProjectId}/agent-review`);
  const ids = new Set((indexState.runs || []).map((run) => run.run_id));
  if (!keepSelection || !selectedRun || !ids.has(selectedRun)) {
    selectedRun = (indexState.runs || [])[0]?.run_id || null;
  }
  if (selectedRun) {
    detailState = await getJSON(`/api/project/${encodedProjectId}/agent-review/${encodeURIComponent(selectedRun)}`);
  } else {
    detailState = null;
  }
}

async function refresh(options) {
  loading = true;
  errorText = "";
  render();
  try {
    await loadIndex(options);
  } catch (error) {
    errorText = error.message || String(error);
  } finally {
    loading = false;
    render();
  }
}

async function chooseRun(runId) {
  selectedRun = runId;
  loading = true;
  errorText = "";
  render();
  try {
    detailState = await getJSON(`/api/project/${encodedProjectId}/agent-review/${encodeURIComponent(runId)}`);
  } catch (error) {
    errorText = error.message || String(error);
  } finally {
    loading = false;
    render();
  }
}

function renderTopbar() {
  const enabled = Boolean(indexState?.actions_enabled);
  return el("header", { class: "topbar" },
    el("div", { class: "brand" },
      el("div", { class: "brand-mark", "aria-hidden": "true" }, "E"),
      el("div", {},
        el("h1", {}, "EveDirector Review"),
        el("p", {}, projectId || "Unknown project"),
      ),
    ),
    el("div", { class: "spacer" }),
    el("span", { class: `pill ${enabled ? "enabled" : "locked"}` },
      enabled ? "ACTIONS ENABLED" : "READ-ONLY"),
    el("a", { class: "back-link", href: `/p/${encodedProjectId}` }, "← Backlot Board"),
  );
}

function renderRuns() {
  const runs = indexState?.runs || [];
  return el("aside", { class: "panel" },
    el("div", { class: "panel-head" },
      el("h2", {}, "Proposal Runs"),
      el("span", { class: "pill" }, String(runs.length))),
    el("div", { class: "panel-body run-list" },
      runs.length ? runs.map((run) => el("button", {
        type: "button",
        class: `run-card${run.run_id === selectedRun ? " active" : ""}`,
        onclick: () => chooseRun(run.run_id),
      },
        el("span", { class: statusClass(run.status) }, run.status),
        el("b", { title: run.run_id }, run.run_id),
        el("small", {}, `${run.semantic_change_count ?? 0} changes · ${run.source_anchor_count ?? 0} anchors`),
        el("small", {}, run.model ? `${run.provider || "model"} · ${run.model}` : (run.provider || "unknown provider")),
      )) : el("div", { class: "empty" }, "No local-agent proposal runs were found."),
    ),
  );
}

function renderGraph(detail) {
  const graph = detail.graph || { nodes: [] };
  const nodes = new Map((graph.nodes || []).map((node) => [node.id, node]));
  const order = ["source", "canonical", "candidate", "validation", "gate"];
  const main = order.map((id) => nodes.get(id)).filter(Boolean);
  const scenes = (detail.candidate?.scenes || []);
  return el("div", {},
    el("div", { class: "graph" },
      el("div", { class: "graph-row" }, main.map((node) => el("div", { class: "graph-node" },
        el("span", { class: "kind" }, node.type),
        el("strong", {}, node.label),
        el("em", {}, node.status || "unknown"),
      ))),
    ),
    el("div", { class: "scene-grid" }, scenes.map((scene) => el("div", {
      class: `scene-node${scene.changed ? " changed" : ""}`,
      title: scene.source_contains || "",
    },
      el("b", {}, scene.title || scene.id),
      el("small", {}, `${fmtDuration(scene.in_seconds)} – ${fmtDuration(scene.out_seconds)} · ${scene.type || "scene"}`),
      el("small", {}, scene.changed ? "SEMANTIC CHANGE" : "SOURCE GROUNDED"),
    ))),
  );
}

function renderChanges(changes) {
  if (!changes.length) return el("div", { class: "empty" }, "No semantic changes.");
  return changes.map((change) => el("article", { class: "change" },
    el("code", {}, change.path),
    el("div", { class: "change-grid" },
      el("pre", {}, `BEFORE\n${textValue(change.before)}`),
      el("pre", {}, `AFTER\n${textValue(change.after)}`),
    ),
  ));
}

function renderAnchors(anchors) {
  if (!anchors.length) return el("div", { class: "empty" }, "No source anchors were reported.");
  return anchors.map((anchor) => el("article", { class: "anchor" },
    el("b", {}, `${anchor.scene_id} · lines ${anchor.line_start}–${anchor.line_end}`),
    el("p", {}, anchor.excerpt || anchor.query || ""),
  ));
}

function renderCenter(detail) {
  const run = detail.run || {};
  return el("main", { class: "panel" },
    el("section", { class: "hero" },
      el("span", { class: statusClass(run.status) }, run.status),
      el("h2", {}, detail.candidate?.title || "Candidate specification"),
      el("p", {}, run.instruction || "Local-agent proposal awaiting review."),
      el("div", { class: "metrics" },
        metric("Semantic changes", run.semantic_change_count ?? detail.semanticChanges?.length ?? 0),
        metric("Source anchors", run.source_anchor_count ?? detail.source?.anchors?.length ?? 0),
        metric("Scenes", detail.candidate?.scene_count),
        metric("Timeline", fmtDuration(detail.candidate?.timeline_seconds)),
      ),
    ),
    renderGraph(detail),
    el("section", { class: "section" },
      el("h3", {}, "Semantic Diff"),
      ...renderChanges(detail.semanticChanges || []),
    ),
  );
}

async function postAction(action, runId, reviewer, reason = "") {
  const verb = action.toUpperCase();
  const confirmation = `${verb} ${runId}`;
  const label = action === "apply"
    ? "Apply this candidate to the canonical video specification?"
    : action === "reject"
      ? "Reject this candidate without modifying the canonical specification?"
      : "Revalidate this candidate against the current source and policy?";
  if (!window.confirm(`${label}\n\nConfirmation: ${confirmation}`)) return;

  errorText = "";
  loading = true;
  render();
  try {
    const response = await fetch(
      `/api/project/${encodedProjectId}/agent-review/${encodeURIComponent(runId)}/${action}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-EveDirector-Action": "review",
        },
        body: JSON.stringify({ reviewer, reason, confirmation }),
      },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${action}`);
    detailState = payload;
    await loadIndex({ keepSelection: true });
  } catch (error) {
    errorText = error.message || String(error);
  } finally {
    loading = false;
    render();
  }
}

function renderActions(detail) {
  const enabled = Boolean(detail.actions_enabled);
  const status = detail.run?.status;
  const reviewable = ["awaiting_human", "validated"].includes(status);
  const reviewer = localStorage.getItem(REVIEWER_KEY) || "";
  const reviewerInput = el("input", { value: reviewer, placeholder: "Reviewer name" });
  reviewerInput.addEventListener("input", () => localStorage.setItem(REVIEWER_KEY, reviewerInput.value));
  const reasonInput = el("textarea", { placeholder: "Required when rejecting a candidate" });
  const actionButtons = el("div", { class: "action-row" },
    el("button", {
      type: "button", class: "validate", disabled: !enabled || !reviewable,
      onclick: () => postAction("validate", detail.run.run_id, reviewerInput.value.trim()),
    }, "VALIDATE"),
    el("button", {
      type: "button", class: "apply", disabled: !enabled || !reviewable,
      onclick: () => postAction("apply", detail.run.run_id, reviewerInput.value.trim()),
    }, "APPLY"),
    el("button", {
      type: "button", class: "reject", disabled: !enabled || ["applied", "rejected"].includes(status),
      onclick: () => postAction("reject", detail.run.run_id, reviewerInput.value.trim(), reasonInput.value.trim()),
    }, "REJECT"),
  );
  return el("div", { class: "actions" },
    enabled ? null : el("div", { class: "notice" },
      "Backlot is read-only. Restart it with BACKLOT_ENABLE_AGENT_ACTIONS=1 to enable guarded review actions."),
    el("label", {}, "Reviewer", reviewerInput),
    el("label", {}, "Rejection reason", reasonInput),
    actionButtons,
    el("div", { class: "notice" },
      "Apply and reject still execute the L3 contract. A stale baseline, invalid source anchor, or unsupported field is rejected server-side."),
  );
}

function renderRight(detail) {
  return el("aside", { class: "panel right-panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "Evidence & Authority")),
    el("section", { class: "section" },
      el("h3", {}, "Source Anchors"),
      ...renderAnchors(detail.source?.anchors || []),
    ),
    el("section", { class: "section" },
      el("h3", {}, "Human Gate"),
      renderActions(detail),
    ),
  );
}

function render() {
  app.innerHTML = "";
  app.append(renderTopbar());
  if (errorText) app.append(el("div", { class: "error" }, errorText));
  if (loading && !indexState) {
    app.append(el("div", { class: "panel empty", style: "margin-top:16px" }, "Loading proposal graph…"));
    return;
  }
  const center = detailState
    ? renderCenter(detailState)
    : el("main", { class: "panel empty" }, "Select or create a local-agent proposal run.");
  const right = detailState
    ? renderRight(detailState)
    : el("aside", { class: "panel right-panel empty" }, "No review detail available.");
  app.append(el("div", { class: "workspace" }, renderRuns(), center, right));
}

refresh({ keepSelection: false });
subscribe(`/api/project/${encodedProjectId}/events`, () => refresh({ keepSelection: true }));
