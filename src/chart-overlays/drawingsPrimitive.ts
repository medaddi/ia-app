/**
 * Lightweight Charts series primitive that renders strategy drawings on the chart canvas:
 * session shading, zones (FVG / OB / Fib / Asian range), structure lines, liquidity levels,
 * swing labels, sweep / trade markers and the TradingView-style position box.
 * Drawn inside the chart's own render loop, so objects stay glued to candles on scroll and zoom.
 */

import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IChartApi, ISeriesApi, IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';
import type { Drawing, DrawingColor, DrawingLayer } from '../../server/strategies/shared/result';

export type OverlayTheme = 'dark' | 'light';

const PALETTE: Record<OverlayTheme, Record<DrawingColor, string> & { text: string; labelBg: string }> = {
  dark: {
    bull: '#16C784', bear: '#EA3943', gold: '#D6AE57', muted: '#8D96A6', asia: '#8D96A6', london: '#4B85B8', ny: '#E59A4B',
    liquidity: '#C9A04A', entry: '#E3C374', text: '#D8DCE3', labelBg: 'rgba(13,16,22,0.85)',
  },
  light: {
    bull: '#0E9F6E', bear: '#D92D3A', gold: '#A8843A', muted: '#6A7385', asia: '#6A7385', london: '#386A99', ny: '#C46A1A',
    liquidity: '#A8843A', entry: '#A8843A', text: '#222731', labelBg: 'rgba(255,255,255,0.9)',
  },
};

const TF_RANK: Record<string, number> = { M1: 0, M5: 1, M15: 2, H1: 3, H4: 4, D1: 5 };

function rgba(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  private request: (() => void) | null = null;
  private drawings: Drawing[] = [];
  private barTimes: number[] = [];
  private tfSec = 900;
  private chartTf = 'M15';
  private layers: Record<DrawingLayer, boolean> = { sessions: true, levels: true, structure: true, swings: true, liquidity: true, fvg: true, ob: true, fib: true, trade: true };
  private theme: OverlayTheme = 'dark';
  private readonly bgView: IPrimitivePaneView;
  private readonly fgView: IPrimitivePaneView;

  constructor() {
    this.bgView = { zOrder: () => 'bottom', renderer: () => this.makeRenderer('bg') };
    this.fgView = { zOrder: () => 'top', renderer: () => this.makeRenderer('fg') };
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

  update(opts: { drawings: Drawing[]; barTimes: number[]; tfSec: number; chartTf: string; layers: Record<DrawingLayer, boolean>; theme: OverlayTheme }) {
    this.drawings = opts.drawings;
    this.barTimes = opts.barTimes;
    this.tfSec = opts.tfSec;
    this.chartTf = opts.chartTf;
    this.layers = opts.layers;
    this.theme = opts.theme;
    this.request?.();
  }

  /** Drawing under a pane point (lines and markers first, then the smallest box). */
  findDrawingAt(px: number, py: number, paneWidth: number): Drawing | null {
    const items = this.drawings.filter(d => this.visible(d) && d.kind !== 'session');
    let best: { d: Drawing; area: number } | null = null;
    for (const d of items) {
      const x1 = this.x(d.t1);
      if (x1 === null) continue;
      const x2 = d.t2 === null ? paneWidth : this.x(d.t2) ?? paneWidth;
      const ya = this.y(d.p1);
      if (ya === null) continue;
      if (d.kind === 'hline' && px >= x1 - 2 && px <= x2 + 2 && Math.abs(py - ya) <= 4) return d;
      if ((d.kind === 'marker' || d.kind === 'label') && Math.abs(px - x1) <= 8 && Math.abs(py - ya) <= 16) return d;
      if (d.kind === 'box' && d.p2 !== undefined) {
        const yb = this.y(d.p2);
        if (yb === null) continue;
        const top = Math.min(ya, yb), bottom = Math.max(ya, yb);
        if (px >= x1 && px <= x2 && py >= top && py <= bottom) {
          const area = (x2 - x1) * (bottom - top);
          if (!best || area < best.area) best = { d, area };
        }
      }
    }
    return best?.d ?? null;
  }

  /** time → x: snaps to the bar containing t; extrapolates beyond the last bar. */
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
      logical = lo === times.length - 1 ? lo + (t - times[lo]) / this.tfSec : lo;
    }
    const x = ts.logicalToCoordinate(logical as any);
    return x === null ? null : x;
  }

  private y(p: number): number | null {
    const v = this.series?.priceToCoordinate(p);
    return v === null || v === undefined ? null : v;
  }

  /** Lower-timeframe details are hidden on higher-timeframe charts; HTF zones stay visible on LTF charts. */
  private visible(d: Drawing): boolean {
    if (!this.layers[d.layer]) return false;
    if (!d.tf || d.layer === 'trade') return true;
    return (TF_RANK[d.tf] ?? 0) >= (TF_RANK[this.chartTf] ?? 0) - (d.layer === 'structure' || d.layer === 'swings' ? 0 : 1);
  }

  private makeRenderer(pass: 'bg' | 'fg'): IPrimitivePaneRenderer {
    return {
      draw: (target: CanvasRenderingTarget2D) => {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
          const pal = PALETTE[this.theme];
          const W = mediaSize.width;
          const H = mediaSize.height;
          const items = this.drawings.filter(d => this.visible(d));
          ctx.save();
          ctx.font = '600 10px Inter, system-ui, sans-serif';
          ctx.textBaseline = 'middle';
          const rightLabels: { y: number; text: string; color: string }[] = [];

          for (const d of items) {
            const color = pal[d.color];
            const x1 = this.x(d.t1);
            const x2 = d.t2 === null ? W : this.x(d.t2) ?? W;
            if (x1 === null || x2 < 0 || x1 > W) continue;
            const left = Math.max(-1, x1);
            const right = Math.min(W + 1, Math.max(x2, x1 + 2));

            if (pass === 'bg' && d.kind === 'session') {
              ctx.fillStyle = rgba(color, this.theme === 'dark' ? 0.05 : 0.06);
              ctx.fillRect(left, 0, right - left, H);
              // Label only when the session is wide enough to hold it
              if (d.text && ctx.measureText(d.text).width + 8 < right - left) {
                ctx.fillStyle = rgba(color, 0.75);
                ctx.fillText(d.text, left + 4, 10);
              }
              continue;
            }
            if (pass === 'bg' && d.kind === 'box' && d.p2 !== undefined) {
              const ya = this.y(d.p1), yb = this.y(d.p2);
              if (ya === null || yb === null) continue;
              const top = Math.min(ya, yb), h = Math.max(1, Math.abs(yb - ya));
              const isTrade = d.layer === 'trade';
              const alpha = isTrade ? 0.14 : d.faded ? 0.05 : d.layer === 'fib' ? 0.07 : 0.11;
              ctx.fillStyle = rgba(color, alpha);
              ctx.fillRect(left, top, right - left, h);
              if (!isTrade) {
                ctx.strokeStyle = rgba(color, d.faded ? 0.25 : 0.55);
                ctx.lineWidth = 1;
                ctx.setLineDash(d.layer === 'fib' ? [3, 3] : []);
                ctx.strokeRect(left + 0.5, top + 0.5, right - left - 1, h - 1);
                ctx.setLineDash([]);
              }
              if (d.midline) {
                const ym = (ya + yb) / 2;
                ctx.strokeStyle = rgba(color, 0.6);
                ctx.setLineDash([2, 3]);
                ctx.beginPath(); ctx.moveTo(left, ym); ctx.lineTo(right, ym); ctx.stroke();
                ctx.setLineDash([]);
              }
              if (d.text && h >= 11 && right - left > 46) {
                ctx.fillStyle = rgba(color, d.faded ? 0.55 : 0.95);
                // Trade zones label their far edge (TP / SL), other zones their top-left corner
                const ly = isTrade ? (yb < ya ? yb + 8 : yb - 8) : top + Math.min(h / 2, 8);
                ctx.fillText(d.text, left + 5, ly);
              }
              continue;
            }
            if (pass !== 'fg') continue;

            if (d.kind === 'hline') {
              const y = this.y(d.p1);
              if (y === null || y < -2 || y > H + 2) continue;
              ctx.strokeStyle = rgba(color, d.style === 'dotted' ? 0.7 : 0.9);
              ctx.lineWidth = d.layer === 'trade' && d.style === 'solid' ? 1.5 : 1;
              ctx.setLineDash(d.style === 'dashed' ? [5, 3] : d.style === 'dotted' ? [1.5, 3] : []);
              ctx.beginPath(); ctx.moveTo(left, Math.round(y) + 0.5); ctx.lineTo(right, Math.round(y) + 0.5); ctx.stroke();
              ctx.setLineDash([]);
              if (!d.text) continue;
              if (d.t2 === null) rightLabels.push({ y, text: d.text, color });
              else if (right - left > 24) {
                ctx.fillStyle = color;
                ctx.textAlign = 'center';
                ctx.fillText(d.text, (left + right) / 2, y - 7);
                ctx.textAlign = 'left';
              }
              continue;
            }
            if (d.kind === 'label') {
              const y = this.y(d.p1);
              if (y === null) continue;
              ctx.fillStyle = rgba(pal.muted, 0.95);
              ctx.textAlign = 'center';
              ctx.fillText(d.text || '', x1, d.position === 'above' ? y - 9 : y + 9);
              ctx.textAlign = 'left';
              continue;
            }
            if (d.kind === 'marker') {
              const y = this.y(d.p1);
              if (y === null) continue;
              const up = d.position === 'below';
              const my = up ? y + 10 : y - 10;
              ctx.fillStyle = color;
              ctx.beginPath();
              if (d.layer === 'liquidity') {
                // "✕ Sweep" on the wick
                ctx.strokeStyle = color; ctx.lineWidth = 1.5;
                ctx.moveTo(x1 - 3, y - 3); ctx.lineTo(x1 + 3, y + 3); ctx.moveTo(x1 + 3, y - 3); ctx.lineTo(x1 - 3, y + 3); ctx.stroke();
                ctx.textAlign = 'center';
                ctx.fillText(d.text || '', x1, up ? y + 12 : y - 12);
                ctx.textAlign = 'left';
              } else {
                ctx.moveTo(x1, up ? my - 5 : my + 5); ctx.lineTo(x1 - 5, up ? my + 3 : my - 3); ctx.lineTo(x1 + 5, up ? my + 3 : my - 3); ctx.closePath(); ctx.fill();
                if (d.text) {
                  ctx.textAlign = 'center';
                  ctx.fillText(d.text, x1, up ? my + 12 : my - 12);
                  ctx.textAlign = 'left';
                }
              }
            }
          }

          // Right-edge level labels with collision avoidance
          if (pass === 'fg') {
            rightLabels.sort((a, b) => a.y - b.y);
            let lastY = -Infinity;
            for (const l of rightLabels) {
              if (l.y - lastY < 12) continue;
              lastY = l.y;
              const w = ctx.measureText(l.text).width + 8;
              ctx.fillStyle = pal.labelBg;
              ctx.fillRect(W - w - 2, l.y - 7, w, 13);
              ctx.fillStyle = l.color;
              ctx.fillText(l.text, W - w + 2, l.y);
            }
          }
          ctx.restore();
        });
      },
    };
  }
}
