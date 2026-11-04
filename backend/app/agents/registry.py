"""
The 4 pair agents, one per chart (app/agents/plans.py), each on the plan proven on 2 years of H1 / H4:

  XAU/USD → XAUUSD_TrendBreakout_Agent   H1 · breakout of the 20-hour channel in the EMA50 / EMA200 trend
  EUR/USD → EURUSD_AsianFade_Agent       H1 · fade of a close beyond the 10-hour channel, 00–06 GMT
  GBP/USD → GBPUSD_ChannelFade_Agent     H4 · fade of a close beyond the 10-candle channel, ADX < 35
  AUD/CHF → AUDCHF_AsianFade_Agent       H1 · fade of a close beyond the 40-hour channel, 22–05 GMT

AGENT_CONFIGS holds each pair's app config (spec, filters, risk, scoring) in the shape the rest of the app reads.
"""

import copy

from ..core.instrument_specs import INSTRUMENT_CONFIG
from .base import PairAgent
from .plans import AudChfAsianFadeAgent, EurAsianFadeAgent, GbpChannelFadeAgent, GoldBreakoutAgent

AGENTS: dict[str, PairAgent] = {"XAU/USD": GoldBreakoutAgent(), "EUR/USD": EurAsianFadeAgent(), "GBP/USD": GbpChannelFadeAgent(),
                                "AUD/CHF": AudChfAsianFadeAgent()}

ASSUMED_SPREAD_PIPS = {"XAUUSD": 2.5, "EURUSD": 1.0, "GBPUSD": 1.5, "AUDCHF": 2.0}  # gold: $0.25 (the costs of the 2-year test)
SLIPPAGE_PIPS = {"XAUUSD": 0.5, "EURUSD": 0.2, "GBPUSD": 0.2, "AUDCHF": 0.2}
NEWS_CURRENCIES = {"XAUUSD": ["USD"], "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"], "AUDCHF": ["AUD", "CHF"]}

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
