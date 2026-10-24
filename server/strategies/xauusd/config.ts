/**
 * XAUUSD strategy configuration: "Liquidity Sweep + MSS + FVG".
 * Every parameter of the strategy lives here; strategy.ts contains no magic numbers.
 */

import { InstrumentSpec } from "../shared/types";
import { LONDON, NEW_YORK } from "../shared/sessions";

export const XAU_CONFIG = {
  version: "1.0.0",
  strategy: "LiquiditySweep_MSS_FVG",
  name: "XAUUSD · Liquidity Sweep + MSS + FVG",
  spec: { symbol: "XAUUSD", displaySymbol: "XAU/USD", decimals: 2, pipSize: 0.1, contractSize: 100, minLot: 0.01, lotStep: 0.01 } as InstrumentSpec,
  timeframes: { bias: "H4/H1", setup: "M15", entry: "M5" },

  structure: { swingN: 3, htfSwingN: 3, avgBodyPeriod: 20, displacementMult: 1.5 },
  bias: { emaPeriod: 200 },
  atrPeriod: 14,
  fvgMinAtr: 0.25,
  equalLevelTolAtr: 0.1,
  roundNumbers: { enabled: true, steps: [10, 50], count: 2 },

  sessions: {
    asia: { name: "Asia", tz: LONDON, start: "00:00", end: "06:00" },
    killzones: [
      { name: "London Open", tz: LONDON, start: "08:00", end: "11:00" },
      { name: "New York Open", tz: NEW_YORK, start: "08:30", end: "11:30" },
    ],
  },

  setup: {
    sweepLookbackBars: 48, // M5 candles searched for a sweep (4 hours)
    maxBarsSweepToMss: 6, // MSS must close within 6 M5 candles after the sweep
    sweepKinds: ["ASIA_L", "ASIA_H", "PDL", "PDH", "PWL", "PWH", "PSL", "PSH", "EQL", "EQH", "ROUND"],
    targetKinds: ["ASIA_H", "ASIA_L", "PSH", "PSL", "PDH", "PDL", "PWH", "PWL", "EQH", "EQL"],
  },

  risk: {
    slAtrBuffer: 0.2, // × ATR(14, M5) beyond the sweep wick, plus the spread
    minSl: 2, // $
    maxSl: 8, // $
    tp1R: 1,
    minRrTp2: 2,
    tp3R: 3,
    partials: [0.5, 0.25, 0.25] as [number, number, number],
    orderExpiryMin: 45,
    cancelIfTp1First: true,
    riskPct: 1,
    balances: [500, 1000, 5000, 10000],
  },

  filters: {
    maxSpread: 0.4, // $ (price units)
    assumedSpread: 0.25, // used when the feed has no live spread
    slippage: 0.05,
    volatility: { lookbackBars: 460, min: 0.5, max: 2.5 }, // ATR(14, H1) vs its 20-day average
    news: {
      currencies: ["USD"],
      keywords: ["CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell", "PCE", "GDP"],
      minutesBefore: 30,
      minutesAfter: 30,
    },
    maxTradesPerDay: 2,
    maxLossesPerDay: 2,
  },

  scoring: {
    weights: { bias: 15, killzone: 10, sweep: 15, displacement: 15, poi: 15, rr: 15, htfDistance: 10, volatility: 5 },
    thresholds: { signal: 75, watch: 60 },
  },

  drawings: { maxPerType: 5 },
};

export type XauConfig = typeof XAU_CONFIG;
