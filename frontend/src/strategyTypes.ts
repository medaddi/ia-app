import type { InstrumentSymbol, StrategySymbol } from './instruments';
/**
 * Shapes returned by the Python backend for the two strategies (backend/app/strategies).
 * The chart, the side panel and the agent all read this one result.
 */

export type Direction = "BULLISH" | "BEARISH";
export type Side = "BUY" | "SELL";
export type StrategyStatus = "SIGNAL" | "WATCH" | "IGNORE" | "NO_TRADE";

export interface InstrumentSpec {
  symbol: StrategySymbol;
  displaySymbol: InstrumentSymbol;
  decimals: number;
  pipSize: number;
  contractSize: number;
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
  quality?: number;
}

export interface SignalJson {
  symbol: StrategySymbol;
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

export type LifecycleState = "PENDING" | "OPEN" | "TP1_HIT" | "TP2_HIT" | "CLOSED" | "CANCELLED" | "EXPIRED";

export interface LifecycleEvent {
  time: number;
  type: "FILL" | "TP1" | "BE" | "TP2" | "TP3" | "SL" | "BE_EXIT" | "TRAIL_EXIT" | "CANCEL" | "EXPIRE";
  price: number;
}

export interface LifecycleResult {
  state: LifecycleState;
  events: LifecycleEvent[];
  fillTime: number | null;
  fillPrice: number | null;
  exitTime: number | null;
  rMultiple: number | null;
  outcome: "WIN" | "LOSS" | "BREAKEVEN" | null;
}

export type DrawingLayer = "sessions" | "levels" | "structure" | "swings" | "liquidity" | "fvg" | "ob" | "fib" | "trade";
export type DrawingColor = "bull" | "bear" | "gold" | "muted" | "asia" | "london" | "ny" | "liquidity" | "entry";

export interface Drawing {
  id: string;
  layer: DrawingLayer;
  kind: "box" | "hline" | "label" | "marker" | "session";
  tf: string;
  t1: number;
  t2: number | null; // null = extend to the right edge
  p1: number;
  p2?: number;
  text?: string;
  color: DrawingColor;
  style?: "solid" | "dashed" | "dotted";
  faded?: boolean;
  position?: "above" | "below";
  midline?: boolean;
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
  signalTime: number;
  signalIndex: number;
  expiresAt: number | null;
  invalidation: string;
  isFresh: boolean;
  lifecycle: LifecycleResult;
  params: Record<string, unknown>;
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
  facts: Record<string, unknown>;
}

export interface ExunuSMCResult {
  terminal: string;
  symbol: InstrumentSymbol;
  current_price: number;
  status: "CONFIRMED_ENTRY" | "WAITING_CONFIRMATION" | "NO_SETUP";
  action: "BUY" | "SELL" | "WAIT";
  confidence: number;
  setup_json: {
    status: string;
    state: string;
    action: "BUY" | "SELL" | "WAIT";
    symbol: string;
    confidence: number;
    setup_grade: string;
    strategy: string;
    current_price: number;
    entry_price: number;
    stop_loss: number;
    target1: number;
    target2: number;
    target3: number;
    risk_reward: string;
    sl_pips: number;
    risk_management: { lot_sizing: Record<string, number | string>; is_rr_valid: boolean };
    timestamp: number;
  };
  agents: {
    structure_agent: { agent: string; summary: string; [k: string]: unknown };
    liquidity_agent: { agent: string; summary: string; [k: string]: unknown };
    risk_agent: { agent: string; summary: string; [k: string]: unknown };
    cto_agent: { agent: string; summary: string; [k: string]: unknown };
  };
  inter_agent_dialogue: Array<{ sender: string; recipient: string; topic: string; summary: string }>;
  summary_ar: string;
  explanation: string;
  timestamp: number;
  strategy: StrategyResult;
}
