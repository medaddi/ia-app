"""
The 6 pair agents, one per chart (app/agents/plans.py), each on its high-win-rate plan proven on 2 years of H1 / H4:

  XAU/USD → XAUUSD_TrendBreakout_Agent   H4 · 40-candle breakout in the trend · 1.25R
  EUR/USD → EURUSD_AsianFade_Agent       H1 · 10-hour fade, 00–06 GMT, ADX < 35 · 1R
  GBP/USD → GBPUSD_TrendPullback_Agent   H1 · 40-hour fade in the trend's direction, ADX < 35 · 1.25R
  EUR/CHF → EURCHF_AsianFade_Agent       H1 · 10-hour fade, 00–06 GMT · 0.75R
  AUD/CAD → AUDCAD_RangeFade_Agent       H1 · 40-hour fade · 0.75R
  AUD/CHF → AUDCHF_RangeFade_Agent       H1 · 40-hour fade, ADX < 35 · 0.75R

AGENT_CONFIGS holds each pair's app config (spec, filters, risk, scoring) in the shape the rest of the app reads.
"""

import copy

from ..core.instrument_specs import INSTRUMENT_CONFIG
from .base import PairAgent
from .plans import AudCadFadeAgent, AudChfFadeAgent, EurAsianFadeAgent, EurChfAsianFadeAgent, GbpTrendFadeAgent, GoldBreakoutAgent

AGENTS: dict[str, PairAgent] = {"XAU/USD": GoldBreakoutAgent(), "EUR/USD": EurAsianFadeAgent(), "GBP/USD": GbpTrendFadeAgent(),
                                "EUR/CHF": EurChfAsianFadeAgent(), "AUD/CAD": AudCadFadeAgent(), "AUD/CHF": AudChfFadeAgent()}

ASSUMED_SPREAD_PIPS = {"XAUUSD": 2.5, "EURUSD": 1.0, "GBPUSD": 1.5, "EURCHF": 1.5, "AUDCAD": 2.0, "AUDCHF": 2.0}  # gold: $0.25 (the test's costs)
SLIPPAGE_PIPS = {"XAUUSD": 0.5, "EURUSD": 0.2, "GBPUSD": 0.2, "EURCHF": 0.2, "AUDCAD": 0.2, "AUDCHF": 0.2}
NEWS_CURRENCIES = {"XAUUSD": ["USD"], "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"], "EURCHF": ["EUR", "CHF"], "AUDCAD": ["AUD", "CAD"],
                   "AUDCHF": ["AUD", "CHF"]}

BASE = {
    "version": "4.0.0",
    "risk": {"riskPct": 1, "balances": [500, 1000, 5000, 10000], "marketValidMin": 60, "showLastSetupBars": 6},
    "filters": {"news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30}},  # news: a note, never a block
    "scoring": {"thresholds": {"signal": 75, "watch": 60}},
}


def _config(pair: str, ag: PairAgent) -> dict:
    k = ag.symbol
    ins = INSTRUMENT_CONFIG[k]
    cfg = copy.deepcopy(BASE)
    cfg.update(strategy=ag.agent_id, name=f"{k} · {ag.agent_id}", agent=ag.agent_id, engine=ag.name, rule=ag.agent_id, timeframes=dict(ag.timeframes),
               params=copy.deepcopy(ag.params), style="trend" if getattr(ag, "rule", "") == "breakout" else "reversal", live=True, why=ag.why, steps=list(ag.steps), history=ag.history,
               targetRange=list(ag.target_range), entryTypes=list(ag.entry_types), peer=ag.peer)
    cfg["spec"] = {"symbol": k, "displaySymbol": pair, "decimals": ins["decimals"], "pipSize": ins["pip_size"], "contractSize": ins["contract_size"],
                   "minLot": 0.01, "lotStep": 0.01}
    cfg["filters"]["news"]["currencies"] = NEWS_CURRENCIES[k]
    cfg["filters"].update(assumedSpreadPips=ASSUMED_SPREAD_PIPS[k], slippagePips=SLIPPAGE_PIPS[k], maxSpreadPips=ins["max_spread_pips"])
    return cfg


AGENT_CONFIGS: dict[str, dict] = {pair: _config(pair, ag) for pair, ag in AGENTS.items()}
