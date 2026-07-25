# EveDirector (OpenMontage fork)

**MANDATORY: Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

## Fork-specific rules that override nothing but bind everything

This repository is EveDirector, a fork of [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage).
AGENT_GUIDE.md still governs how you route a video-production request. In addition, the EveDirector
L0–L6 layers impose an authority boundary you must not cross ([`README.md`](README.md)):

- Never edit `examples/*/video_spec.yaml` or any canonical spec directly on a model's behalf.
  Propose a candidate run instead (`scripts/evedirector_local_agent.py propose`).
- Every candidate scene must anchor to a real line in a real source document.
- Applying a candidate is a human decision made through the L4 review workbench.
  Do not automate Validate, Apply, or Reject.
- Canvas layout is browser-local and carries no semantic authority. Do not persist it server-side.
- Do not widen an L5 allow-list to make a blocked edit possible. That is a design change requiring
  its own data model, permissions, and regression tests.
- All text-mode file I/O must declare `encoding="utf-8"` — `tests/test_text_encoding_contract.py`
  enforces this, because the Linux CI runners cannot observe a Windows CJK decode failure.

Beyond that, all instructions are in AGENT_GUIDE.md.
