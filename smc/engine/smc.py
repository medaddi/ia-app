"""The shared engine lives in the app's backend (backend/app/smc/engine.py) so the research and the live app run the SAME
code. This module is that engine (not a copy)."""

import sys
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

import app.smc.engine as _engine  # noqa: E402

sys.modules[__name__] = _engine
