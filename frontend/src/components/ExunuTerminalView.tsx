import { apiFetch } from '../api';
import { markDataReady } from '../splash';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PriceChart, type ChartLevel, type PriceCandle } from './PriceChart';
import { TeamCard } from './TeamCard';
import { useSmcTeam } from '../smcTeam';
import type { Language } from '../types';
import { useLivePrice } from '../livePrices';
import { TradingViewChart, useChartingLibrary } from '../tradingview/TradingViewChart';
import { PairFlags } from './PairFlags';
import { useDragScroll } from '../useDragScroll';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, PAIR_DECIMALS, TIMEFRAMES, marketOpenNow, type InstrumentSymbol } from '../instruments';

/**
 * The live chart of each pair: its candles, its live price, and its team (SMC S1–S4) with the setup it found drawn on the chart.
 */
interface ExunuTerminalViewProps {
  initialSymbol?: InstrumentSymbol;
  onSymbolChange?: (symbol: InstrumentSymbol) => void; // keeps the app header on the pair shown here
  lang?: string;
}

const PROVIDER_TF: Record<string, string> = { M5: '5M', M15: '15M', M30: '30M', H1: '1H', H4: '4H', D1: '1D', W1: '1W' };
const NO_CANDLES: PriceCandle[] = [];
const LIVE_MS = 5000; // candles every 5 s; the price every second (livePrices.ts)
const DEFAULT_TF = 'H1';

// Each pair remembers the timeframe it was last viewed on
const tfKey = (s: string) => `ld_chart_tf_${s}`;
const savedTf = (s: InstrumentSymbol) => {
  try { const v = localStorage.getItem(tfKey(s)); return v && TIMEFRAMES.includes(v) ? v : DEFAULT_TF; } catch { return DEFAULT_TF; }
};

export const ExunuTerminalView: React.FC<ExunuTerminalViewProps> = ({ initialSymbol = 'XAU/USD', onSymbolChange, lang = 'en' }) => {
  const [symbol, setSymbolState] = useState<InstrumentSymbol>(initialSymbol);
  const [timeframe, setTimeframeState] = useState<string>(() => savedTf(initialSymbol));
  const setSymbol = (s: InstrumentSymbol) => { setSymbolState(s); setTimeframeState(savedTf(s)); onSymbolChange?.(s); };
  const setTimeframe = (tf: string) => { setTimeframeState(tf); try { localStorage.setItem(tfKey(symbol), tf); } catch { /* storage blocked */ } };
  // The app picked another pair (search, dashboard card): follow it
  useEffect(() => { if (initialSymbol !== symbol) { setSymbolState(initialSymbol); setTimeframeState(savedTf(initialSymbol)); } }, [initialSymbol]);

  // The candles are kept under the key of the pair and timeframe they belong to: the chart only gets the pair on screen
  const [candleStore, setCandleStore] = useState<{ key: string; list: PriceCandle[] }>({ key: '', list: [] });
  const [quote, setQuote] = useState<{ time: number; source: string } | null>(null);
  const [updatedAt, setUpdatedAt] = useState(0);
  const tvChart = useChartingLibrary();  // TradingView Advanced Charts when its files are served (docs/TRADINGVIEW.md)
  const pairKey = `${symbol}_${timeframe}`;
  const candles = candleStore.key === pairKey ? candleStore.list : NO_CANDLES;
  const live = useLivePrice(symbol);
  const team = useSmcTeam(symbol);  // THIS pair's team
  const abortRef = useRef<AbortController | null>(null);
  const viewRef = useRef({ symbol, timeframe });
  viewRef.current = { symbol, timeframe };

  const loadCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(sym)}&timeframe=${PROVIDER_TF[tf]}&count=400`, { cache: 'no-store', signal: abortRef.current?.signal });
      const json = await res.json();
      if (viewRef.current.symbol !== sym || viewRef.current.timeframe !== tf) return;  // an answer for the old pair: dropped
      if (json.success && Array.isArray(json.candles)) {
        setCandleStore({ key: `${sym}_${tf}`, list: json.candles });
        setQuote(json.quoteTime ? { time: json.quoteTime, source: json.priceSource || '' } : null);
        setUpdatedAt(Date.now());
        markDataReady();
      }
    } catch {
      // keep the last good candles
    }
  }, []);

  // A switch: the old pair's pending request is aborted before the new pair loads
  useEffect(() => { abortRef.current?.abort(); abortRef.current = new AbortController(); loadCandles(symbol, timeframe); }, [symbol, timeframe]);
  // Live loop: the candles every 5 s, paused while the tab is hidden
  useEffect(() => {
    let busy = false;
    const id = setInterval(async () => {
      if (busy || document.hidden) return;
      busy = true;
      await loadCandles(symbol, timeframe);
      busy = false;
    }, LIVE_MS);
    return () => clearInterval(id);
  }, [symbol, timeframe, loadCandles]);

  const t = (en: string, fr: string, ar: string) => (lang === 'ar' ? ar : lang === 'fr' ? fr : en);
  const pairBar = useDragScroll<HTMLDivElement>();
  const decimals = PAIR_DECIMALS[symbol];
  const lastClose = candles.length ? candles[candles.length - 1].close : null;
  const shown = live?.price ?? lastClose;
  const open = marketOpenNow();
  // What THIS pair's team draws: its analysis (levels, zones, BOS / CHoCH / sweeps) and its setup when one passed the 7 questions
  const mine = team?.success && team.symbol === symbol ? team : null;
  const sig = mine ? mine.signals[mine.signals.length - 1] : undefined;
  const ch = mine?.chart;
  const near = (v: number) => !lastClose || Math.abs(v - lastClose) / lastClose < 0.2;  // never another pair's level
  const levels: ChartLevel[] = (sig ? [{ price: sig.entry, label: `${sig.strategy} ${sig.direction}`, kind: 'entry' as const },
    { price: sig.sl, label: 'SL', kind: 'sl' as const }, { price: sig.tp, label: 'TP', kind: 'tp' as const }] : []).filter(l => near(l.price));
  const drawing = ch ? { boxes: ch.boxes.filter(b => near(b.top) && near(b.bottom)), segments: ch.segments.filter(x => near(x.price)),
    labels: ch.labels.filter(x => near(x.price)), trade: ch.trade && near(ch.trade.entry) ? ch.trade : null } : null;

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-3 glass border rounded-[var(--radius-card)]">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Pairs: each with its flags; scrolls sideways on a phone without a visible scrollbar */}
          <div ref={pairBar} role="tablist" aria-label={t('Instrument', 'Instrument', 'الأداة')}
            className="no-scrollbar select-none cursor-grab flex items-center gap-1 overflow-x-auto max-w-full -mx-1 px-1 [mask-image:linear-gradient(90deg,transparent,#000_12px,#000_calc(100%-16px),transparent)]">
            {INSTRUMENT_SYMBOLS.map(id => (
              <button key={id} role="tab" aria-selected={symbol === id} onClick={() => setSymbol(id)}
                className={`h-10 ps-2 pe-3 shrink-0 inline-flex items-center gap-2 rounded-xl text-xs font-medium cursor-pointer transition-colors ${symbol === id ? 'glass-pill text-gold-100' : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]'}`}>
                <PairFlags symbol={id} size={18} />
                <span className="font-mono">{id}</span><span className="hidden 2xl:inline text-slate-500"> · {INSTRUMENT_LABELS[id]}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className={`w-1.5 h-1.5 rounded-full ${open ? 'bg-emerald-400' : 'bg-slate-500'}`} aria-hidden="true" />
          <span className="text-slate-400">{open ? t('Market open', 'Marché ouvert', 'السوق مفتوح') : t('Market closed', 'Marché fermé', 'السوق مغلق')}</span>
          <span className="text-white font-semibold tabular-nums">{shown != null ? shown.toFixed(decimals) : '—'}</span>
        </div>
      </div>

      {tvChart ? (
        <TradingViewChart symbol={symbol} timeframe={timeframe} lang={lang} onTimeframeChange={setTimeframe} />
      ) : (
        <PriceChart symbol={symbol} candles={candles} decimals={decimals} timeframe={timeframe} timeframes={TIMEFRAMES} onTimeframeChange={setTimeframe}
          livePrice={live?.price ?? null} quote={live?.quoteTime ? { time: live.quoteTime, source: live.source } : quote} updatedAt={updatedAt} lang={lang} levels={levels} drawing={drawing} />
      )}
      <TeamCard key={symbol} team={team} symbol={symbol} decimals={decimals} lang={lang as Language} />
    </div>
  );
};
