"""The pair configs: the research project (smc/pairs/<PAIR>/config.json) and the live app (backend/app/smc/configs/) get the same file."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
common = {
    "sessions_utc": {"asia": [0, 6], "london": [7, 10], "newyork": [12, 15], "trade": [7, 16]},
    "sessions_note": "SCRIPT values in UTC, not shifted for DST (the script gives UTC). London opens 07:00 UTC in winter, 06:00 UTC in summer: testing DST-shifted killzones is an open experiment.",
    "news_window_min": 15,
    "risk_pct": 1.0,
    "split": {"in_sample": 0.6, "out_of_sample": 0.4},
    "timeframes": {"htf": "H1", "ltf": "M5", "context": ["D1", "H4 (from H1)", "M15"]},
}
pairs = {
    "XAUUSD": {"symbol": "XAU/USD", "decimals": 2, "pip": 0.1, "point": 0.01, "contract_size": 100, "pip_value_usd_per_lot": 10.0,
               "spread_pips": 2.5, "slippage_pips": 0.5, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 0.0,
               "notes": ["Very high volatility: the rules use structure levels (swings, OB, FVG), never fixed point distances; ATR only in the S3 range filter.",
                         "Data is COMEX GC=F futures (Yahoo has no spot history): levels sit a few dollars above spot.",
                         "USD, real yields and US data (NFP, CPI, FOMC) drive it: the news filter is mandatory live.",
                         "Spreads widen at news and rollover: the test uses one fixed spread (an under-estimate there)."]},
    "EURUSD": {"symbol": "EUR/USD", "decimals": 5, "pip": 0.0001, "point": 0.00001, "contract_size": 100000, "pip_value_usd_per_lot": 10.0,
               "spread_pips": 1.0, "slippage_pips": 0.2, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 0.0,
               "notes": ["Most liquid major: the most samples for the rules.", "DXY as a context filter is not in the data (open experiment).",
                         "Asian session often quiet: S3 compared with and without a minimum Asian range (open experiment)."]},
    "GBPUSD": {"symbol": "GBP/USD", "decimals": 5, "pip": 0.0001, "point": 0.00001, "contract_size": 100000, "pip_value_usd_per_lot": 10.0,
               "spread_pips": 1.5, "slippage_pips": 0.3, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 0.0,
               "notes": ["Sharper London open and Judas swings than EUR/USD: S3 is the natural candidate.",
                         "UK data (CPI, BoE, GDP) widens spreads and wicks: the fixed spread under-estimates news costs."]},
    "EURCHF": {"symbol": "EUR/CHF", "decimals": 5, "pip": 0.0001, "point": 0.00001, "contract_size": 100000, "pip_value_usd_per_lot": 12.5,
               "spread_pips": 1.5, "slippage_pips": 0.2, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 1.0,
               "notes": ["Low volatility: a setup whose stop is not at least 5x the cost is skipped (min_stop_cost_ratio).",
                         "SNB regime: the 2011-2015 floor (1.20) ended 15 Jan 2015. The data here starts in 2021 (D1) / 2024 (H1) / Aug 2026 (M5): every test is post-2015.",
                         "Narrow Asian range: S3 needs an Asian range of at least 1 H1 ATR (HYPOTHESIS, set before the test).",
                         "Pip value in USD depends on USD/CHF (about 12.5 per lot here): verify with the broker."]},
    "AUDCAD": {"symbol": "AUD/CAD", "decimals": 5, "pip": 0.0001, "point": 0.00001, "contract_size": 100000, "pip_value_usd_per_lot": 7.3,
               "spread_pips": 2.0, "slippage_pips": 0.3, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 1.0,
               "notes": ["Commodity cross (AUD: risk / China, CAD: oil): context only, not in the data (open experiment).",
                         "Wider spread than the majors.", "S3 needs an Asian range of at least 1 H1 ATR (HYPOTHESIS).",
                         "Pip value in USD depends on USD/CAD (about 7.3 per lot here): verify with the broker."]},
    "AUDCHF": {"symbol": "AUD/CHF", "decimals": 5, "pip": 0.0001, "point": 0.00001, "contract_size": 100000, "pip_value_usd_per_lot": 12.5,
               "spread_pips": 2.0, "slippage_pips": 0.3, "commission_usd_per_lot": 0.0, "s3_min_asia_range_atr": 1.0,
               "notes": ["Risk-on (AUD) vs safe haven (CHF): a risk-sentiment filter is an open experiment (no equity data here).",
                         "Low Asian volume: S3 needs an Asian range of at least 1 H1 ATR (HYPOTHESIS).",
                         "Pip value in USD depends on USD/CHF (about 12.5 per lot here): verify with the broker."]},
}
for k, v in pairs.items():
    cfg = {"pair": k, **v, "min_stop_cost_ratio": 5.0, **common}
    (root / "pairs" / k).mkdir(parents=True, exist_ok=True)
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    (root / "pairs" / k / "config.json").write_text(text, encoding="utf-8")
    (root.parent / "backend" / "app" / "smc" / "configs" / f"{k}.json").write_text(text, encoding="utf-8")  # the live app reads the same config
print("ok")
