import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, type InstrumentSymbol } from '../instruments';
import type { StrategyResult } from '../strategyTypes';
import type { Language } from '../types';
import { PairFlags } from './PairFlags';
import { PastTrades } from './PastTrades';
import { useDragScroll } from '../useDragScroll';
import { tr } from './ui';

/** Pair performance: pick a pair, see its strategy's track record (TP / SL / BE, win rate, R) and its closed trades. */
export const PairPerformanceView: React.FC<{ lang: Language; initialSymbol?: string }> = ({ lang, initialSymbol }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [symbol, setSymbol] = useState<InstrumentSymbol>(
    INSTRUMENT_SYMBOLS.includes(initialSymbol as InstrumentSymbol) ? (initialSymbol as InstrumentSymbol) : 'XAU/USD');
  const [result, setResult] = useState<StrategyResult | null>(null);
  const [loading, setLoading] = useState(true);
  const pairBar = useDragScroll<HTMLDivElement>();

  useEffect(() => {
    let live = true;
    setLoading(true);
    setResult(null);
    apiFetch(`/api/exunu/setup?symbol=${encodeURIComponent(symbol)}`)
      .then(r => r.json())
      .then(j => { if (live && j.success) setResult(j.result?.strategy ?? null); })
      .catch(() => {})
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [symbol]);

  return (
    <div className="space-y-4">
      <div ref={pairBar} role="tablist" aria-label={t('Pair', 'Paire', 'الزوج')} className="no-scrollbar select-none cursor-grab flex gap-2 overflow-x-auto -mx-1 px-1">
        {INSTRUMENT_SYMBOLS.map(s => (
          <button key={s} role="tab" aria-selected={s === symbol} onClick={() => setSymbol(s)}
            className={`h-10 px-3.5 shrink-0 rounded-2xl border text-xs cursor-pointer transition-colors ${s === symbol ? 'border-gold-500/60 bg-gold-500/10 text-gold-200' : 'glass text-slate-300 hover:text-white'}`}>
            <span className="inline-flex items-center gap-2"><PairFlags symbol={s} size={16} /><span className="font-mono font-semibold">{s}</span></span>
            <span className={`ms-1.5 hidden sm:inline ${s === symbol ? 'text-gold-300/80' : 'text-slate-500'}`}>{INSTRUMENT_LABELS[s]}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="h-64 rounded-[var(--radius-card)] glass border animate-pulse" aria-busy="true" />
      ) : result && (result.history ?? []).length ? (
        <PastTrades result={result} lang={lang} />
      ) : (
        <div className="rounded-[var(--radius-card)] glass border p-6 text-sm text-slate-400">
          {t('No closed trade on this pair yet.', 'Aucun trade clôturé sur cette paire pour l’instant.', 'ما كاينة حتى صفقة مسدودة ف هاد الزوج دابا.')}
        </div>
      )}
    </div>
  );
};
