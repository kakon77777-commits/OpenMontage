const suffix = "/agent-review";
const encodedProject = location.pathname.startsWith("/p/") && location.pathname.endsWith(suffix)
  ? location.pathname.slice(3, -suffix.length)
  : "";

const style = document.createElement("style");
style.textContent = `
  .evedirector-run-links {
    position: fixed;
    z-index: 50;
    right: 18px;
    bottom: 18px;
    display: grid;
    gap: 8px;
  }
  .evedirector-run-links a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 15px;
    border-radius: 10px;
    box-shadow: 0 12px 30px #0008;
    font: 800 10px/1 ui-monospace, SFMono-Regular, Consolas, monospace;
    letter-spacing: .06em;
    text-decoration: none;
  }
  .l6-director-link {
    border: 1px solid #22d3ee99;
    color: #031116;
    background: #22d3ee;
  }
  .l5-edit-link {
    border: 1px solid #34d39999;
    color: #04120d;
    background: #34d399;
  }
  .evedirector-run-links a:hover { filter: brightness(1.08); }
`;
document.head.append(style);

function ensureLinks() {
  let host = document.getElementById("evedirector-run-links");
  if (!host) {
    host = document.createElement("div");
    host.id = "evedirector-run-links";
    host.className = "evedirector-run-links";
    document.body.append(host);
  }
  return host;
}

function updateRunLinks() {
  const selected = document.querySelector(".run-card.active b");
  const runId = selected?.textContent?.trim();
  const host = document.getElementById("evedirector-run-links");
  if (!runId) {
    host?.remove();
    return;
  }
  const links = ensureLinks();
  links.innerHTML = "";

  const director = document.createElement("a");
  director.className = "l6-director-link";
  director.textContent = "OPEN UNIFIED WORKBENCH ↗";
  director.href = `/p/${encodedProject}/director/${encodeURIComponent(runId)}`;
  director.title = `Open unified canvas, workflow and timeline for ${runId}`;

  const editor = document.createElement("a");
  editor.className = "l5-edit-link";
  editor.textContent = "OPEN CONSTRAINED EDITOR ↗";
  editor.href = `/p/${encodedProject}/agent-edit/${encodeURIComponent(runId)}`;
  editor.title = `Open constrained editor for ${runId}`;

  links.append(director, editor);
}

const observer = new MutationObserver(updateRunLinks);
observer.observe(document.getElementById("app"), { childList: true, subtree: true });
updateRunLinks();
