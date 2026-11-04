"""
The base of the pair agents: a channel plan proven on 2 years (tuned on the first 60 %, judged on the last 40 % it never
saw, docs/STRATEGIES.md), run like a disciplined trader:

  it reads the market first   the trend (EMA50 vs EMA200), the volatility against its usual level, the session, the
                              channel the plan watches and how far price is from it
  it acts only on its edge    a close beyond the channel: with the trend (breakout, gold) or against the stretch (fade)
  one trade at a time         while a trade runs the agent manages it and takes no other (as in the test)
  it plans the exit first     stop at an ATR multiple, one target (its plan's R: closer targets win more often), closed at
                              market at the plan's time limit

FSM: IDLE (outside its hours) · ARMED (watching the channel) · COOLDOWN (a strong trend for a fade) · IN_TRADE.
"""

from typing import Optional

from ..core.quant_primitives import adx, atr, ema
from .base import BEAR, BULL, PairAgent, context, line, marker
from .smc import smc_view

TARGET_R = 2.0


def in_hours(t: int, hours: Optional[tuple[int, int]]) -> bool:
    """The candle opened inside [start, end) GMT; a window may wrap midnight (22 → 5)."""
    if not hours:
        return True
    h, (a, b) = (t // 3600) % 24, hours
    return a <= h < b if a < b else (h >= a or h < b)


def utc1_windows(hours: Optional[tuple[int, int]]) -> Optional[list[tuple[int, int]]]:
    """The GMT hours as UTC+1 minute windows (the clock can_signal_at reads)."""
    if not hours:
        return None
    a, b = (hours[0] + 1) % 24 * 60, (hours[1] + 1) % 24 * 60
    return [(a, b)] if a < b else [(a, 1440), (0, b)]


class ChannelAgent(PairAgent):
    """A close beyond the high / low of the previous `channel` candles: a breakout in the trend, or a fade of the stretch."""

    rule = "fade"  # "breakout" | "fade"
    channel = 20
    sl_atr = 1.0
    hours: Optional[tuple[int, int]] = None  # GMT
    adx_max: Optional[float] = None
    trend_side = False  # a fade only in the trend's direction: buy a dip above EMA200, sell a rally below it
    target_r = TARGET_R
    max_bars = 48
    test: dict = {}
    note: Optional[str] = None
    entry_types = ("MARKET",)
    min_bars = 260

    def __init__(self):
        super().__init__()
        self.windows = utc1_windows(self.hours)
        self.target_range = (self.target_r, self.target_r)
        self.params = {"channel": self.channel, "slAtr": self.sl_atr, "hours": list(self.hours) if self.hours else None,
                       "adxMax": self.adx_max, "trendSide": self.trend_side, "maxBars": self.max_bars, "targetR": self.target_r}

    def session_name(self, minute: int) -> str:
        if not self.hours:
            return "Any session"
        m = (minute - 60) % 1440  # UTC+1 → GMT
        return "Plan window" if in_hours(m * 60, self.hours) else "Outside the plan window"

    # ---------------------------------------------------------------- the trade the plan would run (one at a time)
    @staticmethod
    def _exit_index(c, i: int, buy: bool, sl: float, tp: float, max_bars: int) -> int:
        j = i
        for j in range(i + 1, min(len(c), i + 1 + max_bars)):
            x = c[j]
            if (buy and x.low <= sl) or (not buy and x.high >= sl):  # the stop first when both sit in one candle
                return j
            if (buy and x.high >= tp) or (not buy and x.low <= tp):
                return j
        return j if j > i else len(c)  # still running at the last candle

    def _signal(self, c, i, hi, lo, a, ax, e50, e200) -> Optional[dict]:
        x = c[i]
        if hi[i] is None or a[i] is None or not in_hours(x.time, self.hours):
            return None
        if self.rule == "breakout":
            if e50[i] is None or e200[i] is None:
                return None
            if x.close > hi[i] and e50[i] > e200[i]:
                return {"buy": True, "level": hi[i]}
            if x.close < lo[i] and e50[i] < e200[i]:
                return {"buy": False, "level": lo[i]}
            return None
        if self.adx_max and (ax[i] is None or ax[i] >= self.adx_max):
            return None
        sig = {"buy": False, "level": hi[i]} if x.close > hi[i] else {"buy": True, "level": lo[i]} if x.close < lo[i] else None
        if sig and self.trend_side and (e200[i] is None or sig["buy"] != (x.close > e200[i])):
            return None  # a dip is bought only above EMA200, a rally sold only below it
        return sig

    def _why(self, sig: dict, x, a: float, ax, e50, e200) -> list[str]:
        n, buy, lvl = self.channel, sig["buy"], sig["level"]
        side = "high" if (buy if self.rule == "breakout" else not buy) else "low"
        out = []
        if self.rule == "breakout":
            out.append(f"Trend {'up' if buy else 'down'}: EMA50 {e50:.5g} {'>' if buy else '<'} EMA200 {e200:.5g}")
            out.append(f"Close {x.close:.5g} beyond the {n}-candle {side} {lvl:.5g}: momentum takes over, trade with it")
        else:
            out.append(f"Close {x.close:.5g} beyond the {n}-candle {side} {lvl:.5g}: a stretch this pair usually gives back, fade it")
            if self.hours:
                out.append(f"Inside the {self.hours[0]:02d}:00–{self.hours[1]:02d}:00 GMT window: thin market, no volume behind the move")
            if self.adx_max:
                out.append(f"ADX {ax:.0f} < {self.adx_max:g}: no strong trend to run over the fade")
            if self.trend_side:
                out.append(f"With the trend: price {'above' if buy else 'below'} EMA200 {e200:.5g}, a {'dip bought' if buy else 'rally sold'}")
        out.append(f"Stop {self.sl_atr:g} × ATR ({self.pips(self.sl_atr * a):.1f} pips) · one target at {self.target_r:g}R · out after {self.max_bars} candles")
        return out

    # ---------------------------------------------------------------- the trader's read of the market now
    def _read(self, c, i, hi, lo, a, ax, e50, e200, busy: bool) -> tuple[str, str, str]:
        x = c[i]
        usual = sorted(v for v in a[max(0, i - 200):i + 1] if v)[len([v for v in a[max(0, i - 200):i + 1] if v]) // 2] if a[i] else None
        vol = "" if not usual else (f"volatility high ({a[i] / usual:.1f}× usual)" if a[i] > 1.5 * usual
                                    else f"volatility low ({a[i] / usual:.1f}× usual)" if a[i] < 0.7 * usual else "volatility normal")
        trend = "" if e50[i] is None or e200[i] is None else ("trend up" if e50[i] > e200[i] else "trend down")
        read = " · ".join(v for v in (trend, vol) if v)
        if busy:
            return "IN_TRADE", f"Managing the open trade: stop and target stay put · {read}", "IN TRADE"
        if hi[i] is None or a[i] is None:
            return "IDLE", "Not enough history", "—"
        nxt = c[i].time + (3600 if self.tf == "H1" else 14400)
        if self.hours and not in_hours(nxt, self.hours):
            return "IDLE", f"Outside its window ({self.hours[0]:02d}:00–{self.hours[1]:02d}:00 GMT): the edge is in the quiet hours only · {read}", "WAITING HOURS"
        if self.rule == "fade" and self.adx_max and ax[i] is not None and ax[i] >= self.adx_max:
            return "COOLDOWN", f"ADX {ax[i]:.0f} ≥ {self.adx_max:g}: a strong trend, no fade against it · {read}", "TRENDING"
        up, dn = self.pips(hi[i] - x.close), self.pips(x.close - lo[i])
        if self.rule == "breakout":
            if e50[i] is None or e200[i] is None:
                return "IDLE", "Not enough history for the trend", "—"
            if e50[i] > e200[i]:
                return "ARMED", f"{read}: waiting for a close above the {self.channel}-candle high {hi[i]:.5g} ({up:.0f} pips away) to buy the breakout", "TREND + CHANNEL"
            return "ARMED", f"{read}: waiting for a close below the {self.channel}-candle low {lo[i]:.5g} ({dn:.0f} pips away) to sell the breakout", "TREND + CHANNEL"
        return ("ARMED", f"{read}: watching {lo[i]:.5g} – {hi[i]:.5g} ({self.channel}-candle range, {dn:.0f} / {up:.0f} pips away): "
                         "a close outside it is faded", "STRETCH FADE")

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        n = self.channel
        if len(c) < max(self.min_bars, n + 2):
            return {"setups": [], "context": context("IDLE", "Not enough history")}
        a, ax = atr(c), adx(c)
        cl = [x.close for x in c]
        e50, e200 = ema(cl, 50), ema(cl, 200)
        hi: list[Optional[float]] = [None] * len(c)
        lo: list[Optional[float]] = [None] * len(c)
        for i in range(n, len(c)):
            w = c[i - n:i]
            hi[i], lo[i] = max(x.high for x in w), min(x.low for x in w)
        setups, busy_until = [], -1
        for i in range(210, len(c)):
            if i <= busy_until:
                continue
            sig = self._signal(c, i, hi, lo, a, ax, e50, e200)
            if not sig:
                continue
            x, buy = c[i], sig["buy"]
            risk = self.sl_atr * a[i]
            entry = x.close
            sl = entry - risk if buy else entry + risk
            tp = lambda k: entry + k * risk if buy else entry - k * risk  # noqa: E731
            tp3 = tp(self.target_r)
            busy_until = self._exit_index(c, i, buy, sl, tp3, self.max_bars)
            label = "BREAKOUT" if self.rule == "breakout" else "FADE"
            setups.append({
                "index": i, "time": x.time, "buy": buy, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp(0.5 * self.target_r), "tp2": tp(0.75 * self.target_r), "tp3": tp3,
                "partials": [0, 0, 1], "breakeven": False, "beOffset": 0, "expiryBars": None, "cancelLevel": None, "maxBars": self.max_bars,
                "session": self.session_name((x.time // 60 + 60) % 1440), "tag": f"{label} {self.channel}",
                "draw": {"zones": [], "priceLines": [line(f"{self.symbol}-LVL-{x.time}", "MSS_BREAK", c[i - n].time, x.time, sig["level"], None,
                                                          f"{n}-candle {'high' if sig['level'] == hi[i] else 'low'}")],
                         "markers": [marker(f"{self.symbol}-SIG-{x.time}", x.time, x.low if buy else x.high, not buy, label, BULL if buy else BEAR)]},
                "why": self._why(sig, x, a[i], ax[i], e50[i], e200[i]),
            })
        last = len(c) - 1
        state, banner, tag = self._read(c, last, hi, lo, a, ax, e50, e200, busy_until >= last)
        t0, t1 = c[max(0, last - n)].time, c[last].time + 3600 * 24
        lines = [line(f"{self.symbol}-HI-{c[last].time}", "SESSION_HIGH", t0, t1, hi[last], None, f"{n}-candle high"),
                 line(f"{self.symbol}-LO-{c[last].time}", "SESSION_LOW", t0, t1, lo[last], None, f"{n}-candle low")] if hi[last] is not None else []
        # the SMC view of the same candles: structure, liquidity, order block, FVG (context drawn on the chart, never a signal)
        smc = smc_view(c, self.symbol, 3600 if self.tf == "H1" else 14400)
        ctx = context(state, banner, self.session_name((c[last].time // 60 + 60) % 1440), tag, smc["zones"], lines + smc["lines"], smc["markers"])
        ctx["smc"] = {"trend": smc["trend"], "summary": smc["summary"]}
        return {"setups": setups, "context": ctx}
