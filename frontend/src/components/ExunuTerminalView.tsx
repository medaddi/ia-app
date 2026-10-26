import { apiFetch } from '../api';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, RefreshCw, Activity } from 'lucide-react';
import { SmcChart, SmcChartCandle } from './SmcChart';
import { ExunuActiveSetup } from './ExunuActiveSetup';
import type { ExunuSMCResult } from '../strategyTypes';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, type InstrumentSymbol } from '../instruments';
import type { StrategyResult } from '../strategyTypes';

interface ExunuTerminalViewProps {
  initialSymbol?: InstrumentSymbol;
  onOpenTelegram?: () => void;
  lang?: string;
}

// Review mode: ?asOf=<unix seconds> replays the strategy at a past moment (read-only)
const REVIEW_AS_OF = (() => {
  try { return Number(new URLSearchParams(window.location.search).get('asOf')) || 0; } catch { return 0; }
})();
const asOfParam = REVIEW_AS_OF > 0 ? `&asOf=${REVIEW_AS_OF}` : '';

// Gold: H1 trend breakout · forex: FXAlexG break & retest on H4
const INSTRUMENTS = Object.fromEntries(INSTRUMENT_SYMBOLS.map(s => [s, {
  label: INSTRUMENT_LABELS[s], entryTf: s === 'XAU/USD' ? 'H1' : 'H4', timeframes: ['M15', 'H1', 'H4', 'D1'],
}])) as Record<InstrumentSymbol, { label: string; entryTf: string; timeframes: string[] }>;
const PROVIDER_TF: Record<string, string> = { M5: '5M', M15: '15M', H1: '1H', H4: '4H', D1: '1D' };

export const ExunuTerminalView: React.FC<ExunuTerminalViewProps> = ({ initialSymbol = 'XAU/USD', onOpenTelegram, lang = 'en' }) => {
  const [symbol, setSymbol] = useState<InstrumentSymbol>(initialSymbol);
  const [timeframe, setTimeframe] = useState<string>(INSTRUMENTS[initialSymbol].entryTf);
  const [candles, setCandles] = useState<SmcChartCandle[]>([]);
  const [bundle, setBundle] = useState<ExunuSMCResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const lastSetupRef = useRef<string>('');
  const lastCandleLoadRef = useRef<number>(0);

  const result: StrategyResult | null = bundle?.strategy ?? null;
  const inst = INSTRUMENTS[symbol];

  const loadCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(sym)}&timeframe=${PROVIDER_TF[tf]}&count=400${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.success && Array.isArray(json.candles)) setCandles(json.candles);
      lastCandleLoadRef.current = Date.now();
    } catch {
      // keep the last good candles
    }
  }, []);

  const loadStrategy = useCallback(async (sym: string): Promise<ExunuSMCResult | null> => {
    try {
      const res = await apiFetch(`/api/exunu/setup?symbol=${encodeURIComponent(sym)}${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.success && json.result?.strategy) { setBundle(json.result); return json.result; }
    } catch {
      // next poll retries
    }
    return null;
  }, []);

  const refreshAll = useCallback(async () => {
    setIsLoading(true);
    await Promise.all([loadStrategy(symbol), loadCandles(symbol, timeframe)]);
    setIsLoading(false);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  useEffect(() => { setBundle(null); setCandles([]); refreshAll(); }, [symbol, timeframe]);

  // Live loop: strategy every 3s; candles reload on a new setup or every 30s; the forming candle follows the tick
  useEffect(() => {
    if (REVIEW_AS_OF > 0) return;
    const id = setInterval(async () => {
      const b = await loadStrategy(symbol);
      if (!b) return;
      const key = `${b.strategy.setup?.id ?? ''}|${b.strategy.setup?.lifecycle.state ?? ''}`;
      if (key !== lastSetupRef.current || Date.now() - lastCandleLoadRef.current > 30000) {
        lastSetupRef.current = key;
        loadCandles(symbol, timeframe);
      } else if (b.current_price > 0) {
        setCandles(prev => {
          if (!prev.length) return prev;
          const next = [...prev];
          const l = next[next.length - 1];
          next[next.length - 1] = { ...l, close: b.current_price, high: Math.max(l.high, b.current_price), low: Math.min(l.low, b.current_price) };
          return next;
        });
      }
    }, 3000);
    return () => clearInterval(id);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  const agents = bundle ? [
    { name: 'Structure', summary: bundle.agents.structure_agent.summary, ok: result?.bias.direction !== 'NEUTRAL' },
    { name: 'Liquidity', summary: bundle.agents.liquidity_agent.summary, ok: !!result?.checklist.find(c => (c.key === 'sweep' || c.key === 'zone' || c.key === 'breakout') && c.passed) },
    { name: 'Risk', summary: bundle.agents.risk_agent.summary, ok: !!result?.checklist.find(c => c.key === 'rr' && c.passed) },
    { name: 'CTO', summary: bundle.agents.cto_agent.summary, ok: result?.status === 'SIGNAL' },
  ] : [];

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-3 bg-surface border border-line rounded-[var(--radius-card)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="hidden sm:block">
            <div className="text-sm font-semibold tracking-wide text-white">LiquidityDissection <span className="text-gold-300">Terminal</span></div>
            <div className="text-xs text-slate-500">{result?.strategyName ?? 'Loading…'}</div>
          </div>
          <div role="tablist" aria-label="Instrument" className="flex items-center rounded-lg bg-surface-2 border border-line p-0.5 overflow-x-auto max-w-full">
            {INSTRUMENT_SYMBOLS.map(id => (
              <button key={id} role="tab" aria-selected={symbol === id}
                onClick={() => { setSymbol(id); setTimeframe(INSTRUMENTS[id].entryTf); }}
                className={`h-9 px-3 shrink-0 rounded-md text-xs font-medium transition-colors ${symbol === id ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-100'}`}>
                <span className="font-mono">{id}</span><span className="hidden 2xl:inline text-slate-500"> · {INSTRUMENTS[id].label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {REVIEW_AS_OF > 0 && <span className="px-2 py-1 rounded-md bg-gold-500/15 text-gold-200 text-xs font-medium">Review {new Date(REVIEW_AS_OF * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC</span>}
          <div className="hidden md:flex items-center gap-2 font-mono text-xs">
            <span className={`w-1.5 h-1.5 rounded-full ${result?.market.isOpen ? 'bg-emerald-400' : 'bg-slate-500'}`} aria-hidden="true" />
            <span className="text-slate-400">{result?.market.isOpen ? 'Market open' : 'Market closed'}</span>
            <span className="text-white font-semibold">{result ? result.price.toFixed(result.spec.decimals) : '—'}</span>
          </div>
          {onOpenTelegram && (
            <button onClick={onOpenTelegram} className="h-9 px-3 inline-flex items-center gap-1.5 rounded-lg border border-line text-xs text-slate-200 hover:bg-surface-2">
              <Send className="w-4 h-4 text-gold-400" aria-hidden="true" /><span className="hidden sm:inline">Telegram</span>
            </button>
          )}
          <button onClick={refreshAll} disabled={isLoading} className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-line text-slate-300 hover:bg-surface-2" aria-label="Refresh analysis">
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-gold-400' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 min-w-0">
          <SmcChart symbol={symbol} candles={candles} result={result} timeframe={timeframe} timeframes={[...inst.timeframes]}
            onTimeframeChange={setTimeframe} isLoading={isLoading} onRefresh={refreshAll} lang={lang} />
        </div>
        <div className="lg:col-span-4 min-w-0">
          <ExunuActiveSetup symbol={symbol} result={result} explanation={bundle?.explanation} />
        </div>
      </div>

      {agents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {agents.map((a, i) => (
            <div key={a.name} className="p-3 rounded-xl bg-surface border border-line">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-gold-400" aria-hidden="true" />{i + 1}. {a.name} agent</span>
                <span className={`text-xs font-medium ${a.ok ? 'text-emerald-300' : 'text-slate-500'}`}>{a.ok ? 'Pass' : 'Not met'}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed break-words">{a.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
