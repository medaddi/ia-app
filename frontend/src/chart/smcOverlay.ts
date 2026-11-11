/**
 * The SMC overlays every chart shows (data_feed_charting_engine_architecture_prompt.md, Phase 2.2), computed on the
 * candles of the timeframe on screen, so H4, H1, M15, M5 and M1 each show their own structure:
 *  - the dealing range from the last confirmed swing high (100 %) to swing low (0 %): premium tinted red, discount green,
 *    the equilibrium (50 %) dashed;
 *  - BOS (solid) / CHoCH (dotted) at the broken swing, only on a candle BODY close beyond it;
 *  - the Asian range, London killzone (07:00-10:00 UTC) and NY killzone (12:00-15:00 UTC) as session bands;
 *  - "$$$ BSL" / "$$$ SSL" at the Asian high / low and the previous day's high / low, "✕ Swept" once traded through;
 *  - unmitigated 3-candle FVGs (bull: C1.high < C3.low, bear: C1.low > C3.high); once price trades to their 50 % (CE)
 *    the box shrinks to what is left and says so; fully filled ones are dropped.
 * Swings: 2-candle fractals, known 2 candles after (no look-ahead in what is drawn at the right edge).
 */
import type { DrawBox, DrawLine, DrawSegment } from './smcDrawing';

export interface Bar { time: number; open: number; high: number; low: number; close: number }
export interface PdZone { from: number; to: number; high: number; low: number }
export interface SessionBand { from: number; to: number; label: string; color: string }
export interface SmcOverlay { pd: PdZone | null; boxes: DrawBox[]; segments: DrawSegment[]; sessions: SessionBand[]; lines: DrawLine[] }

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

const DAY = 86400;

function fractals(b: Bar[]) {
  const hi: boolean[] = new Array(b.length).fill(false), lo: boolean[] = new Array(b.length).fill(false);
  for (let i = 2; i < b.length - 2; i++) {
    hi[i] = b[i].high > b[i - 1].high && b[i].high > b[i - 2].high && b[i].high >= b[i + 1].high && b[i].high >= b[i + 2].high;
    lo[i] = b[i].low < b[i - 1].low && b[i].low < b[i - 2].low && b[i].low <= b[i + 1].low && b[i].low <= b[i + 2].low;
  }
  return { hi, lo };
}

/** The blue 50 EMA of the timeframe on screen (from the whole series), as one line. */
export function emaLine(all: Bar[], tfSec: number): DrawLine | null {
  const e50 = ema50(all);
  const pts: [number, number][] = [];
  for (let i = Math.max(0, all.length - 400); i < all.length; i++) { const v = e50[i]; if (v != null) pts.push([all[i].time + tfSec, v]); }
  return pts.length ? { points: pts, color: '#3b82f6', label: '50 EMA' } : null;
}

/** The secondary overlays (the chart's "Details" switch, off by default). */
export function computeSmc(all: Bar[], tfSec: number): SmcOverlay {
  const out: SmcOverlay = { pd: null, boxes: [], segments: [], sessions: [], lines: [] };
  const b = all.slice(-400);
  const n = b.length;
  if (n < 10) return out;
  const end = b[n - 1].time + tfSec;
  const { hi, lo } = fractals(b);

  // structure: the last swing high / low known at each candle; a body close beyond one is a break
  let trend = 0;
  let sh: { p: number; i: number } | null = null, sl: { p: number; i: number } | null = null;
  let lastSh: { p: number; i: number } | null = null, lastSl: { p: number; i: number } | null = null;
  const breaks: DrawSegment[] = [];
  for (let i = 0; i < n; i++) {
    const j = i - 2;
    if (j >= 0 && hi[j]) sh = lastSh = { p: b[j].high, i: j };
    if (j >= 0 && lo[j]) sl = lastSl = { p: b[j].low, i: j };
    const body = b[i].close;
    if (sh && body > sh.p) {
      const kind = trend === 1 ? 'bos' : 'choch';
      breaks.push({ from: b[sh.i].time, to: b[i].time + tfSec, price: sh.p, kind, dir: 1, label: kind === 'bos' ? 'BOS' : 'CHoCH' });
      trend = 1; sh = null;
    } else if (sl && body < sl.p) {
      const kind = trend === -1 ? 'bos' : 'choch';
      breaks.push({ from: b[sl.i].time, to: b[i].time + tfSec, price: sl.p, kind, dir: -1, label: kind === 'bos' ? 'BOS' : 'CHoCH' });
      trend = -1; sl = null;
    }
  }
  out.segments.push(...breaks.slice(-6));

  // the dealing range: the last confirmed swing high and swing low
  if (lastSh && lastSl && lastSh.p > lastSl.p) out.pd = { from: b[Math.min(lastSh.i, lastSl.i)].time, to: end, high: lastSh.p, low: lastSl.p };

  // sessions and their liquidity: intraday charts only
  if (tfSec <= 3600) {
    const lastDay = b[n - 1].time - (b[n - 1].time % DAY);
    for (let d = lastDay - 2 * DAY; d <= lastDay; d += DAY) {
      out.sessions.push({ from: d, to: d + 6 * 3600, label: 'Asia', color: 'rgba(96,165,250,0.10)' },
        { from: d + 7 * 3600, to: d + 10 * 3600, label: 'London KZ', color: 'rgba(212,175,55,0.12)' },
        { from: d + 12 * 3600, to: d + 15 * 3600, label: 'NY KZ', color: 'rgba(244,114,182,0.10)' });
    }
    const inRange = (a: number, z: number) => b.filter(x => x.time >= a && x.time < z);
    const pools: { price: number; dir: number; name: string; made: number }[] = [];
    const asia = inRange(lastDay, lastDay + 6 * 3600);
    if (asia.length && b[n - 1].time >= lastDay + 6 * 3600 - tfSec) {
      pools.push({ price: Math.max(...asia.map(x => x.high)), dir: 1, name: 'Asia High', made: lastDay + 6 * 3600 },
        { price: Math.min(...asia.map(x => x.low)), dir: -1, name: 'Asia Low', made: lastDay + 6 * 3600 });
    }
    let pd = inRange(lastDay - DAY, lastDay);
    for (let k = 2; !pd.length && k <= 4; k++) pd = inRange(lastDay - k * DAY, lastDay - (k - 1) * DAY);  // over a weekend
    if (pd.length) {
      pools.push({ price: Math.max(...pd.map(x => x.high)), dir: 1, name: 'PDH', made: lastDay },
        { price: Math.min(...pd.map(x => x.low)), dir: -1, name: 'PDL', made: lastDay });
    }
    for (const p of pools) {
      const after = b.filter(x => x.time >= p.made);
      const swept = after.some(x => (p.dir > 0 ? x.high > p.price : x.low < p.price));
      out.segments.push({ from: p.made - (p.name.startsWith('Asia') ? 6 * 3600 : DAY), to: end, price: p.price, kind: swept ? 'sweep' : 'liquidity', dir: p.dir,
        label: `$$$ ${p.dir > 0 ? 'BSL' : 'SSL'} · ${p.name}${swept ? ' ✕ Swept' : ''}` });
    }
  }

  // FVGs from the last 150 candles: unmitigated, or shrunk once their 50 % (CE) is traded
  const fvgs: DrawBox[] = [];
  for (let i = Math.max(2, n - 150); i < n; i++) {
    const c1 = b[i - 2], c3 = b[i];
    for (const dir of [1, -1]) {
      const bottom = dir > 0 ? c1.high : c3.high, top = dir > 0 ? c3.low : c1.low;
      if (!(top > bottom)) continue;
      const later = b.slice(i + 1);
      const reach = dir > 0 ? Math.min(Infinity, ...later.map(x => x.low)) : Math.max(-Infinity, ...later.map(x => x.high));
      const mid = (top + bottom) / 2;
      if (dir > 0 ? reach <= bottom : reach >= top) continue;  // filled 100 %: gone
      const ce = dir > 0 ? reach <= mid : reach >= mid;
      const t2 = dir > 0 ? Math.min(top, reach) : top, b2 = dir > 0 ? bottom : Math.max(bottom, reach);
      fvgs.push({ from: b[i - 1].time, to: end, top: t2, bottom: b2, kind: 'fvg', dir, label: `${dir > 0 ? 'Bull' : 'Bear'} FVG${ce ? ' · CE mitigated' : ''}` });
    }
  }
  out.boxes.push(...fvgs.slice(-6));
  return out;
}
