const marker = "/agent-edit/";
const bodyPath = location.pathname.startsWith("/p/") ? location.pathname.slice(3) : "";
const markerIndex = bodyPath.indexOf(marker);
const encodedProject = markerIndex >= 0 ? bodyPath.slice(0, markerIndex) : "";
const encodedRun = markerIndex >= 0 ? bodyPath.slice(markerIndex + marker.length) : "";

let contract = null;
let applying = false;

function durationInput() {
  return [...document.querySelectorAll("label")]
    .find((label) => label.querySelector("span")?.textContent?.trim() === "Duration seconds")
    ?.querySelector("input");
}

function applyTimelineGuard() {
  if (applying || !contract || contract.timeline_editable !== false) return;
  applying = true;
  try {
    for (const button of document.querySelectorAll(".scene-order button")) {
      button.disabled = true;
      button.title = contract.timeline_lock_reason || "Timeline editing is locked.";
    }
    const duration = durationInput();
    if (duration) {
      duration.disabled = true;
      duration.title = contract.timeline_lock_reason || "Timeline editing is locked.";
    }
    const section = document.querySelector(".timeline-section");
    if (section && !document.getElementById("overlay-timeline-lock")) {
      const notice = document.createElement("div");
      notice.id = "overlay-timeline-lock";
      notice.className = "notice";
      notice.style.marginTop = "12px";
      notice.textContent = contract.timeline_lock_reason;
      section.append(notice);
    }
  } finally {
    applying = false;
  }
}

async function loadContract() {
  if (!encodedProject || !encodedRun) return;
  const response = await fetch(
    `/api/project/${encodedProject}/agent-edit/${encodedRun}`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) return;
  const payload = await response.json();
  contract = payload?.editor?.contract || null;
  applyTimelineGuard();
}

const observer = new MutationObserver(applyTimelineGuard);
observer.observe(document.getElementById("app"), { childList: true, subtree: true });
loadContract().catch(() => {});
