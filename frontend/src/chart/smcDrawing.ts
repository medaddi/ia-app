/**
 * The pair's strategy drawn on the chart (backend smc/playbook.py draw()): its indicator lines (Bollinger 3σ, EMA 20/50/200),
 * its time windows (Silver Bullet, killzones, reversion hours) as shaded bands, its levels, and the setup's zones. Also: order blocks and FVGs as labelled boxes, BOS / CHoCH /
 * IDM / liquidity as short labelled segments from the candle they start on to the candle they end on, "Liquidity Sweep"
 * at the wick tip, and the setup's trade as TP / SL areas. A lightweight-charts series primitive: every object is placed
 * by TIME (interpolated between bars, so an H1 object sits right on an M5 or a D1 chart) and redrawn with the view.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { PdZone, SessionBand } from './smcOverlay';
import type { IChartApi, IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesApi, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';

export interface DrawBox { from: number; to: number; top: number; bottom: number; kind: 'ob' | 'fvg'; dir: number; label: string }
export interface DrawSegment { from: number; to: number; price: number; kind: 'bos' | 'choch' | 'sweep' | 'idm' | 'eq' | 'liquidity' | 'session'; dir: number; label: string }
export interface DrawLabel { time: number; price: number; text: string; above: boolean; kind: string }
export interface DrawTrade { from: number; to: number; entry: number; zone?: [number, number] | null; sl: number; tp: number; dir: number; label: string;
  slPips?: number; tpPips?: number; rr?: number; risk?: string }
/** An indicator line: [time, value] points, drawn as a polyline. */
export interface DrawLine { points: [number, number][]; color: string; label: string; dash?: boolean }
/** A time window of the strategy (e.g. the Silver Bullet hour): a shaded band over the whole height. */
export interface DrawWindow { from: number; to: number; label: string }
export interface SmcDrawing { boxes: DrawBox[]; segments: DrawSegment[]; labels: DrawLabel[]; trade: DrawTrade | null; lines?: DrawLine[]; windows?: DrawWindow[];
  pd?: PdZone | null; sessions?: SessionBand[] }

type Theme = 'dark' | 'light';
const BULL = '#16C784', BEAR = '#EA3943';

export class SmcDrawingPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  private request: (() => void) | null = null;
  private data: SmcDrawing | null = null;
  private times: number[] = [];
  private step = 3600;
  private theme: Theme = 'dark';
  private view: IPrimitivePaneView;
  private placed: { x0: number; x1: number; y0: number; y1: number }[] = [];  // the labels drawn this frame

  constructor() {
    const self = this;
    const renderer: IPrimitivePaneRenderer = { draw(target: CanvasRenderingTarget2D) { self.draw(target); } };
    this.view = { renderer: () => renderer, zOrder: () => 'normal' } as IPrimitivePaneView;
  }

  attached(p: SeriesAttachedParameter<Time>) {
    this.chart = p.chart as IChartApi;
    this.series = p.series as ISeriesApi<'Candlestick'>;
    this.request = p.requestUpdate;
  }

  detached() { this.chart = null; this.series = null; this.request = null; }
  paneViews() { return [this.view]; }
  updateAllViews() { /* positions are computed at draw time */ }

  update(data: SmcDrawing | null, barTimes: number[], stepSec: number, theme: Theme) {
    this.data = data;
    this.times = barTimes;
    this.step = stepSec;
    this.theme = theme;
    this.request?.();
  }

  /** x of a time: between two bars by interpolation, before / after the series by the timeframe's step. */
  private x(t: number): number | null {
    const ts = this.chart?.timeScale();
    const n = this.times.length;
    if (!ts || !n) return null;
    const at = (k: number) => { const v = ts.logicalToCoordinate(k as any); return v === null ? null : Number(v); };
    // before the first bar / after the last one the chart gives no position: extrapolated from the bar spacing
    if (t <= this.times[0] || t >= this.times[n - 1]) {
      const first = t <= this.times[0];
      const k = first ? 0 : n - 1;
      const x0 = at(k), x1 = at(first ? Math.min(1, n - 1) : Math.max(0, n - 2));
      if (x0 === null) return null;
      const spacing = x1 === null || n < 2 ? 6 : Math.abs(x0 - x1);
      return x0 + ((t - this.times[k]) / this.step) * spacing;
    }
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (this.times[m] <= t) lo = m; else hi = m; }
    const xa = at(lo), xb = at(hi);
    if (xa === null || xb === null) return null;
    return xa + (xb - xa) * ((t - this.times[lo]) / ((this.times[hi] - this.times[lo]) || this.step));
  }

  private y(p: number): number | null {
    const y = this.series?.priceToCoordinate(p);
    return y === null || y === undefined ? null : Number(y);
  }

  private draw(target: CanvasRenderingTarget2D) {
    const d = this.data;
    if (!d) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      this.placed = [];
      const W = mediaSize.width;
      const dark = this.theme === 'dark';
      const text = dark ? '#E5E7EB' : '#1F2937';
      ctx.font = "600 11px Inter, ui-sans-serif, system-ui, sans-serif";
      ctx.textBaseline = 'middle';
      const clampX = (x: number) => Math.max(0, Math.min(W, x));

      // 0a. session bands (Asia, London killzone, NY killzone): full height, the name at the bottom
      for (const s of d.sessions ?? []) {
        const x0 = this.x(s.from), x1 = this.x(s.to);
        if (x0 === null || x1 === null) continue;
        const a = clampX(x0), b = clampX(x1);
        if (b - a < 2) continue;
        ctx.fillStyle = s.color; ctx.fillRect(a, 0, b - a, mediaSize.height);
        ctx.fillStyle = dark ? 'rgba(229,231,235,0.55)' : 'rgba(31,41,55,0.6)'; ctx.textAlign = 'left';
        if (b - a > ctx.measureText(s.label).width + 6) ctx.fillText(s.label, a + 3, mediaSize.height - 9);
      }
      // 0b. the dealing range: premium (50-100 %) red, discount (0-50 %) green, the equilibrium dashed
      if (d.pd) {
        const p = d.pd;
        const x0 = this.x(p.from), x1 = this.x(p.to), yh = this.y(p.high), yl = this.y(p.low), ym = this.y((p.high + p.low) / 2);
        if (x0 !== null && x1 !== null && yh !== null && yl !== null && ym !== null) {
          const a = clampX(x0), b = clampX(x1);
          ctx.fillStyle = 'rgba(234,57,67,0.07)'; ctx.fillRect(a, yh, b - a, ym - yh);
          ctx.fillStyle = 'rgba(22,199,132,0.07)'; ctx.fillRect(a, ym, b - a, yl - ym);
          ctx.strokeStyle = '#D4AF37'; ctx.lineWidth = 1; ctx.setLineDash([6, 4]);
          ctx.beginPath(); ctx.moveTo(a, ym); ctx.lineTo(b, ym); ctx.stroke(); ctx.setLineDash([]);
          const r = Math.min(b, W - 4) - 6;
          this.tag(ctx, r, yh + 9, 'Premium', '#F87171', 'right');
          this.tag(ctx, r, ym - 8, 'EQ 50 %', '#D4AF37', 'right');
          this.tag(ctx, r, yl - 9, 'Discount', '#4ADE80', 'right');
        }
      }
      // 0. the strategy's time windows (shaded bands, label at the top) and its indicator lines
      (d.windows ?? []).forEach((w, wi) => {
        const x0 = this.x(w.from), x1 = this.x(w.to);
        if (x0 === null || x1 === null) return;
        const a = clampX(x0), b = clampX(x1);
        if (b - a < 2) return;
        ctx.fillStyle = dark ? 'rgba(212,175,55,0.07)' : 'rgba(212,175,55,0.10)';
        ctx.fillRect(a, 0, b - a, mediaSize.height);
        ctx.fillStyle = dark ? 'rgba(212,175,55,0.85)' : 'rgba(146,112,12,0.95)';
        ctx.textAlign = 'left';
        ctx.fillText(w.label, Math.max(4, Math.min(a + 4, W - ctx.measureText(w.label).width - 64)), 12 + 14 * wi);  // kept clear of the price scale  // one row per window: overlapping windows never cover each other's name
      });
      for (const l of d.lines ?? []) {
        ctx.strokeStyle = l.color; ctx.lineWidth = 1.25; ctx.setLineDash(l.dash ? [5, 4] : []);
        ctx.beginPath();
        let started = false, lx = 0, ly = 0;
        for (const [t, v] of l.points) {
          const x = this.x(t), y = this.y(v);
          if (x === null || y === null) { started = false; continue; }
          if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
          lx = x; ly = y;
        }
        ctx.stroke();
        ctx.setLineDash([]);
        if (started && l.label && lx > 0 && lx <= W) this.tag(ctx, Math.min(lx, W) - 6, ly - 9, l.label, l.color, 'right');  // inside, above its line's end
      }

      // 1. the trade: TP area and SL area from the signal on
      if (d.trade) {
        const t = d.trade;
        const x0 = this.x(t.from), x1 = this.x(t.to), ye = this.y(t.entry), ys = this.y(t.sl), yt = this.y(t.tp);
        if (x0 !== null && x1 !== null && ye !== null && ys !== null && yt !== null) {
          const a = clampX(x0), b = clampX(x1);
          ctx.fillStyle = 'rgba(22,199,132,0.16)'; ctx.fillRect(a, Math.min(ye, yt), b - a, Math.abs(yt - ye));
          ctx.fillStyle = 'rgba(234,57,67,0.16)'; ctx.fillRect(a, Math.min(ye, ys), b - a, Math.abs(ys - ye));
          // the entry ZONE (a band, not one price): the limit is its near edge, the trade is on once price is inside
          const zt = t.zone ? this.y(t.zone[1]) : null, zb = t.zone ? this.y(t.zone[0]) : null;
          if (zt !== null && zb !== null) {
            ctx.fillStyle = 'rgba(212,175,55,0.22)'; ctx.fillRect(a, Math.min(zt, zb), b - a, Math.max(2, Math.abs(zb - zt)));
          }
          ctx.strokeStyle = '#D4AF37'; ctx.lineWidth = 1.5; ctx.setLineDash([]);
          ctx.beginPath(); ctx.moveTo(a, ye); ctx.lineTo(b, ye); ctx.stroke();
          this.tag(ctx, a + 6, ye + (t.dir > 0 ? 10 : -10), t.label, '#D4AF37', 'left');
          // the position tool's numbers: the stop's pips and risk, the target's R:R
          if (t.slPips !== undefined) this.tag(ctx, a + 6, (ye + ys) / 2, `SL ${t.slPips.toFixed(1)} pips${t.risk ? ` · ${t.risk}` : ''}`, '#F87171', 'left');
          if (t.rr !== undefined) this.tag(ctx, a + 6, (ye + yt) / 2, `TP ${t.tpPips !== undefined ? `${t.tpPips.toFixed(1)} pips · ` : ''}1:${t.rr.toFixed(1)} RR`, '#4ADE80', 'left');
        }
      }

      // 2. boxes: order blocks and FVGs, label centred inside
      for (const z of d.boxes) {
        const x0 = this.x(z.from), x1 = this.x(z.to), y0 = this.y(z.top), y1 = this.y(z.bottom);
        if (x0 === null || x1 === null || y0 === null || y1 === null) continue;
        const a = clampX(x0), b = clampX(x1);
        if (b - a < 2) continue;
        const bull = z.dir > 0;
        const ob = z.kind === 'ob';
        ctx.fillStyle = ob ? (bull ? 'rgba(22,199,132,0.22)' : 'rgba(234,57,67,0.24)') : (bull ? 'rgba(22,199,132,0.10)' : 'rgba(234,57,67,0.10)');
        ctx.fillRect(a, y0, b - a, y1 - y0);
        ctx.strokeStyle = bull ? 'rgba(22,199,132,0.75)' : 'rgba(234,57,67,0.75)';
        ctx.lineWidth = 1; ctx.setLineDash(ob ? [] : [4, 3]);
        ctx.strokeRect(a + 0.5, y0 + 0.5, b - a - 1, y1 - y0 - 1);
        ctx.setLineDash([]);
        const h = Math.abs(y1 - y0);
        const cy = (y0 + y1) / 2;
        // the name inside the box near its right end (next to the live candles); above it when the box is too thin
        const label = h >= 13 ? z.label : z.label.replace(' Order Block', ' OB');
        const right = Math.min(b, W - 4) - 8;
        if (h >= 13) {
          this.tag(ctx, right, cy, label, text, 'right');
        } else {
          this.tag(ctx, right, Math.min(y0, y1) - 8, label, bull ? '#4ADE80' : '#F87171', 'right');
        }
      }

      // 3. segments: BOS / CHoCH / IDM / sweep / levels, the label centred above (or below) the line
      for (const s of d.segments) {
        const x0 = this.x(s.from), x1 = this.x(s.to), y = this.y(s.price);
        if (x0 === null || x1 === null || y === null) continue;
        const a = clampX(x0), b = clampX(x1);
        if (b <= 0 || a >= W) continue;
        const color = s.kind === 'bos' || s.kind === 'choch' ? (s.dir > 0 ? BULL : BEAR)
          : s.kind === 'idm' ? '#F59E0B' : s.kind === 'sweep' ? '#A78BFA' : s.kind === 'eq' ? '#D4AF37'
          : s.kind === 'liquidity' ? '#F472B6' : '#A78BFA';
        ctx.strokeStyle = color;
        ctx.lineWidth = s.kind === 'bos' || s.kind === 'choch' ? 1.5 : 1;
        ctx.setLineDash(s.kind === 'bos' ? [] : s.kind === 'choch' ? [2, 3] : s.kind === 'idm' || s.kind === 'eq' ? [5, 4] : [2, 3]);  // BOS solid, CHoCH dotted
        ctx.beginPath(); ctx.moveTo(a, y); ctx.lineTo(b, y); ctx.stroke();
        ctx.setLineDash([]);
        if (!s.label) continue;
        if (s.kind === 'bos' || s.kind === 'choch' || s.kind === 'idm') {
          this.tag(ctx, (a + b) / 2, y + (s.dir > 0 ? -9 : 9), s.label, color, 'center');
        } else {
          this.tag(ctx, b - 4, y - 8, s.label, color, 'right');  // a level: its name at the right end
        }
      }

      // 4. "Liquidity Sweep" at the wick tip
      for (const l of d.labels) {
        const x = this.x(l.time + this.step / 2), y = this.y(l.price);
        if (x === null || y === null || x < 0 || x > W) continue;
        this.tag(ctx, x, y + (l.above ? -12 : 12), l.text, '#C4B5FD', 'center');
        ctx.fillStyle = '#A78BFA';
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
      }
    });
  }

  /** A label with a soft dark halo, readable over candles. It never covers another label: moved by a line, else left out. */
  private tag(ctx: CanvasRenderingContext2D, x: number, y: number, s: string, color: string, align: CanvasTextAlign) {
    const w = ctx.measureText(s).width;
    const x0 = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
    const hits = (yy: number) => this.placed.some(r => x0 < r.x1 && x0 + w > r.x0 && yy - 7 < r.y1 && yy + 7 > r.y0);
    const tries = [y, y - 13, y + 13, y - 26, y + 26];
    const yy = tries.find(v => !hits(v));
    if (yy === undefined) return;
    y = yy;
    this.placed.push({ x0: x0 - 2, x1: x0 + w + 2, y0: y - 7, y1: y + 7 });
    ctx.textAlign = align;
    ctx.lineWidth = 3;
    ctx.strokeStyle = this.theme === 'dark' ? 'rgba(9,11,16,0.85)' : 'rgba(255,255,255,0.9)';
    ctx.strokeText(s, x, y);
    ctx.fillStyle = color;
    ctx.fillText(s, x, y);
  }
}
