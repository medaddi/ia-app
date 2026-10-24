/**
 * Strategy service: the ONLY two strategies in the app.
 *   XAUUSD → Liquidity Sweep + MSS + FVG (bias H4/H1, setup M15, entry M5)
 *   EURUSD → Trend Pullback + London Breakout Filter (bias D1/H4, zones H1, entry M15)
 * Fetches real candles, computes today's trade/loss count by replaying the strategy itself on
 * today's closed candles (deterministic, survives restarts), runs the strategy now and caches it.
 */

import { fetchCandleSeries, fetchLivePrice, getMarketSessionStatus } from "../liveMarket";
import { Candle, closedOnly, TF_SEC } from "./shared/types";
import { StrategyResult } from "./shared/result";
import { loadNewsCalendar } from "./shared/news";
import { inLocalWindow, tradingDayKey, zonedParts } from "./shared/sessions";
import { activeWindow } from "./shared/common";
import { detectSwings } from "./shared/structure";
import { evaluateXauusd } from "./xauusd/strategy";
import { evaluateEurusd } from "./eurusd/strategy";
import { XAU_CONFIG } from "./xauusd/config";
import { EUR_CONFIG } from "./eurusd/config";
import { replay, ReplayState, statsAt, StrategyDef } from "./replay";
import { buildExplanation } from "../agent/explain";

export type Sym = "XAU/USD" | "EUR/USD";
export type Tf = "M5" | "M15" | "H1" | "H4" | "D1";

const PROVIDER_TF: Record<Tf, string> = { M5: "5M", M15: "15M", H1: "1H", H4: "4H", D1: "1D" };

export const STRATEGY_DEFS: Record<Sym, StrategyDef & { tfs: Tf[]; limits: Partial<Record<Tf, number>> }> = {
  "XAU/USD": {
    entryTf: "M5",
    tfs: ["M5", "M15", "H1", "H4"],
    limits: { M5: 20000, M15: 8000, H1: 5000, H4: 2000 },
    run: evaluateXauusd,
    canSignalAt: close => activeWindow(close - 1, XAU_CONFIG.sessions.killzones) !== null,
  },
  "EUR/USD": {
    entryTf: "M15",
    tfs: ["M15", "H1", "H4", "D1"],
    limits: { M15: 8000, H1: 5000, H4: 2000, D1: 800 },
    run: evaluateEurusd,
    canSignalAt: close => {
      const s = EUR_CONFIG.sessions;
      const fri = zonedParts(close - 1, s.fridayCutoff.tz).weekday === 5 && !inLocalWindow(close - 1, s.fridayCutoff.tz, "00:00", s.fridayCutoff.time);
      return !fri && activeWindow(close - 1, s.windows) !== null;
    },
    trail: (entry, side) => {
      const swings = detectSwings(entry, EUR_CONFIG.structure.swingN);
      const buf = EUR_CONFIG.risk.slBufferPips * EUR_CONFIG.spec.pipSize;
      const buy = side === "BUY";
      // Runner trails behind the latest confirmed M15 swing; the lifecycle only moves the stop forward
      return (i: number) => {
        const pts = swings.filter(s => s.kind === (buy ? "LOW" : "HIGH") && s.confirmedIndex <= i);
        return pts.length ? pts[pts.length - 1].price + (buy ? -buf : buf) : null;
      };
    },
  },
};

export function normalizeSymbol(s: string): Sym {
  return s.toUpperCase().includes("EUR") ? "EUR/USD" : "XAU/USD";
}

export interface StrategyBundle {
  result: StrategyResult;
  candles: Partial<Record<Tf, Candle[]>>;
}

export async function loadStrategyCandles(sym: Sym, livePrice?: number, fresh = false) {
  const def = STRATEGY_DEFS[sym];
  // `fresh` re-downloads the entry timeframe (candle-close dispatch); higher timeframes use the cache
  const series = await Promise.all(def.tfs.map(tf => fetchCandleSeries(sym, PROVIDER_TF[tf], def.limits[tf] || 1000, livePrice, { fresh: fresh && tf === def.entryTf })));
  const candles: Partial<Record<Tf, Candle[]>> = {};
  def.tfs.forEach((tf, i) => { candles[tf] = series[i].candles; });
  return { candles, isReal: series.every(s => !s.isSynthetic), source: series[0].source };
}

// Today's replay state per symbol, continued incrementally as new candles close
const dayReplay = new Map<string, ReplayState>();

function todayStats(sym: Sym, base: Parameters<typeof replay>[1], nowSec: number) {
  const def = STRATEGY_DEFS[sym];
  const tfSec = TF_SEC[def.entryTf];
  const entry = base.candles[def.entryTf] || [];
  const dayKey = tradingDayKey(nowSec);
  const key = `${sym}|${dayKey}`;
  let state = dayReplay.get(key);
  if (!state) {
    for (const k of dayReplay.keys()) if (k.startsWith(sym)) dayReplay.delete(k);
    const dayStart = entry.find(c => tradingDayKey(c.time) === dayKey)?.time ?? nowSec;
    state = { lastClose: dayStart, emitted: [] };
    dayReplay.set(key, state);
  }
  // Up to the previous close: the current bar is evaluated live
  const lastClosed = closedOnly(entry, tfSec, nowSec);
  const prevClose = lastClosed.length > 1 ? lastClosed[lastClosed.length - 2].time + tfSec : nowSec;
  replay(def, base, state.lastClose, prevClose, state);
  return { day: statsAt(def, entry, new Map(entry.map((c, i) => [c.time, i])), state.emitted, nowSec), emitted: state.emitted };
}

const cache = new Map<Sym, { bundle: StrategyBundle; expires: number }>();
const inflight = new Map<Sym, Promise<StrategyBundle>>();

export async function getStrategyResult(rawSymbol: string, opts: { force?: boolean; fresh?: boolean; livePrice?: number } = {}): Promise<StrategyBundle> {
  const sym = normalizeSymbol(rawSymbol);
  const hit = cache.get(sym);
  if (!opts.force && !opts.fresh && hit && hit.expires > Date.now()) return hit.bundle;
  const pending = inflight.get(sym);
  if (pending && !opts.fresh) return pending;
  const job = (async () => {
    const livePrice = opts.livePrice && opts.livePrice > 0 ? opts.livePrice : (await fetchLivePrice(sym, !!opts.fresh)).price;
    const [{ candles, isReal, source }, news] = await Promise.all([loadStrategyCandles(sym, livePrice, !!opts.fresh), loadNewsCalendar()]);
    const nowSec = Math.floor(Date.now() / 1000);
    const base = { candles, livePrice, spread: null, isRealData: isReal, dataSource: source, news };
    const { day } = isReal ? todayStats(sym, base, nowSec) : { day: { trades: 0, losses: 0 } };
    const result = STRATEGY_DEFS[sym].run({ ...base, nowSec, isMarketOpen: getMarketSessionStatus(sym).isOpen, day });
    if (result.signal) result.signal.explanation = buildExplanation(result);
    const bundle = { result, candles };
    cache.set(sym, { bundle, expires: Date.now() + 4000 });
    return bundle;
  })();
  inflight.set(sym, job);
  try { return await job; } finally { inflight.delete(sym); }
}

/** Review mode: the strategy exactly as it was at `asOfSec` (read-only, never notifies). */
export async function getStrategyResultAsOf(rawSymbol: string, asOfSec: number): Promise<StrategyBundle> {
  const sym = normalizeSymbol(rawSymbol);
  const [{ candles, isReal, source }, news] = await Promise.all([loadStrategyCandles(sym), loadNewsCalendar()]);
  const cut: Partial<Record<Tf, Candle[]>> = {};
  for (const [tf, c] of Object.entries(candles) as [Tf, Candle[]][]) cut[tf] = closedOnly(c, TF_SEC[tf], asOfSec);
  const entry = cut[STRATEGY_DEFS[sym].entryTf] || [];
  const base = {
    candles: cut, livePrice: entry[entry.length - 1]?.close ?? 0, spread: null, isRealData: isReal, news,
    dataSource: `${source} · review as of ${new Date(asOfSec * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`,
  };
  const def = STRATEGY_DEFS[sym];
  const dayStart = entry.find(c => tradingDayKey(c.time) === tradingDayKey(asOfSec))?.time ?? asOfSec;
  const state = replay(def, base, dayStart, asOfSec - TF_SEC[def.entryTf]);
  const day = statsAt(def, entry, new Map(entry.map((c, i) => [c.time, i])), state.emitted, asOfSec);
  const result = def.run({ ...base, nowSec: asOfSec, isMarketOpen: false, day });
  if (result.signal) result.signal.explanation = buildExplanation(result);
  return { result, candles: cut };
}
