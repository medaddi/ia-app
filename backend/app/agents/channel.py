"""
The base of the pair agents: a channel plan proven on 2 years (tuned on the first 60 %, judged on the last 40 % it never
saw, docs/STRATEGIES.md), run like a disciplined trader:

  it reads the market first   the trend (EMA50 vs EMA200), the volatility against its usual level, the session, the
                              channel the plan watches and how far price is from it
  it acts only on its edge    a close beyond the channel: with the trend (breakout) or against the stretch (fade)
  one trade at a time         while a trade runs the agent manages it and takes no other (as in the test)
  it plans the exit first     stop at an ATR multiple, one target (its plan's R: closer targets win more often), closed at
                              market at the plan's time limit

An agent runs one plan (the class attributes) or several `legs` in different hours (the fast gold agent: an Asian
breakout and a London fade), still one trade at a time, the first leg whose rule fires on a candle taking it.

FSM: IDLE (outside its hours) · ARMED (watching the channel) · COOLDOWN (a strong trend for a fade) · IN_TRADE.
"""

from types import SimpleNamespace
from typing import Optional

from ..core.quant_primitives import adx, atr, ema
from .base import BEAR, BULL, PairAgent, context, line, marker
from .smc import smc_view

TARGET_R = 2.0
LEG_FIELDS = ("rule", "channel", "sl_atr", "hours", "adx_max", "trend_side", "target_r", "max_bars")


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
    legs: tuple = ()  # several plans in different hours: dicts of LEG_FIELDS + "label"
    test: dict = {}
    note: Optional[str] = None
    entry_types = ("MARKET",)
    min_bars = 260

    def __init__(self):
        super().__init__()
        if self.legs:
            self.plan = [SimpleNamespace(**{"label": "", "hours": None, "adx_max": None, "trend_side": False, **d}) for d in self.legs]
        else:
            self.plan = [SimpleNamespace(label="", **{k: getattr(self, k) for k in LEG_FIELDS})]
        if len(self.plan) > 1:
            assert all(p.hours for p in self.plan), "the legs of an agent trade in their own hours"
            self.windows = [w for p in self.plan for w in utc1_windows(p.hours)]
            self.max_bars = max(p.max_bars for p in self.plan)
        else:
            self.windows = utc1_windows(self.plan[0].hours)
        rs = [p.target_r for p in self.plan]
        self.target_range = (min(rs), max(rs))
        par = [{"label": p.label, "rule": p.rule, "channel": p.channel, "slAtr": p.sl_atr, "hours": list(p.hours) if p.hours else None,
                "adxMax": p.adx_max, "trendSide": p.trend_side, "maxBars": p.max_bars, "targetR": p.target_r} for p in self.plan]
        self.params = {k: v for k, v in par[0].items() if k != "label"} if len(par) == 1 else {"legs": par, "maxBars": self.max_bars}

    def _leg_at(self, t: int):
        """The leg whose hours hold a candle opened at t (the only leg when it trades any hour)."""
        return next((p for p in self.plan if in_hours(t, p.hours)), None)

    def session_name(self, minute: int) -> str:
        if not any(p.hours for p in self.plan):
            return "Any session"
        m = (minute - 60) % 1440  # UTC+1 → GMT
        leg = self._leg_at(m * 60)
        return "Outside the plan window" if leg is None else (f"{leg.label} window" if leg.label else "Plan window")

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

    @staticmethod
    def _signal(leg, c, i, hi, lo, a, ax, e50, e200) -> Optional[dict]:
        x = c[i]
        if hi[i] is None or a[i] is None or not in_hours(x.time, leg.hours):
            return None
        if leg.rule == "breakout":
            if e50[i] is None or e200[i] is None:
                return None
            if x.close > hi[i] and e50[i] > e200[i]:
                return {"buy": True, "level": hi[i]}
            if x.close < lo[i] and e50[i] < e200[i]:
                return {"buy": False, "level": lo[i]}
            return None
        if leg.adx_max and (ax[i] is None or ax[i] >= leg.adx_max):
            return None
        sig = {"buy": False, "level": hi[i]} if x.close > hi[i] else {"buy": True, "level": lo[i]} if x.close < lo[i] else None
        if sig and leg.trend_side and (e200[i] is None or sig["buy"] != (x.close > e200[i])):
            return None  # a dip is bought only above EMA200, a rally sold only below it
        return sig

    def _hours_text(self, leg) -> str:
        return f"{leg.hours[0]:02d}:00–{leg.hours[1]:02d}:00 GMT"

    def _why(self, leg, sig: dict, x, a: float, ax, e50, e200) -> list[str]:
        n, buy, lvl = leg.channel, sig["buy"], sig["level"]
        side = "high" if (buy if leg.rule == "breakout" else not buy) else "low"
        out = [f"{leg.label}: {self._hours_text(leg)}"] if leg.label and leg.hours else []
        if leg.rule == "breakout":
            out.append(f"Trend {'up' if buy else 'down'}: EMA50 {e50:.5g} {'>' if buy else '<'} EMA200 {e200:.5g}")
            out.append(f"Close {x.close:.5g} beyond the {n}-candle {side} {lvl:.5g}: momentum takes over, trade with it")
        else:
            out.append(f"Close {x.close:.5g} beyond the {n}-candle {side} {lvl:.5g}: a stretch this pair usually gives back, fade it")
            if leg.hours and not leg.label:
                out.append(f"Inside the {self._hours_text(leg)} window: thin market, no volume behind the move")
            if leg.adx_max:
                out.append(f"ADX {ax:.0f} < {leg.adx_max:g}: no strong trend to run over the fade")
            if leg.trend_side:
                out.append(f"With the trend: price {'above' if buy else 'below'} EMA200 {e200:.5g}, a {'dip bought' if buy else 'rally sold'}")
        hrs = leg.max_bars * (1 if self.tf == "H1" else 4)
        out.append(f"Stop {leg.sl_atr:g} × ATR ({self.pips(leg.sl_atr * a):.1f} pips) · one target at {leg.target_r:g}R · "
                   f"out after {leg.max_bars} candles ({hrs} h)")
        return out

    # ---------------------------------------------------------------- the trader's read of the market now
    def _read(self, c, i, ch, a, ax, e50, e200, busy: bool) -> tuple[str, str, str]:
        x = c[i]
        usual = sorted(v for v in a[max(0, i - 200):i + 1] if v)[len([v for v in a[max(0, i - 200):i + 1] if v]) // 2] if a[i] else None
        vol = "" if not usual else (f"volatility high ({a[i] / usual:.1f}× usual)" if a[i] > 1.5 * usual
                                    else f"volatility low ({a[i] / usual:.1f}× usual)" if a[i] < 0.7 * usual else "volatility normal")
        trend = "" if e50[i] is None or e200[i] is None else ("trend up" if e50[i] > e200[i] else "trend down")
        read = " · ".join(v for v in (trend, vol) if v)
        if busy:
            return "IN_TRADE", f"Managing the open trade: stop and target stay put · {read}", "IN TRADE"
        if a[i] is None:
            return "IDLE", "Not enough history", "—"
        nxt = c[i].time + (3600 if self.tf == "H1" else 14400)
        leg = self._leg_at(nxt)
        if leg is None:
            hrs = " and ".join(self._hours_text(p) for p in self.plan)
            why = "the edge is in those hours only" if len(self.plan) > 1 else "the edge is in the quiet hours only"
            return "IDLE", f"Outside its window ({hrs}): {why} · {read}", "WAITING HOURS"
        hi, lo = ch[leg.channel]
        if hi[i] is None:
            return "IDLE", "Not enough history", "—"
        who = f"{leg.label} · " if leg.label else ""
        if leg.rule == "fade" and leg.adx_max and ax[i] is not None and ax[i] >= leg.adx_max:
            return "COOLDOWN", f"{who}ADX {ax[i]:.0f} ≥ {leg.adx_max:g}: a strong trend, no fade against it · {read}", "TRENDING"
        up, dn = self.pips(hi[i] - x.close), self.pips(x.close - lo[i])
        if leg.rule == "breakout":
            if e50[i] is None or e200[i] is None:
                return "IDLE", "Not enough history for the trend", "—"
            if e50[i] > e200[i]:
                return "ARMED", f"{who}{read}: waiting for a close above the {leg.channel}-candle high {hi[i]:.5g} ({up:.0f} pips away) to buy the breakout", "TREND + CHANNEL"
            return "ARMED", f"{who}{read}: waiting for a close below the {leg.channel}-candle low {lo[i]:.5g} ({dn:.0f} pips away) to sell the breakout", "TREND + CHANNEL"
        side = ""
        if leg.trend_side and e200[i] is not None:
            side = " (buys only: price above EMA200)" if x.close > e200[i] else " (sells only: price below EMA200)"
        return ("ARMED", f"{who}{read}: watching {lo[i]:.5g} – {hi[i]:.5g} ({leg.channel}-candle range, {dn:.0f} / {up:.0f} pips away): "
                         f"a close outside it is faded{side}", "STRETCH FADE")

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        nmax = max(p.channel for p in self.plan)
        if len(c) < max(self.min_bars, nmax + 2):
            return {"setups": [], "context": context("IDLE", "Not enough history")}
        a, ax = atr(c), adx(c)
        cl = [x.close for x in c]
        e50, e200 = ema(cl, 50), ema(cl, 200)
        ch: dict[int, tuple[list, list]] = {}
        for n in {p.channel for p in self.plan}:
            hi: list[Optional[float]] = [None] * len(c)
            lo: list[Optional[float]] = [None] * len(c)
            for i in range(n, len(c)):
                w = c[i - n:i]
                hi[i], lo[i] = max(x.high for x in w), min(x.low for x in w)
            ch[n] = (hi, lo)
        setups, busy_until = [], -1
        for i in range(210, len(c)):
            if i <= busy_until:
                continue
            for leg in self.plan:
                hi, lo = ch[leg.channel]
                sig = self._signal(leg, c, i, hi, lo, a, ax, e50, e200)
                if sig:
                    break
            else:
                continue
            x, buy = c[i], sig["buy"]
            risk = leg.sl_atr * a[i]
            entry = x.close
            sl = entry - risk if buy else entry + risk
            tp = lambda k: entry + k * risk if buy else entry - k * risk  # noqa: E731
            tp3 = tp(leg.target_r)
            busy_until = self._exit_index(c, i, buy, sl, tp3, leg.max_bars)
            label = "BREAKOUT" if leg.rule == "breakout" else "FADE"
            setups.append({
                "index": i, "time": x.time, "buy": buy, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp(0.5 * leg.target_r), "tp2": tp(0.75 * leg.target_r), "tp3": tp3,
                "partials": [0, 0, 1], "breakeven": False, "beOffset": 0, "expiryBars": None, "cancelLevel": None, "maxBars": leg.max_bars,
                "session": self.session_name((x.time // 60 + 60) % 1440), "tag": f"{leg.label or label} {leg.channel}".strip(),
                "draw": {"zones": [], "priceLines": [line(f"{self.symbol}-LVL-{x.time}", "MSS_BREAK", c[i - leg.channel].time, x.time, sig["level"], None,
                                                          f"{leg.channel}-candle {'high' if sig['level'] == hi[i] else 'low'}")],
                         "markers": [marker(f"{self.symbol}-SIG-{x.time}", x.time, x.low if buy else x.high, not buy, label, BULL if buy else BEAR)]},
                "why": self._why(leg, sig, x, a[i], ax[i], e50[i], e200[i]),
            })
        last = len(c) - 1
        state, banner, tag = self._read(c, last, ch, a, ax, e50, e200, busy_until >= last)
        # the channel drawn: the one of the leg trading next (or the first leg)
        nxt = self._leg_at(c[last].time + (3600 if self.tf == "H1" else 14400)) or self.plan[0]
        n = nxt.channel
        hi, lo = ch[n]
        t0, t1 = c[max(0, last - n)].time, c[last].time + 3600 * 24
        lines = [line(f"{self.symbol}-HI-{c[last].time}", "SESSION_HIGH", t0, t1, hi[last], None, f"{n}-candle high"),
                 line(f"{self.symbol}-LO-{c[last].time}", "SESSION_LOW", t0, t1, lo[last], None, f"{n}-candle low")] if hi[last] is not None else []
        # the SMC view of the same candles: structure, liquidity, order block, FVG (context drawn on the chart, never a signal)
        smc = smc_view(c, self.symbol, 3600 if self.tf == "H1" else 14400)
        ctx = context(state, banner, self.session_name((c[last].time // 60 + 60) % 1440), tag, smc["zones"], lines + smc["lines"], smc["markers"])
        ctx["smc"] = {"trend": smc["trend"], "summary": smc["summary"]}
        return {"setups": setups, "context": ctx}
