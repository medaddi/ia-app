"""
The strategy library behind the "Analyse" button: for each pair, up to 4 strategies that each held up on 2 years of H1 / H4
(tuned on the first 60 %, won ≥ 55 % and made money on the last 40 % it never saw, positive with double costs, most of
its neighbouring settings positive too; the pair's spread + slippage, the stop counted first, one trade at a time).
The first one of each pair is the pair agent's own plan (the one that sends the automatic signals).

A strategy is a close beyond the high / low of the previous `n` candles:
  fade      against the stretch (filters: hours GMT, ADX below a level, RSI(14) at an extreme, the EMA200 trend side)
  breakout  with the EMA50 / EMA200 trend (filter: ADX above a level)
with a stop at `sl` × ATR(14), one target at `rr` R, closed at market after `mb` candles.
"""


def _s(id_, name, tf, fam, rr, mb, tuned, unseen, **p):
    return {"id": id_, "name": name, "tf": tf, "fam": fam, "rr": rr, "mb": mb, "p": p,
            "test": {"tuned": dict(zip(("trades", "winRate", "totalR"), tuned)), "unseen": dict(zip(("trades", "winRate", "totalR"), unseen))}}


LIBRARY: dict[str, list[dict]] = {
    "XAU/USD": [
        _s("XAU-BO40", "Trend breakout · 40 candles", "H4", "breakout", 1.25, 30, (43, 62.8, 17.1), (25, 72.0, 15.4), n=40, sl=2.0),
        _s("XAU-BO20", "Trend breakout · 20 candles, ADX ≥ 20", "H4", "breakout", 1.25, 30, (42, 61.9, 14.2), (30, 63.3, 13.3), n=20, sl=2.0, adx=20),
        _s("XAU-BO10", "Trend breakout · 10 candles, ADX ≥ 20", "H4", "breakout", 1.25, 30, (51, 58.8, 13.4), (39, 59.0, 14.2), n=10, sl=2.0, adx=20),
    ],
    "EUR/USD": [
        _s("EUR-ASIA", "Asian fade · 10 hours, ADX < 35", "H1", "fade", 1.0, 48, (129, 58.9, 16.3), (90, 56.7, 6.1), n=10, sl=2.0, hours=(0, 6), adx=35),
        _s("EUR-H4T", "H4 dip in the trend · 10 candles", "H4", "fade", 1.0, 30, (45, 55.6, 3.6), (38, 60.5, 7.4), n=10, sl=1.5, trend=True),
        _s("EUR-RSI", "RSI extreme fade · 10 hours, ADX < 35", "H1", "fade", 1.0, 24, (135, 55.6, 6.9), (82, 58.5, 7.8), n=10, sl=1.5, adx=35, rsi=30),
    ],
    "GBP/USD": [
        _s("GBP-T40", "Dip in the trend · 40 hours, ADX < 35", "H1", "fade", 1.25, 48, (51, 60.8, 14.8), (29, 65.5, 11.1), n=40, sl=1.5, adx=35, trend=True),
        _s("GBP-T40W", "Dip in the trend · 40 hours, 1.5R", "H1", "fade", 1.5, 48, (50, 56.0, 16.1), (27, 59.3, 10.6), n=40, sl=1.5, adx=35, trend=True),
        _s("GBP-T20", "Dip in the trend · 20 hours, wide stop", "H1", "fade", 1.0, 48, (89, 57.3, 7.8), (64, 57.8, 5.6), n=20, sl=2.0, adx=35, trend=True),
    ],
    "EUR/CHF": [
        _s("CHF-ASIA", "Asian fade · 10 hours (00–06 GMT)", "H1", "fade", 0.75, 24, (75, 81.3, 21.5), (64, 79.7, 15.0), n=10, sl=1.0, hours=(0, 6)),
        _s("CHF-LATE", "Late-night fade · 10 hours (22–05 GMT)", "H1", "fade", 0.75, 24, (74, 79.7, 19.7), (62, 77.4, 12.1), n=10, sl=1.0, hours=(22, 5)),
        _s("CHF-RSI", "RSI extreme fade · 10 hours", "H1", "fade", 1.0, 48, (88, 61.4, 13.2), (82, 62.2, 11.3), n=10, sl=1.5, rsi=30),
    ],
    "AUD/CAD": [
        _s("AC-R40", "Range fade · 40 hours", "H1", "fade", 0.75, 48, (222, 74.8, 42.7), (165, 70.9, 21.5), n=40, sl=1.0),
        _s("AC-H4R20", "H4 range fade · 20 candles", "H4", "fade", 1.0, 30, (62, 66.1, 17.9), (55, 65.5, 15.3), n=20, sl=1.5),
        _s("AC-H4R40", "H4 range fade · 40 candles", "H4", "fade", 1.0, 30, (48, 68.8, 16.4), (39, 64.1, 10.2), n=40, sl=1.5),
        _s("AC-RSI", "RSI extreme fade · 40 hours, ADX < 35", "H1", "fade", 1.25, 48, (69, 60.9, 20.8), (57, 59.6, 14.0), n=40, sl=2.0, adx=35, rsi=30),
    ],
    "AUD/CHF": [
        _s("ACH-R40", "Range fade · 40 hours, ADX < 35", "H1", "fade", 0.75, 48, (155, 75.5, 34.8), (106, 73.6, 20.0), n=40, sl=1.5, adx=35),
        _s("ACH-H4R40", "H4 range fade · 40 candles", "H4", "fade", 1.5, 30, (44, 56.8, 12.2), (34, 55.9, 13.0), n=40, sl=1.5),
        _s("ACH-LATE", "Late-night fade · 40 hours (22–05 GMT)", "H1", "fade", 1.25, 48, (67, 59.7, 18.0), (35, 62.9, 12.2), n=40, sl=1.5, hours=(22, 5)),
        _s("ACH-ASIA", "Asian fade · 40 hours, ADX < 35", "H1", "fade", 1.25, 48, (51, 56.9, 11.5), (30, 60.0, 8.6), n=40, sl=1.5, hours=(0, 6), adx=35),
    ],
}
