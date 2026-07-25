"""Backlot — the living storyboard.

A read-only, disk-derived production board for OpenMontage. A small local web
server watches ``projects/`` and renders each production's pipeline stages,
script, scene plan, generated assets, decisions, cost, and activity — live.

Design contract (see internal/design/LIVING_STORYBOARD.md):
- Observation, not reporting: all state derives from files the pipeline
  already writes. Agents never update the UI.
- Never block, never break: malformed or missing state degrades gracefully.
- The agent's only duty: ``python -m backlot open <project>`` at pipeline init.
"""

__version__ = "0.1.0"

DEFAULT_PORT = 4750


def _register_evedirector_extensions() -> None:
    """Attach optional EveDirector routes before Backlot builds its app.

    L5 semantic writes and L6 unified views are nested under the isolated L4
    review router. The L6 router is read-only; all semantic submission remains
    delegated to L5's derived-run endpoint and the L3/L4 authority gates.
    """
    from backlot.agent_edit import router as agent_edit_router
    from backlot.agent_review import router as agent_review_router
    from backlot.director import router as director_router

    agent_review_router.include_router(agent_edit_router)
    agent_review_router.include_router(director_router)


_register_evedirector_extensions()
