/**
 * The 50 EMA every chart draws (the FXAlexG spec: the EMA 50 on closes, a secondary confluence, never a signal by itself).
 * The chart draws only the FXAlexG team's objects; the ICT-style overlays (FVG, BOS / CHoCH, premium / discount, killzones,
 * liquidity pools) were removed (the owner, 2026-11-19: "only the FXAlexG strategy").
 */
import type { DrawLine } from './smcDrawing';

export interface Bar { time: number; open: number; high: number; low: number; close: number }
export interface PdZone { from: number; to: number; high: number; low: number }
export interface SessionBand { from: number; to: number; label: string; color: string }

/** The 50 EMA on closes (alpha = 2 / 51), from the first 50 closes' average (the FXAlexG spec, 3.2). */
export function ema50(b: Bar[]): (number | null)[] {
  const out: (number | null)[] = new Array(b.length).fill(null);
  if (b.length < 50) return out;
  const a = 2 / 51;
  let e = b.slice(0, 50).reduce((s, x) => s + x.close, 0) / 50;
  out[49] = e;
  for (let i = 50; i < b.length; i++) { e = b[i].close * a + e * (1 - a); out[i] = e; }
  return out;
}

/** The blue 50 EMA of the timeframe on screen (from the whole series), as one line. */
export function emaLine(all: Bar[], tfSec: number): DrawLine | null {
  const e50 = ema50(all);
  const pts: [number, number][] = [];
  for (let i = Math.max(0, all.length - 400); i < all.length; i++) { const v = e50[i]; if (v != null) pts.push([all[i].time + tfSec, v]); }
  return pts.length ? { points: pts, color: '#3b82f6', label: '50 EMA' } : null;
}
