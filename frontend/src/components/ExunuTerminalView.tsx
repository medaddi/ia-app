import { apiFetch } from '../api';
import { markDataReady } from '../splash';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { SmcChart, SmcChartCandle } from './SmcChart';
import { ExunuActiveSetup } from './ExunuActiveSetup';
import { AgentsConsensus, type Consensus } from './AgentsConsensus';
import type { ManagerVote } from './TradeManagement';
import { PairFlags } from './PairFlags';
import { useDragScroll } from '../useDragScroll';
import type { ExunuSMCResult } from '../strategyTypes';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, chartSpec, type ChartSpec, type InstrumentSymbol } from '../instruments';
import type { StrategyResult } from '../strategyTypes';
import type { Language } from '../types';

interface ExunuTerminalViewProps {
  initialSymbol?: InstrumentSymbol;
  onSymbolChange?: (symbol: InstrumentSymbol) => void; // keeps the app header on the pair shown here
  onOpenTelegram?: () => void;
  lang?: string;
}

// Review mode: ?asOf=<unix seconds> replays the strategy at a past moment (read-only)
const REVIEW_AS_OF = (() => {
  try { return Number(new URLSearchParams(window.location.search).get('asOf')) || 0; } catch { return 0; }
})();
const asOfParam = REVIEW_AS_OF > 0 ? `&asOf=${REVIEW_AS_OF}` : '';

// Each pair's chart: its plan's timeframe and EMAs (instruments.ts CHART_SPEC)
const INSTRUMENTS = Object.fromEntries(INSTRUMENT_SYMBOLS.map(s => [s, { label: INSTRUMENT_LABELS[s], ...chartSpec(s) }])) as Record<InstrumentSymbol, ChartSpec & { label: string }>;
const PROVIDER_TF: Record<string, string> = { M5: '5M', M15: '15M', M30: '30M', H1: '1H', H4: '4H', D1: '1D', W1: '1W' };
const LIVE_MS = 1000; // analysis, candles and price every second (the feed itself updates about once a second)

// Each pair remembers the timeframe it was last viewed on (default: the strategy's decision timeframe)
const tfKey = (s: string) => `ld_chart_tf_${s}`;
const savedTf = (s: InstrumentSymbol) => {
  try { const v = localStorage.getItem(tfKey(s)); return v && INSTRUMENTS[s].timeframes.includes(v) ? v : INSTRUMENTS[s].entryTf; } catch { return INSTRUMENTS[s].entryTf; }
};

export const ExunuTerminalView: React.FC<ExunuTerminalViewProps> = ({ initialSymbol = 'XAU/USD', onSymbolChange, onOpenTelegram, lang = 'en' }) => {
  const [symbol, setSymbolState] = useState<InstrumentSymbol>(initialSymbol);
  const [timeframe, setTimeframeState] = useState<string>(() => savedTf(initialSymbol));
  const setSymbol = (s: InstrumentSymbol) => { setSymbolState(s); setTimeframeState(savedTf(s)); onSymbolChange?.(s); };
  const setTimeframe = (tf: string) => { setTimeframeState(tf); try { localStorage.setItem(tfKey(symbol), tf); } catch { /* storage blocked */ } };
  // The app picked another pair (search, dashboard card): follow it
  useEffect(() => { if (initialSymbol !== symbol) { setSymbolState(initialSymbol); setTimeframeState(savedTf(initialSymbol)); } }, [initialSymbol]);
  const [candles, setCandles] = useState<SmcChartCandle[]>([]);
  const [bundle, setBundle] = useState<ExunuSMCResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number>(0);

  const result: StrategyResult | null = bundle?.strategy ?? null;
  const inst = INSTRUMENTS[symbol];
  // The pair / timeframe on screen: an answer that arrives after a switch belongs to the old pair and is dropped
  // (otherwise GBP/USD could show EUR/USD's last price and candles for a moment)
  const viewRef = useRef({ symbol, timeframe });
  viewRef.current = { symbol, timeframe };

  const loadCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(sym)}&timeframe=${PROVIDER_TF[tf]}&count=400${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (viewRef.current.symbol !== sym || viewRef.current.timeframe !== tf) return;
      if (json.success && Array.isArray(json.candles)) setCandles(json.candles);
    } catch {
      // keep the last good candles
    }
  }, []);

  const loadStrategy = useCallback(async (sym: string): Promise<ExunuSMCResult | null> => {
    try {
      const res = await apiFetch(`/api/exunu/setup?symbol=${encodeURIComponent(sym)}${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (viewRef.current.symbol !== sym) return null;
      if (json.success && json.result?.strategy) { setBundle(json.result); markDataReady(); return json.result; }
    } catch {
      // next poll retries
    }
    return null;
  }, []);

  const refreshAll = useCallback(async () => {
    setIsLoading(true);
    const [b] = await Promise.all([loadStrategy(symbol), loadCandles(symbol, timeframe)]);
    if (b) setUpdatedAt(Date.now());
    setIsLoading(false);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  useEffect(() => { setBundle(null); setCandles([]); refreshAll(); }, [symbol, timeframe]);

  // Live loop: every second the analysis and the candles (with the forming one) are reloaded together,
  // so the drawings, the checklist and the chart always come from the same moment. Paused while the tab is hidden.
  useEffect(() => {
    if (REVIEW_AS_OF > 0) return;
    let busy = false;
    const id = setInterval(async () => {
      if (busy || document.hidden) return;
      busy = true;
      const [b] = await Promise.all([loadStrategy(symbol), loadCandles(symbol, timeframe)]);
      if (b) setUpdatedAt(Date.now());
      busy = false;
    }, LIVE_MS);
    return () => clearInterval(id);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  const t = (en: string, fr: string, ar: string) => (lang === 'ar' ? ar : lang === 'fr' ? fr : en);
  const pairBar = useDragScroll<HTMLDivElement>();

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-3 glass border rounded-[var(--radius-card)]">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Pairs: each with its flags; scrolls sideways on a phone without a visible scrollbar */}
          <div ref={pairBar} role="tablist" aria-label={t('Instrument', 'Instrument', 'الأداة')}
            className="no-scrollbar select-none cursor-grab flex items-center gap-1 overflow-x-auto max-w-full -mx-1 px-1 [mask-image:linear-gradient(90deg,transparent,#000_12px,#000_calc(100%-16px),transparent)]">
            {INSTRUMENT_SYMBOLS.map(id => (
              <button key={id} role="tab" aria-selected={symbol === id}
                onClick={() => setSymbol(id)}
                className={`h-10 ps-2 pe-3 shrink-0 inline-flex items-center gap-2 rounded-xl text-xs font-medium cursor-pointer transition-colors ${symbol === id ? 'glass-pill text-gold-100' : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]'}`}>
                <PairFlags symbol={id} size={18} />
                <span className="font-mono">{id}</span><span className="hidden 2xl:inline text-slate-500"> · {INSTRUMENTS[id].label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {REVIEW_AS_OF > 0 && <span className="px-2 py-1 rounded-md bg-gold-500/15 text-gold-200 text-xs font-medium">Review {new Date(REVIEW_AS_OF * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC</span>}
          <div className="hidden md:flex items-center gap-2 font-mono text-xs">
            <span className={`w-1.5 h-1.5 rounded-full ${result?.market.isOpen ? 'bg-emerald-400' : 'bg-slate-500'}`} aria-hidden="true" />
            <span className="text-slate-400">{result?.market.isOpen ? t('Market open', 'Marché ouvert', 'السوق مفتوح') : t('Market closed', 'Marché fermé', 'السوق مغلق')}</span>
            <span className="text-white font-semibold tabular-nums">{result ? result.price.toFixed(result.spec.decimals) : '—'}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 min-w-0">
          <SmcChart symbol={symbol} candles={candles} result={result} timeframe={timeframe} timeframes={inst.timeframes} entryTf={inst.entryTf}
            emas={inst.emas} emaNote={inst.emaNote} updatedAt={REVIEW_AS_OF > 0 ? 0 : updatedAt}
            onTimeframeChange={setTimeframe} isLoading={isLoading} onRefresh={refreshAll} lang={lang} />
          {(bundle as any)?.consensus && (
            <AgentsConsensus consensus={(bundle as any).consensus as Consensus} hasSetup={!!result?.setup} manager={(bundle as any)?.management as ManagerVote | null} lang={lang as Language} />
          )}
        </div>
        <div className="lg:col-span-4 min-w-0 lg:sticky lg:top-0 lg:self-start">
          <ExunuActiveSetup symbol={symbol} result={result} explanation={bundle?.explanation} manager={(bundle as any)?.management as ManagerVote | null} lang={lang} />
        </div>
      </div>

    </div>
  );
};
