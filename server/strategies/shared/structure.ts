/**
 * Swings and market structure.
 * - Swing: fractal with N candles on each side, strictly higher/lower. Confirmed only once the
 *   N right-side candles have closed (confirmedIndex = index + N).
 * - BOS: candle CLOSE beyond the last confirmed swing in the trend direction.
 * - CHoCH / MSS: first candle CLOSE beyond the last confirmed swing against the current trend.
 */

import { Candle, Direction } from "./types";
import { body } from "./indicators";

export interface Swing {
  index: number;
  time: number;
  price: number;
  kind: "HIGH" | "LOW";
  confirmedIndex: number;
  label: "HH" | "LH" | "HL" | "LL" | null;
  takenIndex: number | null; // first candle that traded beyond the swing
}

export interface StructureEvent {
  type: "BOS" | "CHOCH";
  direction: Direction;
  level: number;
  pivotIndex: number;
  pivotTime: number;
  breakIndex: number;
  breakTime: number;
  legStartIndex: number; // extreme of the leg that produced the break
  displacementIndex: number | null; // strongest candle of the leg if body > mult × avg body
  displacementMult: number; // strongest body / avg body in the leg
}

export function detectSwings(c: Candle[], n: number): Swing[] {
  const swings: Swing[] = [];
  for (let i = n; i < c.length - n; i++) {
    let isHigh = true;
    let isLow = true;
    for (let k = 1; k <= n; k++) {
      if (c[i - k].high >= c[i].high || c[i + k].high >= c[i].high) isHigh = false;
      if (c[i - k].low <= c[i].low || c[i + k].low <= c[i].low) isLow = false;
      if (!isHigh && !isLow) break;
    }
    if (isHigh) swings.push({ index: i, time: c[i].time, price: c[i].high, kind: "HIGH", confirmedIndex: i + n, label: null, takenIndex: null });
    if (isLow) swings.push({ index: i, time: c[i].time, price: c[i].low, kind: "LOW", confirmedIndex: i + n, label: null, takenIndex: null });
  }
  let prevHigh: Swing | null = null;
  let prevLow: Swing | null = null;
  for (const s of swings) {
    if (s.kind === "HIGH") {
      if (prevHigh) s.label = s.price > prevHigh.price ? "HH" : "LH";
      prevHigh = s;
    } else {
      if (prevLow) s.label = s.price > prevLow.price ? "HL" : "LL";
      prevLow = s;
    }
    for (let j = s.index + 1; j < c.length; j++) {
      if (s.kind === "HIGH" ? c[j].high > s.price : c[j].low < s.price) { s.takenIndex = j; break; }
    }
  }
  return swings;
}

export function detectStructure(
  c: Candle[],
  swings: Swing[],
  avgBody: number[],
  displacementMult: number
): { events: StructureEvent[]; trend: Direction | "NEUTRAL" } {
  const events: StructureEvent[] = [];
  let trend: Direction | "NEUTRAL" = "NEUTRAL";
  let activeHigh: Swing | null = null;
  let activeLow: Swing | null = null;
  const byConfirm = new Map<number, Swing[]>();
  for (const s of swings) {
    const list = byConfirm.get(s.confirmedIndex) || [];
    list.push(s);
    byConfirm.set(s.confirmedIndex, list);
  }

  for (let j = 0; j < c.length; j++) {
    for (const s of byConfirm.get(j) || []) {
      if (s.kind === "HIGH") activeHigh = s;
      else activeLow = s;
    }
    const bullBreak = activeHigh && c[j].close > activeHigh.price;
    const bearBreak = activeLow && c[j].close < activeLow.price;
    if (!bullBreak && !bearBreak) continue;
    const dir: Direction = bullBreak ? "BULLISH" : "BEARISH";
    const pivot = (bullBreak ? activeHigh : activeLow)!;

    // The leg starts at the opposite extreme between the pivot and the break
    let legStart = pivot.index;
    for (let i = pivot.index; i <= j; i++) {
      if (dir === "BULLISH" ? c[i].low < c[legStart].low : c[i].high > c[legStart].high) legStart = i;
    }
    let bestIdx: number | null = null;
    let bestMult = 0;
    for (let i = legStart; i <= j; i++) {
      const dirOk = dir === "BULLISH" ? c[i].close > c[i].open : c[i].close < c[i].open;
      const ab = avgBody[i];
      if (!dirOk || !(ab > 0)) continue;
      const m = body(c[i]) / ab;
      if (m > bestMult) { bestMult = m; bestIdx = i; }
    }

    events.push({
      type: trend !== "NEUTRAL" && trend !== dir ? "CHOCH" : "BOS",
      direction: dir,
      level: pivot.price,
      pivotIndex: pivot.index,
      pivotTime: pivot.time,
      breakIndex: j,
      breakTime: c[j].time,
      legStartIndex: legStart,
      displacementIndex: bestMult > displacementMult ? bestIdx : null,
      displacementMult: bestMult,
    });
    trend = dir;
    if (bullBreak) activeHigh = null; else activeLow = null;
  }
  return { events, trend };
}

/** Latest swing high and swing low labels describe the structure (HH/HL = bullish, LH/LL = bearish). */
export function structureFromLabels(swings: Swing[]): Direction | "NEUTRAL" {
  const lastHigh = [...swings].reverse().find(s => s.kind === "HIGH" && s.label);
  const lastLow = [...swings].reverse().find(s => s.kind === "LOW" && s.label);
  if (lastHigh?.label === "HH" && lastLow?.label === "HL") return "BULLISH";
  if (lastHigh?.label === "LH" && lastLow?.label === "LL") return "BEARISH";
  return "NEUTRAL";
}
