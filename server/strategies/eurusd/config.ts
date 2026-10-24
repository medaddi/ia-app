/**
 * EURUSD strategy configuration: "Trend Pullback + London Breakout Filter".
 * Every parameter of the strategy lives here; strategy.ts contains no magic numbers.
 */

import { InstrumentSpec } from "../shared/types";
import { LONDON } from "../shared/sessions";

export const EUR_CONFIG = {
  version: "1.0.0",
  strategy: "TrendPullback_LondonBreakout",
  name: "EURUSD · Trend Pullback + London Breakout Filter",
  spec: { symbol: "EURUSD", displaySymbol: "EUR/USD", decimals: 5, pipSize: 0.0001, contractSize: 100000, minLot: 0.01, lotStep: 0.01 } as InstrumentSpec,
  timeframes: { bias: "D1/H4", setup: "H1", entry: "M15" },

  structure: { swingN: 3, htfSwingN: 3, dailySwingN: 2, avgBodyPeriod: 20, displacementMult: 1.5 },
  bias: { emaFast: 50, emaSlow: 200 },
  atrPeriod: 14,
  fvgMinAtr: 0.25,
  dailyRoomPips: 15, // don't buy within 15 pips of daily resistance / PWH (mirror for sells)

  sessions: {
    asia: { name: "Asia", tz: LONDON, start: "00:00", end: "06:00" },
    windows: [
      { name: "London", tz: LONDON, start: "07:00", end: "10:30" },
      { name: "London/NY overlap", tz: LONDON, start: "13:00", end: "16:00" },
    ],
    fridayCutoff: { tz: LONDON, time: "14:00" },
  },

  setupA: {
    lookbackBars: 16, // M15 candles scanned for a confirmation candle
    pullbackBars: 6, // candles that form the pullback before/at the confirmation
    fib: [0.5, 0.618],
    fibTolerance: 0.05, // fraction of the leg allowed beyond the 61.8% line
    minConfluence: 2,
    emaPeriod: 50, // M15 EMA
    rsiPeriod: 14,
    rsiBuy: [40, 50] as [number, number],
    rsiSell: [50, 60] as [number, number],
    pinWickBody: 2,
    minLegPips: 15,
  },

  setupB: {
    minRangePips: 12,
    maxRangePips: 40,
  },

  risk: {
    slBufferPips: 3,
    slAtrMult: 1.5, // × ATR(14, M15), whichever is wider
    minSlPips: 8,
    maxSlPips: 25,
    tp1R: 1,
    tp2R: 2,
    minRr: 2,
    tp3RefR: 3, // reference only: TP3 trails behind M15 swings
    partials: [0.5, 0.25, 0.25] as [number, number, number],
    marketOrderValidMin: 15,
    riskPct: 1,
    balances: [500, 1000, 5000, 10000],
  },

  filters: {
    maxSpreadPips: 1.5,
    assumedSpreadPips: 0.8,
    slippagePips: 0.2,
    news: {
      currencies: ["EUR", "USD"],
      keywords: ["ECB", "Main Refinancing", "Monetary Policy", "Lagarde", "CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell"],
      minutesBefore: 30,
      minutesAfter: 30,
    },
    volatility: { lookbackBars: 460 },
    maxTradesPerDay: 3,
    maxLossesPerDay: 2,
  },

  scoring: {
    weights: { bias: 15, window: 10, zone: 20, trigger: 15, momentum: 10, rr: 15, htfDistance: 10, volatility: 5 },
    thresholds: { signal: 75, watch: 60 },
  },

  drawings: { maxPerType: 5 },
};

export type EurConfig = typeof EUR_CONFIG;
