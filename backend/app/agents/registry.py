"""
The 4 autonomous pair agents, one per chart:

  XAU/USD → XAUUSD_Sovereign_SMC_Agent       M15 liquidity · M5 MSS + FVG ∩ OTE
  EUR/USD → EURUSD_AsianSweep_FVG_Agent      M15 Asian range · M5 sweep / MSS / FVG
  GBP/USD → GBPUSD_LondonJudas_SMT_Agent     D1 / M15 levels · M5 SMT vs EUR/USD + order block
  AUD/CHF → AUDCHF_MeanReversion_Range_Agent H4 ADX range · H1 RSI divergence + engulfing

AGENT_CONFIGS holds each pair's app config (spec, filters, risk, scoring) in the shape the rest of the app reads.
"""

import copy

from ..core.instrument_specs import INSTRUMENT_CONFIG
from .audchf import AUDCHFAgent
from .base import PairAgent
from .eurusd import EURUSDAgent
from .gbpusd import GBPUSDAgent
from .xauusd import XAUUSDAgent

AGENTS: dict[str, PairAgent] = {"XAU/USD": XAUUSDAgent(), "EUR/USD": EURUSDAgent(), "GBP/USD": GBPUSDAgent(), "AUD/CHF": AUDCHFAgent()}

ASSUMED_SPREAD_PIPS = {"XAUUSD": 2.5, "EURUSD": 1.0, "GBPUSD": 1.5, "AUDCHF": 2.0}  # gold: $0.25
SLIPPAGE_PIPS = {"XAUUSD": 0.5, "EURUSD": 0.2, "GBPUSD": 0.2, "AUDCHF": 0.2}
NEWS_CURRENCIES = {"XAUUSD": ["USD"], "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"], "AUDCHF": ["AUD", "CHF"]}

BASE = {
    "version": "4.0.0",
    "risk": {"riskPct": 1, "balances": [500, 1000, 5000, 10000], "marketValidMin": 60, "showLastSetupBars": 6},
    "filters": {"news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30}, "maxTradesPerDay": 2, "maxLossesPerDay": 2},
    "scoring": {"thresholds": {"signal": 75, "watch": 60}},
}


def _config(pair: str, ag: PairAgent) -> dict:
    k = ag.symbol
    ins = INSTRUMENT_CONFIG[k]
    cfg = copy.deepcopy(BASE)
    cfg.update(strategy=ag.agent_id, name=f"{k} · {ag.agent_id}", agent=ag.agent_id, engine=ag.name, rule=ag.agent_id, timeframes=dict(ag.timeframes),
               params=copy.deepcopy(ag.params), style="reversal", live=True, why=ag.why, steps=list(ag.steps), history=ag.history,
               targetRange=list(ag.target_range), entryTypes=list(ag.entry_types), peer=ag.peer)
    cfg["spec"] = {"symbol": k, "displaySymbol": pair, "decimals": ins["decimals"], "pipSize": ins["pip_size"], "contractSize": ins["contract_size"],
                   "minLot": 0.01, "lotStep": 0.01}
    cfg["filters"]["news"]["currencies"] = NEWS_CURRENCIES[k]
    cfg["filters"].update(assumedSpreadPips=ASSUMED_SPREAD_PIPS[k], slippagePips=SLIPPAGE_PIPS[k], maxSpreadPips=ins["max_spread_pips"])
    return cfg


AGENT_CONFIGS: dict[str, dict] = {pair: _config(pair, ag) for pair, ag in AGENTS.items()}
