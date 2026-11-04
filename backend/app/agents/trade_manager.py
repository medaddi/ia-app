"""
The trade-management agents: one per pair, separate from the setup agents. A setup agent only looks for setups (it
keeps scanning while its earlier trades run); its trade-management agent runs every trade that was sent:

  at each tick (the cron, every minute) for every sent trade of its pair that is not finished:
  1. replays the trade on the latest candles (the same lifecycle as the app): PENDING → OPEN → TP1_HIT → CLOSED, or
     CANCELLED / EXPIRED for a limit that never filled
  2. tells the traders what to do, once per step, on Telegram and on the app (Web Push):
       🟡 ORDER FILLED · 🎯 TP1 HIT (close 50 % / move the SL to break-even, +2 pips on gold) · 📈 +1R · ⚠️ NEAR SL ·
       📰 NEWS IN N MIN · ⌛ ORDER EXPIRES SOON
  3. announces how the trade ended (TP / SL / break-even / cancelled) and closes the journal trades taken on it.
"""

from ..db import SessionLocal
from ..followup import follow_up
from ..push import push_closed
from ..trading import update_signal_outcomes


class TradeManagerAgent:
    def __init__(self, pair: str):
        self.pair = pair
        self.agent_id = f"{pair.replace('/', '')}_TradeManager_Agent"

    async def run(self, bundle: dict, entry_tf: str) -> dict:
        """One pass over the pair's running trades. Never raises: a failing notice is logged, the next tick retries."""
        from ..telegram.bot import notify_closed

        r = bundle["result"]
        candles = bundle["candles"].get(entry_tf) or []
        ended: list[dict] = []
        out = {"closed": 0, "notices": 0, "errors": []}
        try:
            with SessionLocal() as db:
                update_signal_outcomes(db, self.pair, candles, ended)
        except Exception as err:
            out["errors"].append(f"outcomes: {err!r}")
        if ended:
            out["closed"] = len(ended)
            for name, fn in (("telegram", notify_closed), ("push", push_closed)):
                try:
                    await fn(ended)
                except Exception as err:  # one channel failing never blocks the other
                    out["errors"].append(f"{name} result: {err!r}")
        try:
            out["notices"] = await follow_up(self.pair, r.get("price"))
        except Exception as err:
            out["errors"].append(f"follow-up: {err!r}")
        return out


def managers(pairs) -> dict[str, TradeManagerAgent]:
    return {p: TradeManagerAgent(p) for p in pairs}
