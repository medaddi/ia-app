/**
 * Liquidity levels and sweeps.
 * Levels: PDH/PDL, PWH/PWL, Asian high/low, previous session high/low, equal highs/lows
 * (within tol × ATR) and round numbers. A level only exists from `availableFrom` (e.g. the
 * Asian high exists once the Asian session has closed).
 * Sweep: a candle wicks beyond the level and CLOSES back inside, on the first candle that takes it.
 */

import { Candle } from "./types";
import { Swing } from "./structure";
import { tradingDayKey, tradingWeekKey } from "./sessions";

export type LevelKind = "PDH" | "PDL" | "PWH" | "PWL" | "ASIA_H" | "ASIA_L" | "PSH" | "PSL" | "EQH" | "EQL" | "ROUND" | "SWING_H" | "SWING_L";

export interface Level {
  id: string;
  kind: LevelKind;
  label: string;
  price: number;
  side: "HIGH" | "LOW"; // HIGH = buy-side liquidity above, LOW = sell-side below
  time: number; // when it formed (for drawing)
  availableFrom: number; // first time a candle may sweep it
  weight: number; // importance for scoring (0-1)
}

export interface Sweep {
  id: string;
  level: Level;
  index: number;
  time: number;
  extreme: number; // wick extreme
  depthAtr: number;
}

/** PDH/PDL and PWH/PWL from intraday candles, using the 17:00 New York rollover. */
export function dailyWeeklyLevels(c: Candle[]): Level[] {
  if (!c.length) return [];
  const lastKey = tradingDayKey(c[c.length - 1].time);
  const lastWeek = tradingWeekKey(c[c.length - 1].time);
  const days = new Map<string, { high: number; low: number; start: number; end: number }>();
  const weeks = new Map<string, { high: number; low: number; start: number; end: number }>();
  for (const x of c) {
    for (const [map, key] of [[days, tradingDayKey(x.time)], [weeks, tradingWeekKey(x.time)]] as const) {
      const r = map.get(key);
      if (!r) map.set(key, { high: x.high, low: x.low, start: x.time, end: x.time });
      else { r.high = Math.max(r.high, x.high); r.low = Math.min(r.low, x.low); r.end = x.time; }
    }
  }
  const out: Level[] = [];
  const prevDay = [...days.keys()].filter(k => k < lastKey).pop();
  if (prevDay) {
    const d = days.get(prevDay)!;
    out.push({ id: `PDH-${prevDay}`, kind: "PDH", label: "PDH", price: d.high, side: "HIGH", time: d.start, availableFrom: d.end, weight: 0.9 });
    out.push({ id: `PDL-${prevDay}`, kind: "PDL", label: "PDL", price: d.low, side: "LOW", time: d.start, availableFrom: d.end, weight: 0.9 });
  }
  const prevWeek = [...weeks.keys()].filter(k => k < lastWeek).pop();
  if (prevWeek) {
    const w = weeks.get(prevWeek)!;
    out.push({ id: `PWH-${prevWeek}`, kind: "PWH", label: "PWH", price: w.high, side: "HIGH", time: w.start, availableFrom: w.end, weight: 1 });
    out.push({ id: `PWL-${prevWeek}`, kind: "PWL", label: "PWL", price: w.low, side: "LOW", time: w.start, availableFrom: w.end, weight: 1 });
  }
  return out;
}

/** Equal highs / lows: two or more untaken swings within tol × ATR of each other. */
export function equalLevels(swings: Swing[], atr: number, tol: number, uptoIndex: number): Level[] {
  const out: Level[] = [];
  for (const kind of ["HIGH", "LOW"] as const) {
    const live = swings.filter(s => s.kind === kind && s.confirmedIndex <= uptoIndex && (s.takenIndex === null || s.takenIndex > uptoIndex));
    for (let i = 0; i < live.length; i++) {
      for (let j = i + 1; j < live.length; j++) {
        if (Math.abs(live[i].price - live[j].price) > tol * atr) continue;
        const price = kind === "HIGH" ? Math.max(live[i].price, live[j].price) : Math.min(live[i].price, live[j].price);
        const id = `${kind === "HIGH" ? "EQH" : "EQL"}-${live[i].time}-${live[j].time}`;
        out.push({ id, kind: kind === "HIGH" ? "EQH" : "EQL", label: "$$$", price, side: kind, time: live[i].time, availableFrom: live[j].time, weight: 0.8 });
      }
    }
  }
  return out;
}

/** Round-number levels ($10 / $50 for gold) around the current price. */
export function roundNumberLevels(price: number, steps: number[], count: number, sinceTime: number): Level[] {
  const out: Level[] = [];
  for (const step of steps) {
    const base = Math.floor(price / step) * step;
    for (let k = -count; k <= count + 1; k++) {
      const p = base + k * step;
      out.push({ id: `ROUND-${step}-${p}`, kind: "ROUND", label: `${p}`, price: p, side: p >= price ? "HIGH" : "LOW", time: sinceTime, availableFrom: sinceTime, weight: step >= 50 ? 0.6 : 0.4 });
    }
  }
  // Keep the biggest step when two steps share a price
  return out.filter((l, i, arr) => arr.findIndex(x => x.price === l.price) === i);
}

/**
 * Sweeps of `levels` by candles in [from, to]. The candle that first trades beyond the level
 * after it became available is the take; it is a sweep only if that candle closes back inside.
 */
export function findSweeps(c: Candle[], levels: Level[], from: number, to: number, atr: number): Sweep[] {
  const out: Sweep[] = [];
  for (const lv of levels) {
    for (let i = 0; i <= to && i < c.length; i++) {
      const x = c[i];
      if (x.time <= lv.availableFrom) continue;
      const beyond = lv.side === "HIGH" ? x.high > lv.price : x.low < lv.price;
      if (!beyond) continue;
      const closedBack = lv.side === "HIGH" ? x.close < lv.price : x.close > lv.price;
      if (closedBack && i >= from) {
        const extreme = lv.side === "HIGH" ? x.high : x.low;
        out.push({ id: `SWEEP-${lv.id}-${x.time}`, level: lv, index: i, time: x.time, extreme, depthAtr: atr > 0 ? Math.abs(extreme - lv.price) / atr : 0 });
      }
      break; // only the first take counts
    }
  }
  return out.sort((a, b) => a.index - b.index || b.level.weight - a.level.weight);
}
