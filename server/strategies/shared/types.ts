/**
 * Shared types for the EXUNU strategies (XAUUSD and EURUSD).
 * Times are unix seconds (UTC). A candle's `time` is its OPEN time.
 */

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export type Direction = "BULLISH" | "BEARISH";
export type Side = "BUY" | "SELL";

export interface InstrumentSpec {
  symbol: "XAUUSD" | "EURUSD";
  displaySymbol: "XAU/USD" | "EUR/USD";
  decimals: number;
  pipSize: number; // XAUUSD: 0.1 ($0.10), EURUSD: 0.0001
  contractSize: number; // units per 1.00 lot
  minLot: number;
  lotStep: number;
}

export interface ChecklistItem {
  key: string;
  rule: string;
  ruleAr: string;
  passed: boolean;
  detail: string;
  weight: number;
  required: boolean;
  quality?: number; // 0-1 partial credit for the score (defaults to passed ? 1 : 0)
}

export type StrategyStatus = "SIGNAL" | "WATCH" | "IGNORE" | "NO_TRADE";

/** Signal JSON exactly as specified for the app and Telegram. */
export interface SignalJson {
  symbol: "XAUUSD" | "EURUSD";
  strategy: string;
  setup: string;
  direction: Side;
  entry_type: "LIMIT" | "MARKET";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number;
  rr_tp2: number;
  score: number;
  timeframes: { bias: string; setup: string; entry: string };
  checklist: { rule: string; passed: boolean; detail: string }[];
  invalidation: string;
  expires_at: string;
  explanation: string;
}

export const TF_SEC: Record<string, number> = {
  M1: 60, M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400,
};

/** Keeps only candles that had fully closed at `nowSec` (no look-ahead). */
export function closedOnly(candles: Candle[], tfSec: number, nowSec: number): Candle[] {
  let end = candles.length;
  while (end > 0 && candles[end - 1].time + tfSec > nowSec) end--;
  return end === candles.length ? candles : candles.slice(0, end);
}

export const roundTo = (v: number, d: number) => Number(v.toFixed(d));
