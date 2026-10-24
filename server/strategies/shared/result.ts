/**
 * Result and drawing types shared by both strategies. The chart, the agent, the signals feed,
 * Telegram and the backtester all consume this one shape.
 */

import { ChecklistItem, Direction, InstrumentSpec, SignalJson, Side, StrategyStatus } from "./types";
import { LifecycleParams, LifecycleResult } from "./lifecycle";

export type DrawingLayer = "sessions" | "levels" | "structure" | "swings" | "liquidity" | "fvg" | "ob" | "fib" | "trade";
export type DrawingColor = "bull" | "bear" | "gold" | "muted" | "asia" | "london" | "ny" | "liquidity" | "entry";

export interface Drawing {
  id: string;
  layer: DrawingLayer;
  kind: "box" | "hline" | "label" | "marker" | "session";
  tf: string; // timeframe the object was detected on ("H1 OB" on a lower timeframe chart)
  t1: number;
  t2: number | null; // null = extend to the right edge
  p1: number;
  p2?: number;
  text?: string;
  color: DrawingColor;
  style?: "solid" | "dashed" | "dotted";
  faded?: boolean;
  position?: "above" | "below";
  midline?: boolean; // dotted 50% line inside a box
}

export interface TradeSetup {
  id: string;
  setup: string; // "GOLD" | "A" | "B"
  direction: Side;
  entryType: "LIMIT" | "MARKET";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number;
  tp2Source: string;
  tp3Source: string;
  rrTp2: number;
  slDistance: number;
  slPips: number;
  lots: Record<string, number>;
  signalTime: number; // close time of the candle that completed the setup
  signalIndex: number; // index in the entry-timeframe candles
  expiresAt: number | null;
  invalidation: string;
  isFresh: boolean; // completed on the latest closed entry-timeframe candle
  lifecycle: LifecycleResult;
  params: Omit<LifecycleParams, "trailLevel" | "startIndex">; // replayable order parameters
  anchors: Record<string, unknown>;
}

export interface StrategyResult {
  symbol: InstrumentSpec["symbol"];
  displaySymbol: InstrumentSpec["displaySymbol"];
  strategy: string;
  strategyName: string;
  timeframes: { bias: string; setup: string; entry: string };
  nowSec: number;
  price: number;
  spec: InstrumentSpec;
  dataQuality: { ok: boolean; reason: string; source: string };
  market: { isOpen: boolean; window: string | null };
  bias: { direction: Direction | "NEUTRAL"; detail: string };
  status: StrategyStatus;
  score: number;
  checklist: ChecklistItem[];
  rejection: string | null;
  headline: string;
  headlineAr: string;
  setup: TradeSetup | null;
  signal: SignalJson | null;
  canNotify: boolean;
  news: { blocked: boolean; detail: string; next: string | null; source: string };
  day: { trades: number; losses: number };
  drawings: Drawing[];
  facts: Record<string, unknown>; // structured detector output for the AI agent
}
