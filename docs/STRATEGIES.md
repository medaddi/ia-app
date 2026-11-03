# LiquidityDissection — the 4 autonomous pair agents

Each instrument is run by **its own agent** (`backend/app/agents/`) with **its own deterministic strategy** and **its own
chart**. Nothing else creates signals. Same closed candles → same result. Every session time is **UTC+1 (Morocco time)**,
a fixed offset (`core/quant_primitives.py`, `TZ_OFFSET_SEC`).

| Pair | Agent | Decides on |
|---|---|---|
| XAU/USD | `XAUUSD_Sovereign_SMC_Agent` | M5 (M15 session liquidity) |
| EUR/USD | `EURUSD_AsianSweep_FVG_Agent` | M5 (M15 Asian range) |
| GBP/USD | `GBPUSD_LondonJudas_SMT_Agent` | M5 (D1 / M15 levels, EUR/USD read at the same time) |
| AUD/CHF | `AUDCHF_MeanReversion_Range_Agent` | H1 (H4 ADX and channel) |

## 1. Instrument normalisation (`core/instrument_specs.py`)

| Symbol | Pip | Decimals | Max spread |
|---|---|---|---|
| EURUSD | 0.0001 | 5 | 1.5 pips |
| GBPUSD | 0.0001 | 5 | 2.2 pips |
| AUDCHF | 0.0001 | 5 | 3.0 pips |
| XAUUSD | 0.10 ($1.00 = 10 pips) | 2 | 3.5 pips |

`pips_to_price(symbol, pips)` and `price_to_pips(symbol, diff)` are used for every stop, buffer and zone width.

## 2. Quantitative primitives (`core/quant_primitives.py`)

- **5-bar fractal**: swing high at `[-3]` when `High[-3]` is above `High[-5]`, `High[-4]`, `High[-2]`, `High[-1]` (low: mirror). Known 2 candles after the pivot.
- **FVG** on `[-3] [-2] [-1]`: bullish `Low[-1] > High[-3]` (bottom `High[-3]`, top `Low[-1]`), bearish `High[-1] < Low[-3]`; `ce_50` = middle; min 2.5 pips forex, 6 pips ($0.60) gold.
- **Order block**: bullish MSS → the lowest bearish candle of the 10 before the break; bearish MSS → the highest bullish candle. `OB_Mean = (Open + Close) / 2`.
- **OTE** of a displacement leg: 0.618, 0.705 (sweet spot), 0.786 retracements.
- Wilder RSI / ATR / ADX (14).

## 3. The agents

Each agent is a state machine: `IDLE → ARMED → LIQUIDITY_SWEPT → MSS_CONFIRMED → PENDING_ORDER → IN_TRADE → COOLDOWN`.
A stop below the agent's minimum is widened to it; above its maximum there is no trade.

### EURUSD_AsianSweep_FVG_Agent
1. Asian range 00:00–07:00 (M15): high, low, 50 %. Range outside **12–45 pips** → COOLDOWN.
2. Killzones **08:00–11:00** and **13:30–16:00**: the Asian high (short) / low (long) taken by **1–20 pips** (more = a real breakout).
3. M5 close beyond the last confirmed M5 swing formed before the sweep (MSS) with an M5 FVG **≥ 2.5 pips** in the leg.
4. **LIMIT at the FVG ce_50**, cancelled after **12 M5 bars** (or once the target trades first). SL **3 pips** beyond the
   sweep wick (**6–18 pips**). TP1: stop to break-even at the Asian 50 % or +1R, whichever first. TP2: the opposite side
   of Asia, at least **2R**.
- Draws: `ASIAN_BOX` + ASIAN HIGH / LOW / EQUILIBRIUM 50% lines, `ASIAN HIGH SWEPT` marker, `MSS_BREAK`, FVG box with its `50% CE ENTRY` line, trade box.

### GBPUSD_LondonJudas_SMT_Agent
1. 07:45: PDH / PDL and Asian high / low (00:00–07:30) of GBPUSD **and** EURUSD.
2. **08:00–10:30**, at PDH / Asian high (short) or PDL / Asian low (long): A) GBPUSD takes its level by **4–30 pips** while
   EURUSD does not take its own, or B) EURUSD takes its level while GBPUSD fails within **5 pips** of its own.
3. GBPUSD closes back inside and beyond the last M5 swing, with a **3-candle displacement** (open of `[-3]` → close of `[-1]`) **≥ 1.5 × ATR_M5(14)**.
4. **LIMIT at OB_Mean**, cancelled after **90 min**. SL **4 pips** beyond the Judas extreme (**15–28 pips**). TP **3R**, break-even at **+1.5R**.
- Draws: PDH / PDL solid, Asian SESSION_HIGH / LOW dashed, `JUDAS TRAP + SMT vs EURUSD` badge, OB box with `OB 50% ENTRY`, `MSS_BREAK`, trade box.

### AUDCHF_MeanReversion_Range_Agent
1. H4: **ADX(14) ≥ 28 → COOLDOWN**. Else the 60-bar H4 range: supply `max(High) → − 0.8 × ATR_H4`, demand `min(Low) → + 0.8 × ATR_H4`, equilibrium the middle.
2. H1 in a zone, RSI(14) divergence between two swings **5–30 bars** apart: demand `Low_2 ≤ Low_1 + 2 pips`, `RSI_2 ≥ RSI_1 + 3`, `RSI_1 < 35`; supply the mirror with `RSI_1 > 65`.
3. A closed H1 **engulfing** in the reversal direction, range **≥ 0.7 × ATR_H1(14)** → **MARKET** at its close.
4. SL **1.2 × ATR_H1** beyond the divergence extreme (**20–35 pips**). TP1 equilibrium (**close 50 %** + break-even), TP2 the opposite zone boundary.
- Draws: `SUPPLY_BAND`, `DEMAND_BAND`, EQUILIBRIUM line, sloped `H1 RSI DIVERGENCE` line, `ENGULFING TRIGGER`, trade box.

### XAUUSD_Sovereign_SMC_Agent
1. 07:30: Asian high / low (00:00–07:30) + PDH / PDL. Asia **> 180 pips ($18)** → London is skipped, New York only.
   13:15: London high / low (08:00–13:15) join the New York pools.
2. Killzones **08:00–11:00** and **13:30–16:30**: a pool swept by **8–65 pips ($0.80–$6.50)** and an M5 close back inside
   within **1–3 candles**; the peak / trough and the protected M5 swing before the sweep are locked.
3. M5 close beyond the protected swing (MSS); displacement **≥ 25 pips ($2.50)** with a bearish (bullish) FVG **≥ 6 pips**
   or an order block. OTE of the leg. Entry: `max(fvg.bottom, ote_618)` when the FVG overlaps the OTE zone (short;
   long: `min(fvg.top, ote_618)`), else `fvg.ce_50` in the premium / discount, else the 0.705 sweet spot when the OB
   overlaps the OTE, else no order.
4. **LIMIT**, cancelled after **12 M5 candles** or once price reaches 50 % of the way to TP2. SL sweep extreme **± $0.50**
   (**25–65 pips**, above 65: skipped). TP1: +1.5R or the swept session's midpoint, whichever first, at least 1.3R —
   **close 50 %**, stop to **entry + 2 pips**. TP2: the opposite session pool beyond TP1, else **3R**.
- Draws: `ASIAN_BOX` (gold `rgba(212,175,55,0.10)`), `LONDON_BOX` (cyan `rgba(56,189,248,0.08)`), PDH / PDL / Asian / London lines,
  `XAU LIQUIDITY SWEEP + REJECTION` badge, `OTE_GOLD_ZONE` (61.8–78.6 %, dotted 70.5 %), FVG / OB boxes, `MSS_BREAK`, trade box.

## 4. The chart contract

Every agent emits an `AgentChartOverlayState` (`frontend/src/agentOverlay.ts`): `fsmState`, `statusBannerText` (top-left
of its chart), `metrics` (spread, ATR, session, confluence tag), `zones`, `priceLines`, `markers` and
`tradeExecutionBox`. It is in every strategy result (`overlay`) and at `GET /api/agents/overlay?symbol=`. A chart renders
only its own agent's state, in the single view and in the 4-chart split screen.

## 5. Multi-Agent Risk Coordinator (`core/risk_guard.py`)

- Base risk **1 %** of the equity per trade (the lot table of every signal).
- **Correlated USD exposure** (max 1.5 % unhedged) across EURUSD, GBPUSD and XAUUSD: same-direction USD trades still OPEN
  (stop not at break-even): **0 → 1 %**, **1 → 0.5 %** (lots halved, also on Telegram), **2 → blocked** until one reaches TP1 / BE.
- **News blackout**: no entry from 30 min before to 30 min after a red event of the pair's currencies; pending limits
  expire 30 min before it.
- Spread guard, live data, limit still valid / market entry not chased, at most 4 open orders.
- Day guard: 2 trades per pair a day; the desk locks until 00:00 (UTC+1) once the day's closed trades reach −2.5 %.

## 6. Testing

`backend/tests/test_four_agents.py` builds each agent's setup by hand and checks the order, the lifecycle and the chart
overlay; the replay (`strategies/replay.py`) runs the same code bar by bar. `GET /api/backtest?symbol=` replays the
agent on the feed's history (60 days of M5, 2 years of H1). Losses happen; nothing here is a guaranteed result.
