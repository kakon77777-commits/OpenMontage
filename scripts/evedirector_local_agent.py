"""EveDirector L3 local-agent CLI.

The local model may propose a complete source-grounded video specification, but
it cannot overwrite the canonical file. Applying a candidate requires a
separate explicit approval command.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evedirector_agent import *  # noqa: F401,F403,E402
from evedirector_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
