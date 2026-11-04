import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, ScanSearch, X } from 'lucide-react';
import { apiFetch } from '../api';
import { tr } from './ui';
import type { Language } from '../types';

interface TestPart { trades: number; winRate: number; totalR: number }
interface Row {
  id: string; name: string; timeframe: string; family: 'fade' | 'breakout'; targetR: number; maxBars: number; status: 'SETUP' | 'LATE' | 'WAITING';
  reason: string; test: { tuned: TestPart; unseen: TestPart };
  setup?: { direction: 'BUY' | 'SELL'; entry: number; sl: number; tp: number; rr: number; since: number; closeBy: number; rNow: number; slPips: number; lots: Record<string, number> };
  last?: { direction: string; at: number; result: string };
}
interface Analysis {
  success: boolean; error?: string; symbol: string; price: number; priceSource?: string; at: number; marketOpen: boolean; decimals: number;
  read: { trend: string; volatility: string; atrRatio: number; atrPips: number | null; smc: string }; verdict: string; strategies: Row[];
}

const TONE: Record<Row['status'], string> = {
  SETUP: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30', LATE: 'bg-amber-500/15 text-amber-200 ring-amber-500/30',
  WAITING: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
};

/**
 * The "Analyse" button of a pair: one request (backend /api/analyze) that checks every library strategy of the pair on
 * the latest closed candles, and shows the setups that can be taken now, those too late, and what the others wait for.
 */
export const AnalyzeButton: React.FC<{ symbol: string; lang: Language; compact?: boolean }> = ({ symbol, lang, compact = false }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<Analysis | null>(null);
  const [err, setErr] = useState('');

  const run = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setOpen(true);
    setBusy(true);
    setErr('');
    try {
      const res = await apiFetch(`/api/analyze?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || j.detail || `HTTP ${res.status}`);
      setData(j);
    } catch (x) {
      setErr(String((x as Error).message || x));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" onClick={run} onKeyDown={e => e.stopPropagation()}
        className={`inline-flex items-center gap-1.5 rounded-lg bg-gold-500/15 text-gold-200 ring-1 ring-inset ring-gold-500/40 hover:bg-gold-500/25 font-semibold cursor-pointer transition-colors ${compact ? 'h-7 px-2 text-[11px]' : 'h-9 px-3 text-xs'}`}
        aria-label={t(`Analyse ${symbol} now`, `Analyser ${symbol} maintenant`, `حلل ${symbol} دابا`)}>
        <ScanSearch className="w-3.5 h-3.5" aria-hidden="true" />{t('Analyse', 'Analyser', 'حلل')}
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" onClick={() => setOpen(false)} role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="an-title" onClick={e => e.stopPropagation()}
            className="w-full sm:max-w-2xl max-h-[88vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl glass-strong border p-4 sm:p-5">
            <header className="flex items-start justify-between gap-3">
              <div>
                <h3 id="an-title" className="text-base font-semibold text-white">{t('Analysis', 'Analyse', 'التحليل')} · {symbol}</h3>
                {data && <p className="mt-0.5 text-xs text-slate-400">{new Date(data.at * 1000).toLocaleString()} · {t('price', 'prix', 'الثمن')} <span className="font-mono text-slate-200">{data.price.toFixed(data.decimals)}</span>{data.marketOpen ? '' : ` · ${t('market closed', 'marché fermé', 'السوق مسدود')}`}</p>}
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => run()} disabled={busy} className="h-8 px-2.5 rounded-lg border border-line text-xs text-slate-200 hover:bg-white/[0.05] disabled:opacity-50 cursor-pointer">{t('Re-analyse', 'Relancer', 'عاود')}</button>
                <button type="button" onClick={() => setOpen(false)} className="h-8 w-8 flex items-center justify-center rounded-lg border border-line text-slate-300 hover:bg-white/[0.05] cursor-pointer" aria-label={t('Close', 'Fermer', 'سد')}><X className="w-4 h-4" /></button>
              </div>
            </header>

            {busy && !data && <div className="py-10 flex items-center justify-center gap-2 text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin" />{t('Analysing every strategy…', 'Analyse de chaque stratégie…', 'كيحلل كل استراتيجية…')}</div>}
            {err && <p className="mt-4 text-sm text-rose-300">{err}</p>}

            {data && (
              <>
                <div className={`mt-3 rounded-xl border px-3 py-2 text-sm font-semibold ${data.strategies.some(s => s.status === 'SETUP') ? 'border-emerald-500/30 bg-emerald-500/[0.07] text-emerald-200' : 'border-line bg-white/[0.02] text-slate-300'}`}>
                  {data.strategies.some(s => s.status === 'SETUP')
                    ? t(`${data.strategies.filter(s => s.status === 'SETUP').length} setup(s) can be taken now`, `${data.strategies.filter(s => s.status === 'SETUP').length} setup(s) à prendre maintenant`, `${data.strategies.filter(s => s.status === 'SETUP').length} سيتاب يقدر يتاخد دابا`)
                    : t('No setup right now: every strategy is waiting', 'Aucun setup pour l’instant : chaque stratégie attend', 'حتى سيتاب دابا: كل استراتيجية كتسنا')}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-mono">
                  <span className={`px-2 py-1 rounded-lg border border-line ${data.read.trend === 'bullish' ? 'text-emerald-300' : 'text-rose-300'}`}>{t('trend', 'tendance', 'الاتجاه')} {data.read.trend}</span>
                  <span className="px-2 py-1 rounded-lg border border-line text-slate-300">{t('volatility', 'volatilité', 'التقلب')} {data.read.volatility} ({data.read.atrRatio}×)</span>
                  {data.read.atrPips != null && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">ATR {data.read.atrPips} pips</span>}
                  {data.read.smc && <span className="px-2 py-1 rounded-lg border border-sky-500/30 text-sky-200">{data.read.smc}</span>}
                </div>

                <ul className="mt-3 space-y-2">
                  {data.strategies.map(s => (
                    <li key={s.id} className="rounded-xl border border-line bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-white">{s.name} <span className="text-[11px] font-mono text-slate-500">{s.timeframe} · {s.targetR}R</span></span>
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ring-1 ring-inset ${TONE[s.status]}`}>
                          {s.status === 'SETUP' ? t('SETUP', 'SETUP', 'سيتاب') : s.status === 'LATE' ? t('LATE', 'TROP TARD', 'متأخر') : t('WAITING', 'EN ATTENTE', 'كيتسنا')}
                        </span>
                      </div>
                      {s.setup && (
                        <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-xs font-mono">
                          <div className={`rounded-lg px-2 py-1.5 ${s.setup.direction === 'BUY' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-rose-500/10 text-rose-300'}`}>{s.setup.direction} {s.setup.entry.toFixed(data.decimals)}</div>
                          <div className="rounded-lg px-2 py-1.5 bg-rose-500/10 text-rose-200">SL {s.setup.sl.toFixed(data.decimals)} <span className="text-slate-500">({s.setup.slPips}p)</span></div>
                          <div className="rounded-lg px-2 py-1.5 bg-emerald-500/10 text-emerald-200">TP {s.setup.tp.toFixed(data.decimals)} <span className="text-slate-500">(1:{s.setup.rr})</span></div>
                          <div className="rounded-lg px-2 py-1.5 bg-white/[0.04] text-slate-300">{t('lot', 'lot', 'لوت')} $1000 · {s.setup.lots['1000$']}</div>
                        </div>
                      )}
                      <p className="mt-1.5 text-[11px] text-slate-400 leading-snug">{s.reason}</p>
                      <p className="mt-1 text-[10px] text-slate-500 font-mono">
                        {t('2-year test', 'test 2 ans', 'اختبار 2 سنين')}: {t('never seen', 'jamais vu', 'ما شافوش')} {s.test.unseen.trades} · {s.test.unseen.winRate}% · {s.test.unseen.totalR >= 0 ? '+' : ''}{s.test.unseen.totalR}R
                        {s.last ? ` · ${t('last', 'dernier', 'آخر')} ${s.last.direction} ${s.last.result}` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[10px] text-slate-500 leading-relaxed">{t('Each strategy won ≥ 55 % on 2 years of history it was never tuned on. A test is evidence, not a guarantee: set your own risk.',
                  'Chaque stratégie a gagné ≥ 55 % sur 2 ans d’historique jamais vu pendant son réglage. Un test est un indice, pas une garantie : fixez votre risque.',
                  'كل استراتيجية ربحات ≥ 55% ف 2 سنين ما شافتهومش ف الضبط. الاختبار دليل، ماشي ضمانة: حدد المخاطرة ديالك.')}</p>
              </>
            )}
          </section>
        </div>, document.body)}
    </>
  );
};
