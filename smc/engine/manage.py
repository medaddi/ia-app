"""The trade management lives in the app's backend (backend/app/smc/manage.py) so the backtest and the live trade manager
run the SAME code. This module is that one (not a copy)."""

import sys

from . import smc  # noqa: F401  (puts the backend on the path)
import app.smc.manage as _manage  # noqa: E402

sys.modules[__name__] = _manage
