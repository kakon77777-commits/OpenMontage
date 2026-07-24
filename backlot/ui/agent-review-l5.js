const suffix = "/agent-review";
const encodedProject = location.pathname.startsWith("/p/") && location.pathname.endsWith(suffix)
  ? location.pathname.slice(3, -suffix.length)
  : "";

const style = document.createElement("style");
style.textContent = `
  .l5-edit-link {
    position: fixed;
    z-index: 50;
    right: 18px;
    bottom: 18px;
    display: inline-flex;
    align-items: center;
    min-height: 42px;
    padding: 0 15px;
    border: 1px solid #34d39999;
    border-radius: 10px;
    color: #04120d;
    background: #34d399;
    box-shadow: 0 12px 30px #0008;
    font: 800 10px/1 ui-monospace, SFMono-Regular, Consolas, monospace;
    letter-spacing: .06em;
    text-decoration: none;
  }
  .l5-edit-link:hover { filter: brightness(1.08); }
`;
document.head.append(style);

function updateEditorLink() {
  const selected = document.querySelector(".run-card.active b");
  const runId = selected?.textContent?.trim();
  let link = document.getElementById("l5-edit-link");
  if (!runId) {
    link?.remove();
    return;
  }
  if (!link) {
    link = document.createElement("a");
    link.id = "l5-edit-link";
    link.className = "l5-edit-link";
    link.textContent = "EDIT AS DERIVED CANDIDATE ↗";
    document.body.append(link);
  }
  link.href = `/p/${encodedProject}/agent-edit/${encodeURIComponent(runId)}`;
  link.title = `Open constrained editor for ${runId}`;
}

const observer = new MutationObserver(updateEditorLink);
observer.observe(document.getElementById("app"), { childList: true, subtree: true });
updateEditorLink();
