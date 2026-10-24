import { Candle, ChecklistItem, InstrumentSpec, SignalJson } from "./types";
import { Level } from "./liquidity";
import { inLocalWindow } from "./sessions";
import { Swing } from "./structure";
import { TradeSetup } from "./result";

/** A level is still liquidity if no closed candle traded beyond it since it became available. */
export function isUntaken(level: Level, c: Candle[], uptoIndex: number): boolean {
  for (let i = 0; i <= uptoIndex && i < c.length; i++) {
    if (c[i].time <= level.availableFrom) continue;
    if (level.side === "HIGH" ? c[i].high > level.price : c[i].low < level.price) return false;
  }
  return true;
}

/** Nearest untaken swing beyond `price` in the trade direction (opposing liquidity on that timeframe). */
export function nearestSwingBeyond(swings: Swing[], price: number, buy: boolean, uptoIndex: number): Swing | null {
  const pool = swings
    .filter(s => s.kind === (buy ? "HIGH" : "LOW") && s.confirmedIndex <= uptoIndex && (s.takenIndex === null || s.takenIndex > uptoIndex))
    .filter(s => (buy ? s.price > price : s.price < price))
    .sort((a, b) => (buy ? a.price - b.price : b.price - a.price));
  return pool[0] || null;
}

export function activeWindow(tsSec: number, windows: { name: string; tz: string; start: string; end: string }[]) {
  return windows.find(w => inLocalWindow(tsSec, w.tz, w.start, w.end)) || null;
}

/** ATR now vs its average over `lookback` bars. */
export function volatilityRatio(atr: number[], lookback: number): { now: number; avg: number; ratio: number } {
  const vals = atr.filter(Number.isFinite);
  const now = vals[vals.length - 1] ?? NaN;
  const window = vals.slice(-lookback);
  const avg = window.reduce((a, b) => a + b, 0) / (window.length || 1);
  return { now, avg, ratio: avg > 0 ? now / avg : NaN };
}

export function item(key: string, rule: string, ruleAr: string, passed: boolean, detail: string, weight: number, required: boolean, quality?: number): ChecklistItem {
  return { key, rule, ruleAr, passed, detail, weight, required, quality: quality === undefined ? undefined : Math.max(0, Math.min(1, quality)) };
}

export function toSignalJson(spec: InstrumentSpec, strategy: string, setup: TradeSetup, score: number, timeframes: SignalJson["timeframes"], checklist: ChecklistItem[]): SignalJson {
  return {
    symbol: spec.symbol,
    strategy,
    setup: setup.setup,
    direction: setup.direction,
    entry_type: setup.entryType,
    entry: setup.entry,
    sl: setup.sl,
    tp1: setup.tp1,
    tp2: setup.tp2,
    tp3: setup.tp3,
    rr_tp2: Number(setup.rrTp2.toFixed(2)),
    score,
    timeframes,
    checklist: checklist.map(c => ({ rule: c.rule, passed: c.passed, detail: c.detail })),
    invalidation: setup.invalidation,
    expires_at: new Date((setup.expiresAt ?? setup.signalTime + 4 * 3600) * 1000).toISOString(),
    explanation: "",
  };
}

export const fmtTime = (t: number) => new Date(t * 1000).toISOString().slice(11, 16) + " UTC";
