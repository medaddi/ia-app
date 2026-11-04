"""
The SMC view of a chart (the method of the app's original Exunu engine, with every check real): context drawn on each
pair's chart, NEVER a signal. Tested as a strategy on 2 years of H1 / H4 it lost on every pair, so the signals come from
the pair agents; this shows the structure a smart-money trader reads.

  structure   confirmed 3-bar swings, labelled HH / HL / LH / LL; trend = the last two highs and lows
  BOS / CHoCH the latest close beyond the last swing: with the trend = BOS, against it = CHoCH
  liquidity   the nearest swing high above price (buy-side, BSL) and swing low below it (sell-side, SSL) not yet swept
  order block the last opposite candle before the impulse that made the latest BOS / CHoCH, until price trades through it
  FVG         the latest 3-candle gap (candle 1's high below candle 3's low, or the mirror) not yet filled
"""

from typing import Optional

from .base import BEAR, BULL, line, marker, zone

LOOKBACK = 160  # candles read for the view


def _swings(c, start: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Confirmed 3-bar swings (a swing at k is known once candle k + 1 closed)."""
    highs, lows = [], []
    for k in range(max(1, start), len(c) - 1):
        if c[k].high > c[k - 1].high and c[k].high > c[k + 1].high:
            highs.append((k, c[k].high))
        if c[k].low < c[k - 1].low and c[k].low < c[k + 1].low:
            lows.append((k, c[k].low))
    return highs, lows


def smc_view(c, symbol: str, tf_sec: int) -> dict:
    """{"zones", "lines", "markers", "trend", "summary"} of the SMC read on the latest candle."""
    out = {"zones": [], "lines": [], "markers": [], "trend": "NEUTRAL", "summary": ""}
    if len(c) < 30:
        return out
    start = max(1, len(c) - LOOKBACK)
    last = len(c) - 1
    end = c[last].time + 12 * tf_sec
    highs, lows = _swings(c, start)
    if len(highs) < 2 or len(lows) < 2:
        return out
    trend = ("BULLISH" if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]
             else "BEARISH" if highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1] else "NEUTRAL")
    out["trend"] = trend

    # the swing labels: each high against the previous high, each low against the previous low (the last 2 of each)
    for seq, high in ((highs, True), (lows, False)):
        for (k0, p0), (k1, p1) in list(zip(seq, seq[1:]))[-2:]:
            tag = ("HH" if p1 > p0 else "LH") if high else ("HL" if p1 > p0 else "LL")
            out["markers"].append(marker(f"SMC-{symbol}-{tag}-{c[k1].time}", c[k1].time, p1, high, tag, "#94A3B8", "circle"))

    # BOS / CHoCH: the latest close beyond the swing high / low that stood before it
    event = None
    hi_i = lo_i = 0
    for i in range(start + 2, len(c)):
        while hi_i < len(highs) and highs[hi_i][0] + 1 < i:
            hi_i += 1
        while lo_i < len(lows) and lows[lo_i][0] + 1 < i:
            lo_i += 1
        ph = highs[hi_i - 1] if hi_i else None
        pl = lows[lo_i - 1] if lo_i else None
        if ph and c[i].close > ph[1] and c[i - 1].close <= ph[1]:
            event = (i, ph, True)
        elif pl and c[i].close < pl[1] and c[i - 1].close >= pl[1]:
            event = (i, pl, False)
    if event:
        i, (k, lvl), up = event
        kind = "BOS" if (up and trend != "BEARISH") or (not up and trend != "BULLISH") else "CHoCH"
        out["lines"].append(line(f"SMC-{symbol}-BRK-{c[i].time}", "BOS" if kind == "BOS" else "CHOCH", c[k].time, c[i].time, lvl, None,
                                 f"{kind} {'↑' if up else '↓'}"))
        # the order block: the last opposite candle before the impulse that broke the level
        ob = next((j for j in range(i - 1, max(k - 1, i - 12), -1) if (c[j].close < c[j].open) == up), None)
        if ob is not None:
            top, bot = max(c[ob].open, c[ob].close), min(c[ob].open, c[ob].close)
            hit = any((x.low < bot) if up else (x.high > top) for x in c[i + 1:])  # traded through: no longer valid
            if not hit:
                out["zones"].append(zone(f"SMC-{symbol}-OB-{c[ob].time}", "OB_BULL" if up else "OB_BEAR", c[ob].time, end, top, bot,
                                         f"OB {'demand' if up else 'supply'}", (top + bot) / 2))

    # liquidity: the nearest swing high above / low below price not taken since it formed
    px = c[last].close
    bsl = next(((k, p) for k, p in reversed(highs) if p > px and all(x.high <= p for x in c[k + 1:])), None)
    ssl = next(((k, p) for k, p in reversed(lows) if p < px and all(x.low >= p for x in c[k + 1:])), None)
    if bsl:
        out["lines"].append(line(f"SMC-{symbol}-BSL-{c[bsl[0]].time}", "BSL", c[bsl[0]].time, end, bsl[1], None, "BSL"))
    if ssl:
        out["lines"].append(line(f"SMC-{symbol}-SSL-{c[ssl[0]].time}", "SSL", c[ssl[0]].time, end, ssl[1], None, "SSL"))

    # the latest unfilled fair value gap
    for i in range(last, max(start, last - 60), -1):
        a, b = c[i - 2], c[i]
        if b.low > a.high and all(x.low > a.high for x in c[i + 1:]):
            out["zones"].append(zone(f"SMC-{symbol}-FVG-{a.time}", "FVG_BULL", a.time, end, b.low, a.high, "FVG ↑", (b.low + a.high) / 2))
            break
        if b.high < a.low and all(x.high < a.low for x in c[i + 1:]):
            out["zones"].append(zone(f"SMC-{symbol}-FVG-{a.time}", "FVG_BEAR", a.time, end, a.low, b.high, "FVG ↓", (a.low + b.high) / 2))
            break

    parts = [f"structure {trend.lower()}"]
    if event:
        parts.append(f"last {'BOS' if (event[2] and trend != 'BEARISH') or (not event[2] and trend != 'BULLISH') else 'CHoCH'} {'up' if event[2] else 'down'}")
    if bsl:
        parts.append(f"BSL {bsl[1]:.5g}")
    if ssl:
        parts.append(f"SSL {ssl[1]:.5g}")
    out["summary"] = "SMC: " + ", ".join(parts)
    return out
