/**
 * Order lifecycle simulator. The live status shown in the app, the daily trade/loss limits and
 * the backtester all use this one function, so they can never disagree.
 *
 * Price model: candles are bid prices. A BUY fills at ask (bid + spread) and exits at bid;
 * a SELL fills at bid and exits at ask. Stops get extra slippage. When one candle touches both
 * SL and a target, SL is assumed first (conservative).
 */

import { Candle, Side } from "./types";

export interface LifecycleParams {
  side: Side;
  entryType: "LIMIT" | "MARKET";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3: number | null; // null = trail only
  startIndex: number; // first candle after the signal candle
  expiryTime: number | null; // pending LIMIT order cancelled after this time
  marketFillTime?: number; // MARKET orders fill at the close of the signal candle
  cancelIfTp1BeforeFill: boolean;
  partials: [number, number, number];
  spread: number; // price units
  slippage: number; // price units
  trailLevel?: (index: number) => number | null; // runner stop after TP2
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
  rMultiple: number | null; // realised result in R once CLOSED
  outcome: "WIN" | "LOSS" | "BREAKEVEN" | null;
}

export function simulateLifecycle(c: Candle[], p: LifecycleParams, uptoIndex = c.length - 1): LifecycleResult {
  const buy = p.side === "BUY";
  const risk = Math.abs(p.entry - p.sl);
  const res: LifecycleResult = { state: p.entryType === "LIMIT" ? "PENDING" : "OPEN", events: [], fillTime: null, fillPrice: null, exitTime: null, rMultiple: null, outcome: null };
  let realised = 0;
  let remaining = 1;
  let stop = p.sl;
  let stage = 0; // 0 = before TP1, 1 = after TP1, 2 = after TP2
  const r = (exit: number) => ((buy ? exit - res.fillPrice! : res.fillPrice! - exit) / risk);

  let i = p.startIndex;
  if (p.entryType === "MARKET") {
    const fill = buy ? p.entry + p.spread + p.slippage : p.entry - p.slippage;
    res.fillPrice = fill;
    res.fillTime = p.marketFillTime ?? c[i]?.time ?? null; // filled as the confirmation candle closes
    res.events.push({ time: res.fillTime ?? 0, type: "FILL", price: fill });
  }

  for (; i <= uptoIndex && i < c.length; i++) {
    const x = c[i];
    if (res.state === "PENDING") {
      if (p.expiryTime !== null && x.time >= p.expiryTime) {
        res.state = "EXPIRED";
        res.events.push({ time: x.time, type: "EXPIRE", price: x.open });
        return res;
      }
      const touched = buy ? x.low + p.spread <= p.entry : x.high >= p.entry;
      const tp1First = p.cancelIfTp1BeforeFill && (buy ? x.high >= p.tp1 : x.low + p.spread <= p.tp1);
      if (!touched && tp1First) {
        res.state = "CANCELLED";
        res.events.push({ time: x.time, type: "CANCEL", price: p.tp1 });
        return res;
      }
      if (!touched) continue;
      res.state = "OPEN";
      res.fillPrice = buy ? p.entry : p.entry; // limit fills at its price
      res.fillTime = x.time;
      res.events.push({ time: x.time, type: "FILL", price: p.entry });
      // Stop on the fill candle itself (worst case)
      const slHit = buy ? x.low <= stop : x.high + p.spread >= stop;
      if (slHit) return close(x.time, buy ? stop - p.slippage : stop + p.slippage, "SL");
      continue;
    }

    const bidLow = x.low, bidHigh = x.high;
    const askLow = x.low + p.spread, askHigh = x.high + p.spread;
    const stopHit = buy ? bidLow <= stop : askHigh >= stop;
    if (stopHit) {
      const exit = buy ? stop - (stage === 0 ? p.slippage : 0) : stop + (stage === 0 ? p.slippage : 0);
      return close(x.time, exit, stage === 0 ? "SL" : stage === 1 ? "BE_EXIT" : "TRAIL_EXIT");
    }
    const reached = (tp: number) => (buy ? bidHigh >= tp : askLow <= tp);
    if (stage === 0 && reached(p.tp1)) {
      realised += p.partials[0] * r(p.tp1);
      remaining -= p.partials[0];
      stage = 1;
      stop = res.fillPrice!;
      res.state = "TP1_HIT";
      res.events.push({ time: x.time, type: "TP1", price: p.tp1 }, { time: x.time, type: "BE", price: stop });
    }
    if (stage === 1 && reached(p.tp2)) {
      realised += p.partials[1] * r(p.tp2);
      remaining -= p.partials[1];
      stage = 2;
      res.state = "TP2_HIT";
      res.events.push({ time: x.time, type: "TP2", price: p.tp2 });
    }
    if (stage === 2 && p.tp3 !== null && reached(p.tp3)) return close(x.time, p.tp3, "TP3");
    if (stage === 2 && p.trailLevel) {
      const t = p.trailLevel(i);
      if (t !== null && (buy ? t > stop : t < stop)) stop = t;
    }
  }
  return res;

  function close(time: number, exit: number, type: LifecycleEvent["type"]): LifecycleResult {
    realised += remaining * r(exit);
    remaining = 0;
    res.state = "CLOSED";
    res.exitTime = time;
    res.events.push({ time, type, price: exit });
    res.rMultiple = Number(realised.toFixed(3));
    res.outcome = realised > 0.05 ? "WIN" : realised < -0.05 ? "LOSS" : "BREAKEVEN";
    return res;
  }
}
