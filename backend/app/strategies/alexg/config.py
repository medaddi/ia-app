"""
Forex strategy configuration: "FXAlexG · Set & Forget GPA" (the user's written rules of the fxalexg
Set and Forget strategy):
  1. Trend on W1, D1 and H4 by market structure (HH/HL or LL/LH; a shift only on a candle BODY close
     beyond the previous swing). Trade only with the majority, ideally all three in sync.
  2. Areas of interest only on W1 / D1, with at least 3 touches. Buys above the AOI, sells below it.
  3. Ten confluences of 10% each → grade: A+ 80–100%, B 70–79%, C+ 60–69% (minimum), below 60% no trade.
  4. Entry: price touched the AOI, H4 rejection, then a 30m engulfing at the start of London or New York.
     SL beyond the pattern's head (or the rejection swing). TP at the next W1/D1 zone with 3+ touches,
     just before a round psychological level. Minimum 1:2, else no trade. Set & forget.
Every parameter lives here; strategy.py contains no magic numbers.
One config per pair: only the instrument, the assumed spread and the news currencies differ.
"""

import copy

from .._pairs import BANKS as _BANKS
from ..shared.sessions import LONDON

ALEXG_BASE = {
    "version": "2.0.0",
    "strategy": "FXAlexG_SetForget_GPA",
    "timeframes": {"bias": "W1/D1/H4", "setup": "D1/W1 AOI · H4", "entry": "M30"},
    "entryTf": "M30",  # the engulfing candle (rule 10: 30m or 15m; rule 4: 30m or 1H)
    "ltfTf": "H1",  # lower-timeframe pattern and EMA (rules 8 and 9: 1H or 30m)
    "history": 2600,  # entry candles analysed (the feed serves ~60 days of 30m)

    "trend": {
        "swingN": {"W1": 2, "D1": 3, "H4": 3},  # fractal swings per timeframe; the trend flips on a body close beyond the last swing
        "minAgree": 2,  # trade the majority: at least 2 of the 3 timeframes
    },
    "atrPeriod": 14,
    "emaPeriod": 50,  # 50 EMA on H4 and on the lower timeframe

    "aoi": {
        "swingN": 2,  # D1 / W1 swing points that make a zone
        "lookbackD1": 250,  # ~1 year of daily swings
        "lookbackW1": 156,  # ~3 years of weekly swings
        "clusterAtr": 0.3,  # swing points within 0.3 × ATR(D1) of the zone's first point form one zone (~20 pips on the majors)
        "minWidthAtr": 0.15,
        "minTouches": 3,  # a valid AOI has at least 3 touches
        "touchTolAtr": 0.25,  # price "at the AOI" = within 0.25 × ATR(D1) of the zone
        "touchBarsH4": 6,  # the touch happened in the last 6 H4 candles (one day)
    },

    "h4": {
        "barsH4": 6,  # H4 rejection is looked for in the last 6 H4 candles
        "emaTolAtr": 0.1,
        "structTolAtr": 0.25,
        "pinWickBody": 2,  # pin bar: rejection wick ≥ 2 × body …
        "wickRange": 0.5,  # … and ≥ 50% of the candle (also the "wick rejection")
    },

    "ltf": {
        "swingN": 2,
        "patternBars": 48,  # H&S / double top-bottom in the last 48 lower-timeframe candles
        "shoulderTolAtr": 0.6,  # the two shoulders within 0.6 × ATR of each other
        "doubleTolAtr": 0.3,  # the two tops / bottoms of a double within 0.3 × ATR
        "doubleMinGap": 4,
        "emaBars": 6,
        "emaTolAtr": 0.1,
    },

    "sessions": {
        # Rule 10 / entry trigger: the engulfing prints at the start of London or New York (8:00 AM New York = 13:00 London)
        "windows": [
            {"name": "London open", "tz": LONDON, "start": "07:00", "end": "10:00"},
            {"name": "New York open", "tz": LONDON, "start": "13:00", "end": "16:00"},
        ],
    },

    "risk": {
        "slBufferAtr": 0.1,  # × ATR(H1) beyond the head / the rejection swing
        "slLookbackLtf": 12,  # without a pattern: beyond the lowest low / highest high of the last 12 H1 candles
        "minSlPips": 10,
        "maxSlPips": 90,
        "minRr": 2,  # below 1:2 to the next zone: no trade
        "tpSpreadPips": 2,  # TP a little before the zone edge (spread)
        "roundStepPips": 50,  # psychological levels every 50 pips (…0.89000, 0.89500…)
        "roundBeforePips": 15,  # a round level up to 15 pips before the TP pulls the TP in front of it
        "roundOffsetPips": 3,
        "tp1R": 1,  # TP1 / TP2 are progress marks only (set & forget: one target, no partials, no breakeven)
        "tp2R": 2,
        "partials": [0, 0, 1],
        "breakeven": False,
        "marketValidMin": 30,
        "riskPct": 1,
        "balances": [500, 1000, 5000, 10000],
        "showLastSetupBars": 48,  # keep a closed trade on the chart for one day of 30m candles
    },

    "filters": {
        "maxSpreadPips": 4,
        "slippagePips": 0.2,
        "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
        "maxTradesPerDay": 2,
        "maxLossesPerDay": 1,
    },

    "scoring": {
        "confluenceWeight": 10,  # each of the 10 confluences = 10%
        "grades": [{"min": 80, "grade": "A+"}, {"min": 70, "grade": "B"}, {"min": 60, "grade": "C+"}],
        "thresholds": {"signal": 60, "watch": 50},  # C+ (60%) is the minimum to take a trade
    },
}


# pair → (assumed spread in pips, Yahoo ticker)
PAIRS = {
    "EUR/USD": (1.0, "EURUSD=X"),
    "GBP/USD": (1.5, "GBPUSD=X"),
    "USD/CAD": (1.5, "USDCAD=X"),
    "NZD/USD": (1.5, "NZDUSD=X"),
    "EUR/CHF": (1.5, "EURCHF=X"),
    "NZD/CAD": (2.5, "NZDCAD=X"),
    "AUD/CAD": (2.0, "AUDCAD=X"),
    "AUD/CHF": (2.0, "AUDCHF=X"),
}

NAMES = {"EUR/USD": "Euro / US Dollar", "GBP/USD": "British Pound / US Dollar", "USD/CAD": "US Dollar / Canadian Dollar",
         "NZD/USD": "New Zealand Dollar / US Dollar", "EUR/CHF": "Euro / Swiss Franc", "NZD/CAD": "New Zealand Dollar / Canadian Dollar",
         "AUD/CAD": "Australian Dollar / Canadian Dollar", "AUD/CHF": "Australian Dollar / Swiss Franc"}


def grade_of(score: float, cfg: dict) -> str:
    return next((g["grade"] for g in cfg["scoring"]["grades"] if score >= g["min"]), "NO TRADE")


def _config(pair: str, spread: float) -> dict:
    sym = pair.replace("/", "")
    cfg = copy.deepcopy(ALEXG_BASE)
    cfg["name"] = f"{sym} · FXAlexG Set & Forget GPA"
    cfg["spec"] = {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01}
    cfg["filters"]["assumedSpreadPips"] = spread
    ccys = [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in _BANKS[c]])
    return cfg


ALEXG_CONFIGS: dict[str, dict] = {pair: _config(pair, spread) for pair, (spread, _) in PAIRS.items()}
