"""
The three pair agents' plans (docs/STRATEGIES.md): one agent per pair, each reading its own strategy.

  Agent 1 · EUR/USD → Asian_Sweep_FVG_Engine     M5  (London / New York sweep of the Asian range, FVG limit)
  Agent 2 · GBP/USD → London_Judas_SMT_Engine    M5  (London fakeout of PDH/PDL/Asia with EUR/USD SMT, order-block limit)
  Agent 3 · AUD/CHF → Mean_Reversion_Range_Engine H1 (H4 range, RSI divergence + engulfing, market order)

The global risk manager (agent/risk_manager.py) sits on top of the three: 1 % risk lot, spread guard, USD correlation,
news, two trades per pair a day and the −2.5 % daily circuit breaker.
"""

from . import asian_sweep, london_judas, mean_reversion

ENGINES = {
    "asian_sweep_fvg": asian_sweep,
    "london_judas_smt": london_judas,
    "mean_reversion_range": mean_reversion,
}

AGENTS = {
    "EUR/USD": {
        "agent": 1, "rule": "asian_sweep_fvg", "name": "Asian_Sweep_FVG_Engine", "tf": "M5", "history": 12000, "minBars": 300,
        "params": asian_sweep.PARAMS, "maxSpreadPips": 1.5, "targetRange": [2.0, 20.0], "entryTypes": ["LIMIT"],
        "sessions": [[0, 7 * 60], [8 * 60, 11 * 60], [13 * 60 + 30, 16 * 60]],
        "why": "In the Asian hours EUR/USD sleeps in a tight box and the stops pile up just beyond it. At the London (or New York) "
               "open the banks run one side of the box, then turn: the agent waits for the close back through the last swing (MSS) "
               "with a fair value gap in the move, and sells (buys) the gap's 50 % back to the other side of the box.",
        "steps": ["07:00 London: Asian high / low of 00:00–07:00, range 12–45 pips (else no trade today)",
                  "08:00–11:00 and 13:30–16:00: a sweep of the Asian high (low) by at most 20 pips",
                  "M5 close beyond the last swing before the sweep (MSS), with an FVG > 2.5 pips in that leg",
                  "LIMIT at the FVG's 50 %, deleted after 12 M5 candles or if the target comes first",
                  "SL sweep extreme ± 3 pips (≤ 18 pips) · TP the other side of Asia (R:R ≥ 2) · BE at the Asian 50 % or 1R"],
    },
    "GBP/USD": {
        "agent": 2, "rule": "london_judas_smt", "name": "London_Judas_SMT_Engine", "tf": "M5", "history": 12000, "minBars": 300,
        "params": london_judas.PARAMS, "peer": "EUR/USD", "maxSpreadPips": 2.2, "targetRange": [3.0, 3.0], "entryTypes": ["LIMIT"],
        "sessions": [[8 * 60, 10 * 60]],
        "why": "Cable fakes a breakout at the London open (the Judas swing) and then runs the other way. The agent compares it with "
               "EUR/USD at the same moment: GBP/USD takes yesterday's high (or the Asian high) while EUR/USD fails to take its own, "
               "that divergence (SMT) marks the trap. It sells (buys) the order block of the move that breaks the structure back.",
        "steps": ["Before 08:00 London: PDH / PDL and the Asian high / low (00:00–07:30) of GBP/USD and EUR/USD",
                  "08:00–10:00: GBP/USD takes a level by 5–30 pips while EUR/USD does not take its own (SMT)",
                  "M5 close back inside and beyond the last swing (MSS), leg > 1.5 × ATR(14)",
                  "LIMIT at the open of the order block (last opposite candle before the leg)",
                  "SL fakeout extreme ± 4 pips (15–28 pips) · TP 3R · BE at 1.5R"],
    },
    "AUD/CHF": {
        "agent": 3, "rule": "mean_reversion_range", "name": "Mean_Reversion_Range_Engine", "tf": "H1", "history": 12500, "minBars": 1200,
        "params": mean_reversion.PARAMS, "maxSpreadPips": 3.0, "targetRange": [1.8, 40.0], "entryTypes": ["MARKET"],
        "why": "AUD/CHF does not run in one direction: it bounces between the top and the bottom of its range like a tennis ball. "
               "At a wall the agent does not guess: it waits for the sellers (buyers) to tire, an RSI divergence, then a strong "
               "engulfing candle, and trades back toward the middle and the other wall.",
        "steps": ["H4: ADX(14) < 28 · zones on the last 60 H4: Highest / Lowest ± 0.8 × ATR_H4(14)",
                  "H1 in a zone: swing low (high) at or beyond the previous one 5–30 H1 earlier, RSI(14) higher (lower) by 3+, the previous < 35 (> 65)",
                  "H1 engulfing candle, range > 0.7 × ATR_H1(14): MARKET at its close",
                  "SL 1.2 × ATR_H1 beyond the extreme · TP1 the range's middle (50 %, then BE) · TP2 the opposite zone · R:R ≥ 1.8 blended"],
    },
}
