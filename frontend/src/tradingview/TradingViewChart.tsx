/**
 * TradingView Advanced Charts (Charting Library) for a pair: a clean chart, no analysis drawn on it.
 * The library is licensed by TradingView and not shipped in this repo: it is used when its files are served
 * from /charting_library/ (frontend/public/charting_library, see docs/TRADINGVIEW.md); until then the app's own chart shows.
 */
import React, { useEffect, useRef, useState } from 'react';
import type { InstrumentSymbol } from '../instruments';
import { TF_RES, createDatafeed } from './datafeed';

type Any = any; // the library's typings ship with its files
declare global { interface Window { TradingView?: Any } }

const LIB_PATH = '/charting_library/';
const LIB_FILE = `${LIB_PATH}charting_library.standalone.js`;

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

export const TradingViewChart: React.FC<{
  symbol: InstrumentSymbol; timeframe: string; lang?: string; theme?: 'dark' | 'light'; height?: number; onTimeframeChange?: (tf: string) => void;
}> = ({ symbol, timeframe, lang = 'en', theme = 'dark', height, onTimeframeChange }) => {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<Any>(null);
  const ready = useRef(false);
  const [error, setError] = useState<string | null>(null);

  // the widget: once per pair and theme (the timeframe changes in place)
  useEffect(() => {
    let dead = false;
    loadLibrary().then(() => {
      if (dead || !box.current || !window.TradingView) return;
      const w = new window.TradingView.widget({
        container: box.current, library_path: LIB_PATH, datafeed: createDatafeed(), symbol, interval: TF_RES[timeframe] ?? '60',
        locale: lang === 'ar' ? 'ar' : lang === 'fr' ? 'fr' : 'en', timezone: 'Etc/UTC', theme, autosize: true,
        disabled_features: ['use_localstorage_for_settings', 'header_symbol_search', 'symbol_search_hot_key', 'header_compare'],
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
        w.activeChart().onIntervalChanged().subscribe(null, (res: string) => {
          const tf = Object.keys(TF_RES).find(k => TF_RES[k] === res);
          if (tf && onTimeframeChange) onTimeframeChange(tf);
        });
      });
    }).catch(e => setError(String(e)));
    return () => {
      dead = true;
      ready.current = false;
      try { widget.current?.remove(); } catch { /* already removed */ }
      widget.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, theme, lang]);

  // the timeframe from the app's own buttons
  useEffect(() => {
    const w = widget.current;
    if (w && ready.current && TF_RES[timeframe] && w.activeChart().resolution() !== TF_RES[timeframe]) w.activeChart().setResolution(TF_RES[timeframe], () => {});
  }, [timeframe]);

  if (error) return <div className="p-4 text-xs text-rose-300">{error}</div>;
  return <div ref={box} className="w-full rounded-[var(--radius-card)] overflow-hidden border border-line" style={{ height: height ?? 560 }} />;
};
