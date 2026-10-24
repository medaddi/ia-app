/**
 * Bar-by-bar replay of a strategy. Used by the live service (today's trade / loss count) and by
 * the backtester, so both run the exact same strategy code and order lifecycle.
 * At each closed entry-timeframe bar the strategy only sees candles closed at that moment.
 */

import { Candle, TF_SEC } from "./shared/types";
import { StrategyInput } from "./shared/input";
import { StrategyResult, TradeSetup } from "./shared/result";
import { LifecycleResult, simulateLifecycle } from "./shared/lifecycle";
import { tradingDayKey } from "./shared/sessions";

export interface StrategyDef {
  entryTf: "M5" | "M15";
  run: (input: StrategyInput) => StrategyResult;
  canSignalAt: (closeSec: number) => boolean; // cheap pre-filter: windows where a signal is possible
  trail?: (entry: Candle[], side: "BUY" | "SELL") => ((i: number) => number | null) | undefined;
}

export interface EmittedSignal {
  id: string;
  dayKey: string;
  signalTime: number;
  setup: TradeSetup;
  score: number;
  status: StrategyResult["status"];
  headline: string;
  checklist: StrategyResult["checklist"];
}

export interface ReplayState {
  lastClose: number;
  emitted: EmittedSignal[];
}

type Base = Omit<StrategyInput, "nowSec" | "day" | "isMarketOpen">;

export function replay(def: StrategyDef, base: Base, fromSec: number, toSec: number, state: ReplayState = { lastClose: fromSec, emitted: [] }): ReplayState {
  const tfSec = TF_SEC[def.entryTf];
  const entry = base.candles[def.entryTf] || [];
  const indexOf = new Map(entry.map((c, i) => [c.time, i]));
  for (let i = 0; i < entry.length; i++) {
    const close = entry[i].time + tfSec;
    if (close <= state.lastClose || close > toSec) continue;
    state.lastClose = close;
    if (!def.canSignalAt(close)) continue;
    const day = statsAt(def, entry, indexOf, state.emitted, close);
    const r = def.run({ ...base, nowSec: close, isMarketOpen: true, day });
    if (r.canNotify && r.setup && !state.emitted.some(e => e.id === r.setup!.id)) {
      state.emitted.push({ id: r.setup.id, dayKey: tradingDayKey(close - 1), signalTime: r.setup.signalTime, setup: r.setup, score: r.score, status: r.status, headline: r.headline, checklist: r.checklist });
    }
  }
  return state;
}

/** Trades placed and losses closed so far on the trading day of `atSec`. */
export function statsAt(def: StrategyDef, entry: Candle[], indexOf: Map<number, number>, emitted: EmittedSignal[], atSec: number): { trades: number; losses: number } {
  const tfSec = TF_SEC[def.entryTf];
  const dayKey = tradingDayKey(atSec - 1);
  let trades = 0, losses = 0;
  let upto = -1;
  for (let i = entry.length - 1; i >= 0; i--) if (entry[i].time + tfSec <= atSec) { upto = i; break; }
  for (const e of emitted) {
    if (e.dayKey !== dayKey) continue;
    const lc = outcome(def, entry, indexOf, e.setup, upto);
    if (!(lc.state === "CANCELLED" || lc.state === "EXPIRED")) trades++;
    if (lc.outcome === "LOSS") losses++;
  }
  return { trades, losses };
}

/** Lifecycle of an emitted setup using candles up to `uptoIndex` (the whole series by default). */
export function outcome(def: StrategyDef, entry: Candle[], indexOf: Map<number, number>, setup: TradeSetup, uptoIndex = entry.length - 1): LifecycleResult {
  const tfSec = TF_SEC[def.entryTf];
  const sigIdx = indexOf.get(setup.signalTime - tfSec);
  if (sigIdx === undefined) return setup.lifecycle;
  return simulateLifecycle(entry, { ...setup.params, startIndex: sigIdx + 1, trailLevel: def.trail?.(entry, setup.params.side) }, uptoIndex);
}
