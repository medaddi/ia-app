/**
 * TradingView Advanced Charts (Charting Library) for a pair, with its agent's analysis drawn as TradingView objects:
 * zones → rectangles, levels → trend lines, signals → arrows, the trade → a long / short position with its stop and
 * target. The library is licensed by TradingView and not shipped in this repo: it is used when its files are served
 * from /charting_library/ (frontend/public/charting_library, see docs/TRADINGVIEW.md); until then the app's own chart shows.
 */
import React, { useEffect, useRef, useState } from 'react';
import type { AgentChartOverlayState } from '../agentOverlay';
import type { InstrumentSymbol } from '../instruments';
import { TF_RES, createDatafeed } from './datafeed';

type Any = any; // the library's typings ship with its files
declare global { interface Window { TradingView?: Any } }

const LIB_PATH = '/charting_library/';
const LIB_FILE = `${LIB_PATH}charting_library.standalone.js`;
const LINE_STYLE: Record<string, number> = { SOLID: 0, DOTTED: 1, DASHED: 2 };

let probe: Promise<boolean> | null = null;
/** Are the library's files served? (a dev server answers index.html for a missing file: the content type tells them apart) */
export function chartingLibraryAvailable(): Promise<boolean> {
  probe ??= fetch(LIB_FILE, { method: 'GET', cache: 'force-cache' })
    .then(r => r.ok && (r.headers.get('content-type') || '').includes('javascript'))
    .catch(() => false);
  return probe;
}

export function useChartingLibrary(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => { chartingLibraryAvailable().then(setOk); }, []);
  return ok;
}

let loading: Promise<void> | null = null;
function loadLibrary(): Promise<void> {
  if (window.TradingView) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = LIB_FILE;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Charting Library not found'));
    document.head.appendChild(s);
  });
  return loading;
}

/** The agent's overlay as TradingView drawings, on a chart whose old drawings were removed first. */
function drawOverlay(chart: Any, ov: AgentChartOverlayState | null, decimals: number): Any[] {
  if (!ov) return [];
  const ids: Any[] = [];
  const add = (p: Promise<Any> | Any) => Promise.resolve(p).then(id => id && ids.push(id)).catch(() => {});
  const locked = { lock: true, disableSelection: true, disableSave: true, disableUndo: true };
  for (const z of ov.zones) {
    add(chart.createMultipointShape([{ time: z.startTime, price: z.topPrice }, { time: z.endTime, price: z.bottomPrice }], {
      shape: 'rectangle', text: z.label, ...locked,
      overrides: { backgroundColor: z.fillColor, color: z.borderColor, fillBackground: true, linewidth: 1, showLabel: true,
        textColor: z.borderColor, transparency: z.isMitigated ? 85 : 70 } }));
    if (z.midPrice != null) {
      add(chart.createMultipointShape([{ time: z.startTime, price: z.midPrice }, { time: z.endTime, price: z.midPrice }], {
        shape: 'trend_line', ...locked, overrides: { linecolor: z.borderColor, linestyle: 2, linewidth: 1 } }));
    }
  }
  for (const l of ov.priceLines) {
    add(chart.createMultipointShape([{ time: l.startTime, price: l.startPrice }, { time: l.endTime, price: l.endPrice }], {
      shape: 'trend_line', text: l.label, ...locked,
      overrides: { linecolor: l.color, linestyle: LINE_STYLE[l.lineStyle] ?? 0, linewidth: 1, showLabel: true, textcolor: l.color,
        horzLabelsAlign: 'right', vertLabelsAlign: 'bottom' } }));
  }
  for (const m of ov.markers) {
    add(chart.createShape({ time: m.time, price: m.price }, {
      shape: m.position === 'aboveBar' ? 'arrow_down' : 'arrow_up', text: m.text, ...locked,
      overrides: { color: m.color, arrowColor: m.color, fontsize: 11 } }));
  }
  const box = ov.tradeExecutionBox;
  if (box) {
    const tick = 10 ** -decimals;
    add(chart.createMultipointShape([{ time: box.entryTime, price: box.entryPrice }], {
      shape: box.direction === 'LONG' ? 'long_position' : 'short_position', ...locked,
      overrides: { profitLevel: Math.round(Math.abs(box.tp2Price - box.entryPrice) / tick), stopLevel: Math.round(Math.abs(box.entryPrice - box.stopLoss) / tick),
        accountSize: 1000, risk: 1, riskDisplayMode: 'percents' } }));
  }
  return ids;
}

export const TradingViewChart: React.FC<{
  symbol: InstrumentSymbol; timeframe: string; overlay: AgentChartOverlayState | null; decimals: number; lang?: string;
  theme?: 'dark' | 'light'; compact?: boolean; height?: number; onTimeframeChange?: (tf: string) => void;
}> = ({ symbol, timeframe, overlay, decimals, lang = 'en', theme = 'dark', compact = false, height, onTimeframeChange }) => {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<Any>(null);
  const ready = useRef(false);
  const drawn = useRef<Any[]>([]);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const [error, setError] = useState<string | null>(null);

  const redraw = () => {
    const w = widget.current;
    if (!w || !ready.current) return;
    const chart = w.activeChart();
    for (const id of drawn.current) { try { chart.removeEntity(id); } catch { /* already gone */ } }
    drawn.current = drawOverlay(chart, overlayRef.current, decimals);
  };

  // the widget: once per pair and theme (the timeframe changes in place)
  useEffect(() => {
    let dead = false;
    loadLibrary().then(() => {
      if (dead || !box.current || !window.TradingView) return;
      const w = new window.TradingView.widget({
        container: box.current, library_path: LIB_PATH, datafeed: createDatafeed(), symbol, interval: TF_RES[timeframe] ?? '60',
        locale: lang === 'ar' ? 'ar' : lang === 'fr' ? 'fr' : 'en', timezone: 'Etc/UTC', theme, autosize: true,
        disabled_features: ['use_localstorage_for_settings', 'header_symbol_search', 'symbol_search_hot_key', 'header_compare',
          ...(compact ? ['left_toolbar', 'header_widget', 'timeframes_toolbar', 'legend_context_menu'] : [])],
        enabled_features: ['hide_left_toolbar_by_default'],
        overrides: { 'paneProperties.background': theme === 'dark' ? '#090B10' : '#FFFFFF', 'paneProperties.backgroundType': 'solid',
          'mainSeriesProperties.candleStyle.upColor': '#16C784', 'mainSeriesProperties.candleStyle.downColor': '#EA3943',
          'mainSeriesProperties.candleStyle.borderUpColor': '#16C784', 'mainSeriesProperties.candleStyle.borderDownColor': '#EA3943',
          'mainSeriesProperties.candleStyle.wickUpColor': '#16C784', 'mainSeriesProperties.candleStyle.wickDownColor': '#EA3943' },
        studies_overrides: {},
      });
      widget.current = w;
      w.onChartReady(() => {
        if (dead) return;
        ready.current = true;
        const chart = w.activeChart();
        chart.createStudy('Moving Average Exponential', false, true, { length: 50 }).catch(() => {});
        chart.createStudy('Moving Average Exponential', false, true, { length: 200 }).catch(() => {});
        chart.onIntervalChanged().subscribe(null, (res: string) => {
          const tf = Object.keys(TF_RES).find(k => TF_RES[k] === res);
          if (tf && onTimeframeChange) onTimeframeChange(tf);
        });
        redraw();
      });
    }).catch(e => setError(String(e)));
    return () => {
      dead = true;
      ready.current = false;
      drawn.current = [];
      try { widget.current?.remove(); } catch { /* already removed */ }
      widget.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, theme, lang, compact]);

  // the timeframe from the app's own buttons
  useEffect(() => {
    const w = widget.current;
    if (w && ready.current && TF_RES[timeframe] && w.activeChart().resolution() !== TF_RES[timeframe]) {
      w.activeChart().setResolution(TF_RES[timeframe], () => redraw());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe]);

  // the agent's drawings follow its overlay
  const sig = overlay ? JSON.stringify([overlay.zones, overlay.priceLines, overlay.markers, overlay.tradeExecutionBox]) : '';
  useEffect(() => { redraw(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [sig]);

  if (error) return <div className="p-4 text-xs text-rose-300">{error}</div>;
  return <div ref={box} className="w-full rounded-[var(--radius-card)] overflow-hidden border border-line" style={{ height: height ?? (compact ? 320 : 560) }} />;
};
