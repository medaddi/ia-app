/**
 * Lightweight Charts series primitive that renders ONE agent's AgentChartOverlayState on its own chart:
 * zones (fill, border, label in the top-right corner, dashed 50 % line), price lines (solid / dashed / dotted, sloped for
 * the RSI divergence) and the live trade projection (entry, SL, TP1, TP2). Markers are the series' native markers.
 * Drawn inside the chart's render loop, so every object stays glued to its candles on scroll and zoom.
 */

import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IChartApi, ISeriesApi, IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';
import type { AgentChartOverlayState, LineCategory, OverlayPriceLine, OverlayZone, ZoneCategory } from '../agentOverlay';

export type OverlayTheme = 'dark' | 'light';
export type OverlayLayer = 'sessions' | 'zones' | 'structure' | 'markers' | 'trade' | 'smc';

export const ZONE_LAYER: Record<ZoneCategory, OverlayLayer> = {
  ASIAN_BOX: 'sessions', LONDON_BOX: 'sessions', FVG_BULL: 'smc', FVG_BEAR: 'smc', OB_BULL: 'smc', OB_BEAR: 'smc',
  OTE_GOLD_ZONE: 'zones', SUPPLY_BAND: 'zones', DEMAND_BAND: 'zones',
};
export const LINE_LAYER: Record<LineCategory, OverlayLayer> = {
  PDH: 'sessions', PDL: 'sessions', SESSION_HIGH: 'sessions', SESSION_LOW: 'sessions', MSS_BREAK: 'structure', EQUILIBRIUM: 'structure',
  DIVERGENCE_LINE: 'structure', BSL: 'smc', SSL: 'smc', BOS: 'smc', CHOCH: 'smc',
};

const BULL = '#16C784', BEAR = '#EA3943', GOLD = '#D4AF37';
const DASH: Record<OverlayPriceLine['lineStyle'], number[]> = { SOLID: [], DASHED: [6, 4], DOTTED: [1.5, 3] };

export class AgentOverlayPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  private request: (() => void) | null = null;
  private state: AgentChartOverlayState | null = null;
  private barTimes: number[] = [];
  private tfSec = 300;
  private layers: Record<OverlayLayer, boolean> = { sessions: true, zones: true, structure: true, markers: true, trade: true, smc: true };
  private theme: OverlayTheme = 'dark';
  private decimals = 5;
  private zoneLabels: { x: number; y: number; text: string; color: string; maxW: number }[] = [];
  private readonly bgView: IPrimitivePaneView;
  private readonly fgView: IPrimitivePaneView;

  constructor() {
    this.bgView = { zOrder: () => 'bottom', renderer: () => this.renderer('bg') };
    this.fgView = { zOrder: () => 'top', renderer: () => this.renderer('fg') };
  }

  attached(p: SeriesAttachedParameter<Time>) {
    this.chart = p.chart as IChartApi;
    this.series = p.series as ISeriesApi<'Candlestick'>;
    this.request = p.requestUpdate;
  }

  detached() {
    this.chart = null;
    this.series = null;
    this.request = null;
  }

  paneViews() {
    return [this.bgView, this.fgView];
  }

  update(o: { state: AgentChartOverlayState | null; barTimes: number[]; tfSec: number; layers: Record<OverlayLayer, boolean>; theme: OverlayTheme; decimals: number }) {
    this.state = o.state;
    this.barTimes = o.barTimes;
    this.tfSec = o.tfSec;
    this.layers = o.layers;
    this.theme = o.theme;
    this.decimals = o.decimals;
    this.request?.();
  }

  private zones(): OverlayZone[] {
    return (this.state?.zones ?? []).filter(z => z.id.startsWith('AN-') || this.layers[ZONE_LAYER[z.category] ?? 'zones']);  // AN-: the Analyse button's setup, always shown
  }

  private lines(): OverlayPriceLine[] {
    return (this.state?.priceLines ?? []).filter(l => l.id.startsWith('AN-') || this.layers[LINE_LAYER[l.category] ?? 'structure']);
  }

  /** The overlay item under a pane point: a line first, then the trade box, then the smallest zone. */
  findAt(px: number, py: number, paneWidth: number): { id: string; label: string } | null {
    for (const l of this.lines()) {
      const x1 = this.x(l.startTime), x2 = this.x(l.endTime) ?? paneWidth;
      const y1 = this.y(l.startPrice), y2 = this.y(l.endPrice);
      if (x1 === null || y1 === null || y2 === null || px < x1 - 3 || px > Math.min(x2, paneWidth) + 3) continue;
      const yy = x2 === x1 ? y1 : y1 + (y2 - y1) * ((px - x1) / (x2 - x1));
      if (Math.abs(py - yy) <= 4) return { id: l.id, label: l.label };
    }
    const tb = this.state?.tradeExecutionBox;
    if (tb && this.layers.trade) {
      const x1 = this.x(tb.entryTime), ya = this.y(tb.stopLoss), yb = this.y(tb.tp2Price);
      if (x1 !== null && ya !== null && yb !== null && px >= x1 && py >= Math.min(ya, yb) && py <= Math.max(ya, yb)) return { id: 'trade', label: 'Trade' };
    }
    let best: { id: string; label: string; area: number } | null = null;
    for (const z of this.zones()) {
      const x1 = this.x(z.startTime), x2 = this.x(z.endTime) ?? paneWidth, ya = this.y(z.topPrice), yb = this.y(z.bottomPrice);
      if (x1 === null || ya === null || yb === null) continue;
      if (px >= x1 && px <= x2 && py >= ya && py <= yb) {
        const area = (x2 - x1) * (yb - ya);
        if (!best || area < best.area) best = { id: z.id, label: z.label, area };
      }
    }
    return best ? { id: best.id, label: best.label } : null;
  }

  /** time → x on the bar grid; extrapolated beyond the last bar (projections into the future). */
  private x(t: number): number | null {
    const times = this.barTimes;
    const ts = this.chart?.timeScale();
    if (!ts || !times.length) return null;
    let logical: number;
    if (t <= times[0]) logical = (t - times[0]) / this.tfSec;
    else {
      let lo = 0, hi = times.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (times[mid] <= t) lo = mid; else hi = mid - 1;
      }
      logical = lo === times.length - 1 ? lo + (t - times[lo]) / this.tfSec : lo + (t - times[lo]) / Math.max(1, times[lo + 1] - times[lo]);
    }
    // the library maps whole bar positions only: a time between two bars is placed between their coordinates
    const k = Math.floor(logical);
    const c0 = ts.logicalToCoordinate(k as any);
    if (logical === k || c0 === null) return c0;
    const c1 = ts.logicalToCoordinate((k + 1) as any);
    return c1 === null ? c0 : c0 + (c1 - c0) * (logical - k);
  }

  private y(p: number): number | null {
    const v = this.series?.priceToCoordinate(p);
    return v === null || v === undefined ? null : v;
  }

  private renderer(pass: 'bg' | 'fg'): IPrimitivePaneRenderer {
    return {
      draw: (target: CanvasRenderingTarget2D) => {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
          const W = mediaSize.width;
          const s = this.state;
          if (!s) return;
          const labelBg = this.theme === 'dark' ? 'rgba(10,12,17,0.82)' : 'rgba(255,255,255,0.88)';
          ctx.save();
          ctx.font = '600 10px Inter, system-ui, sans-serif';
          ctx.textBaseline = 'middle';

          if (pass === 'bg') {
            this.zoneLabels = [];
            for (const z of this.zones()) {
              const x1 = this.x(z.startTime), x2 = this.x(z.endTime) ?? W, ya = this.y(z.topPrice), yb = this.y(z.bottomPrice);
              if (x1 === null || ya === null || yb === null || x2 < 0 || x1 > W) continue;
              const left = Math.max(-1, x1), right = Math.min(W + 1, Math.max(x2, x1 + 3));
              const top = Math.min(ya, yb), h = Math.max(1, Math.abs(yb - ya));
              ctx.globalAlpha = z.isMitigated ? 0.55 : 1;
              ctx.fillStyle = z.fillColor;
              ctx.fillRect(left, top, right - left, h);
              ctx.strokeStyle = z.borderColor;
              ctx.lineWidth = 1;
              ctx.setLineDash(z.category === 'OTE_GOLD_ZONE' ? [4, 3] : []);
              ctx.strokeRect(left + 0.5, top + 0.5, right - left - 1, h - 1);
              ctx.setLineDash([]);
              if (z.midPrice !== undefined) {
                const ym = this.y(z.midPrice);
                if (ym !== null) {
                  ctx.strokeStyle = z.borderColor;
                  ctx.setLineDash(z.category === 'OTE_GOLD_ZONE' ? [1.5, 3] : [5, 3]);
                  ctx.beginPath(); ctx.moveTo(left, Math.round(ym) + 0.5); ctx.lineTo(right, Math.round(ym) + 0.5); ctx.stroke();
                  ctx.setLineDash([]);
                }
              }
              // the label inside the top-right corner (drawn in the fg pass, after the labels that matter more)
              if (z.label && h >= 10) this.zoneLabels.push({ x: right - 5, y: top + Math.min(h / 2, 8), text: z.label, color: z.borderColor, maxW: right - left - 10 });
              ctx.globalAlpha = 1;
            }
            const tb = s.tradeExecutionBox;
            if (tb && this.layers.trade) {
              const x1 = this.x(tb.entryTime);
              const ye = this.y(tb.entryPrice), ys = this.y(tb.stopLoss), y1 = this.y(tb.tp1Price), y2 = this.y(tb.tp2Price);
              if (x1 !== null && ye !== null && ys !== null && y1 !== null && y2 !== null) {
                const left = Math.max(0, x1);
                ctx.fillStyle = 'rgba(234, 57, 67, 0.14)';
                ctx.fillRect(left, Math.min(ye, ys), W - left, Math.abs(ys - ye));
                ctx.fillStyle = 'rgba(22, 199, 132, 0.16)';
                ctx.fillRect(left, Math.min(ye, y1), W - left, Math.abs(y1 - ye));
                ctx.fillStyle = 'rgba(22, 199, 132, 0.08)';
                ctx.fillRect(left, Math.min(y1, y2), W - left, Math.abs(y2 - y1));
              }
            }
            ctx.restore();
            return;
          }

          // fg: price lines with their labels, then the trade projection's levels
          const right: { y: number; text: string; color: string }[] = [];
          const middle: { x: number; y: number; text: string; color: string }[] = [];
          // every label of the frame takes a slot; one that would land on another moves a step up or down, else it waits
          const slots: [number, number, number, number][] = [];
          const free = (x0: number, y0: number, x1: number, y1: number) => !slots.some(([a, b, c, d]) => x0 < c && x1 > a && y0 < d && y1 > b);
          const place = (x0: number, w: number, y: number, h = 13): number | null => {
            for (const dy of [0, -13, 13, -26, 26]) {
              const yy = y + dy;
              if (yy - h / 2 < 0 || yy + h / 2 > mediaSize.height) continue;
              if (free(x0 - 1, yy - h / 2, x0 + w + 1, yy + h / 2)) { slots.push([x0 - 1, yy - h / 2, x0 + w + 1, yy + h / 2]); return yy; }
            }
            return null;
          };
          for (const l of this.lines()) {
            const x1 = this.x(l.startTime), x2 = this.x(l.endTime) ?? W, y1 = this.y(l.startPrice), y2 = this.y(l.endPrice);
            if (x1 === null || y1 === null || y2 === null || x2 < 0 || x1 > W) continue;
            ctx.strokeStyle = l.color;
            ctx.lineWidth = l.category === 'MSS_BREAK' || l.category === 'DIVERGENCE_LINE' ? 1.6 : 1;
            ctx.setLineDash(DASH[l.lineStyle] ?? []);
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(Math.min(x2, W), x2 > W ? y1 + (y2 - y1) * ((W - x1) / (x2 - x1)) : y2); ctx.stroke();
            ctx.setLineDash([]);
            if (!l.label) continue;
            if (l.startPrice === l.endPrice && x2 >= W - 2) right.push({ y: y1, text: l.label, color: l.color });
            else middle.push({ x: (Math.max(0, x1) + Math.min(W, x2)) / 2, y: Math.min(y1, y2) - 8, text: l.label, color: l.color });
          }
          const tb = s.tradeExecutionBox;
          const tradeYs: number[] = [];
          if (tb && this.layers.trade) {
            const x1 = Math.max(0, this.x(tb.entryTime) ?? 0);
            // the levels are on the price axis; the canvas draws the lines and one status tag on the entry row
            const rows: [number, string, number[]][] = [[tb.entryPrice, GOLD, []], [tb.stopLoss, BEAR, []], [tb.tp2Price, BULL, []]];
            if (Math.abs(tb.tp1Price - tb.tp2Price) > 1e-9) rows.push([tb.tp1Price, BULL, [5, 3]]);  // a second target only when there is one
            for (const [p, color, dash] of rows) {
              const y = this.y(p);
              if (y === null) continue;
              tradeYs.push(y);
              ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.setLineDash(dash);
              ctx.beginPath(); ctx.moveTo(x1, Math.round(y) + 0.5); ctx.lineTo(W, Math.round(y) + 0.5); ctx.stroke();
              ctx.setLineDash([]);
            }
            const ye = this.y(tb.entryPrice);
            if (ye !== null) {
              const text = `${tb.direction} ${tb.orderType} · ${tb.status === 'PENDING' ? 'PENDING' : tb.status === 'TP1_HIT_BE' ? 'TP1 · BE' : `${tb.floatingPips >= 0 ? '+' : ''}${tb.floatingPips.toFixed(1)}p`} · 1:${tb.rrRatio.toFixed(1)}`;
              const w = ctx.measureText(text).width + 8;
              const lx = Math.max(2, Math.min(x1 - w - 4, W - w - 2));  // left of the projection, on the candles side
              slots.push([lx - 1, ye - 7, lx + w + 1, ye + 6]);  // the trade's tag first: it never moves
              ctx.fillStyle = labelBg; ctx.fillRect(lx, ye - 7, w, 13);
              ctx.fillStyle = GOLD; ctx.fillText(text, lx + 4, ye);
            }
            for (const ty of tradeYs) slots.push([W - 150, ty - 6, W, ty + 6]);  // the trade levels' rows at the price edge
          }
          // then the price-edge labels (channel, liquidity), then the labels along their lines, then the zones'
          right.sort((a, b) => a.y - b.y);
          for (const l of right) {
            const w = ctx.measureText(l.text).width + 8;
            const yy = place(W - w - 2, w, l.y);
            if (yy === null) continue;
            ctx.fillStyle = labelBg; ctx.fillRect(W - w - 2, yy - 7, w, 13);
            ctx.fillStyle = l.color; ctx.fillText(l.text, W - w + 2, yy);
          }
          for (const l of middle) {
            const w = ctx.measureText(l.text).width;
            const yy = place(l.x - w / 2, w, l.y, 12);
            if (yy === null) continue;
            ctx.fillStyle = l.color; ctx.textAlign = 'center'; ctx.fillText(l.text, l.x, yy); ctx.textAlign = 'left';
          }
          for (const z of this.zoneLabels) {
            const w = ctx.measureText(z.text).width;
            if (w > z.maxW) continue;
            const yy = place(z.x - w, w, z.y, 12);
            if (yy === null) continue;
            ctx.fillStyle = z.color; ctx.textAlign = 'right'; ctx.fillText(z.text, z.x, yy); ctx.textAlign = 'left';
          }
          ctx.restore();
        });
      },
    };
  }
}
