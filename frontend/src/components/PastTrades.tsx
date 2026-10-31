import React, { useState } from 'react';
import { History } from 'lucide-react';
import type { PastTrade, StrategyResult } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/** The pair's performance (every closed trade of its strategy) and the list of those trades, newest first:
 * each one ends as TP (closed in profit), SL (closed at a loss) or BE (out at the entry, costs only). */
const SHOWN = 8;
const classOf = (h: PastTrade) => h.result ?? (h.r === null || Math.abs(h.r) <= 0.05 ? 'BE' : h.r > 0 ? 'TP' : 'SL');
const TONE = { TP: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30', SL: 'bg-rose-500/15 text-rose-300 ring-rose-500/30', BE: 'bg-slate-500/15 text-slate-300 ring-slate-500/30' } as const;

export const PastTrades: React.FC<{ result: StrategyResult | null; lang?: Language }> = ({ result, lang = 'en' }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [all, setAll] = useState(false);
  const d = result?.spec.decimals ?? 5;
  const list = (result?.history ?? []).filter(h => h.exitTime && h.id !== result?.setup?.id).slice().reverse();
  const st = result?.historyStats;
  if (!list.length || !st) return null;
  const locale = lang === 'ar' ? 'ar-MA' : lang === 'fr' ? 'fr-FR' : 'en-GB';
  const when = (s: number) => new Date(s * 1000).toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });
  const exitName = (x: string | null) => ({
    SL: t('stop', 'stop', 'الستوب'), TP3: t('target', 'objectif', 'الهدف'), TP2: 'TP2', TP1: 'TP1', BE_EXIT: t('stop at entry', 'stop au point mort', 'الستوب فالدخول'),
    TRAIL_EXIT: t('trailing stop', 'stop suiveur', 'ستوب متحرك'), SIGNAL_EXIT: t('EMA5 exit', 'sortie EMA5', 'خروج EMA5'), TIME_EXIT: t('time limit', 'limite de durée', 'نهاية المدة'),
  } as Record<string, string>)[x ?? ''] ?? (x ?? '—');
  const sign = (v: number | null) => (v === null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}R`);
  const since = st.since ? new Date(st.since * 1000).toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric' }) : '';
  const tiles: { l: string; v: string; tone?: string }[] = [
    { l: t('Win rate', 'Réussite', 'نسبة النجاح'), v: st.winRate === null ? '—' : `${st.winRate}%`, tone: st.winRate !== null && st.winRate >= 50 ? 'text-emerald-300' : 'text-gold-200' },
    { l: t('Total', 'Total', 'المجموع'), v: sign(st.totalR), tone: st.totalR >= 0 ? 'text-emerald-300' : 'text-rose-300' },
    { l: t('Profit factor', 'Profit factor', 'معامل الربح'), v: st.profitFactor === null ? '—' : st.profitFactor.toFixed(2), tone: (st.profitFactor ?? 0) >= 1 ? 'text-emerald-300' : 'text-rose-300' },
    { l: t('Per trade', 'Par trade', 'لكل صفقة'), v: sign(st.avgR) },
    { l: t('Avg win / loss', 'Gain / perte moy.', 'متوسط الربح / الخسارة'), v: `${sign(st.avgWinR)} / ${sign(st.avgLossR)}` },
    { l: t('Max drawdown', 'Drawdown max', 'أكبر تراجع'), v: `−${st.maxDrawdownR.toFixed(2)}R`, tone: 'text-rose-300' },
  ];
  return (
    <section className="mt-4 rounded-[var(--radius-card)] bg-surface border border-line" aria-labelledby="past-title">
      <header className="px-4 pt-4 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="past-title" className="flex items-center gap-2 text-sm font-semibold text-white">
            <span className="icon-tile w-8 h-8 text-gold-400" aria-hidden="true"><History className="w-4 h-4" /></span>{t('Pair performance', 'Performance de la paire', 'أداء الزوج')}
            <span className="text-xs font-normal text-slate-500">· {result?.spec.displaySymbol}</span>
          </h3>
          <span className="text-[11px] text-slate-500">{t(`${st.trades} closed trades since ${since}`, `${st.trades} trades clôturés depuis le ${since}`, `${st.trades} صفقة مسدودة من ${since}`)}</span>
        </div>
        {/* TP / BE / SL split */}
        <div className="mt-3 flex h-2 rounded-full overflow-hidden bg-surface-3" aria-hidden="true">
          <span className="bg-emerald-400" style={{ width: `${(100 * st.tp) / st.trades}%` }} />
          <span className="bg-slate-500" style={{ width: `${(100 * st.be) / st.trades}%` }} />
          <span className="bg-rose-400" style={{ width: `${(100 * st.sl) / st.trades}%` }} />
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs font-mono">
          <span className="text-emerald-300">TP {st.tp}</span><span className="text-slate-400">BE {st.be}</span><span className="text-rose-300">SL {st.sl}</span>
          <span className="text-slate-500">{t('longest losing run', 'pire série de pertes', 'أطول سلسلة خسائر')} {st.maxLosingRun}</span>
        </div>
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
          {tiles.map(x => (
            <div key={x.l} className="rounded-xl border border-line bg-surface-2 px-2.5 py-2 min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 leading-tight">{x.l}</div>
              <div className={`mt-0.5 font-mono text-sm font-semibold tabular-nums truncate ${x.tone ?? 'text-white'}`}>{x.v}</div>
            </div>
          ))}
        </div>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-slate-500 border-y border-line">
              <th className="text-start font-medium px-4 py-2">{t('Entry (UTC)', 'Entrée (UTC)', 'الدخول (UTC)')}</th>
              <th className="text-start font-medium px-2 py-2">{t('Side', 'Sens', 'الاتجاه')}</th>
              <th className="text-end font-medium px-2 py-2">{t('Entry', 'Entrée', 'الدخول')}</th>
              <th className="text-end font-medium px-2 py-2">{t('Exit', 'Sortie', 'الخروج')}</th>
              <th className="text-end font-medium px-2 py-2">{t('Went to', 'Allé jusqu’à', 'وصل حتى')}</th>
              <th className="text-end font-medium px-4 py-2">{t('Result', 'Résultat', 'النتيجة')}</th>
            </tr>
          </thead>
          <tbody>
            {(all ? list : list.slice(0, SHOWN)).map(h => {
              const c = classOf(h);
              return (
                <tr key={h.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2 text-slate-400 whitespace-nowrap">{when(h.signalTime)}</td>
                  <td className={`px-2 py-2 font-semibold ${h.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{h.direction}</td>
                  <td className="px-2 py-2 text-end text-slate-200">{h.entry.toFixed(d)}</td>
                  <td className="px-2 py-2 text-end text-slate-300 whitespace-nowrap">{h.exitPrice !== null ? h.exitPrice.toFixed(d) : '—'} <span className="text-slate-500 font-sans">{exitName(h.exitType)}</span></td>
                  <td className="px-2 py-2 text-end text-slate-400">{h.reachR != null ? `${h.reachR.toFixed(1)}R` : '—'}</td>
                  <td className="px-4 py-2 text-end whitespace-nowrap">
                    <span className={`inline-block min-w-[2.25rem] text-center px-1.5 py-0.5 rounded-md ring-1 ring-inset font-bold text-[10px] ${TONE[c]}`}>{c}</span>
                    <span className={`ms-2 font-semibold ${c === 'TP' ? 'text-emerald-300' : c === 'SL' ? 'text-rose-300' : 'text-slate-300'}`}>{sign(h.r)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {list.length > SHOWN && (
        <button onClick={() => setAll(a => !a)} className="w-full py-2.5 text-xs text-slate-400 hover:text-gold-300 border-t border-line cursor-pointer">
          {all ? t('Show less', 'Afficher moins', 'بان أقل') : t(`Show the last ${list.length}`, `Afficher les ${list.length} derniers`, `بان آخر ${list.length}`)}
        </button>
      )}
      <p className="px-4 pb-3 pt-2 text-[11px] text-slate-500">
        {t('R includes spread and slippage; gold’s breakout closes part at TP1 / TP2, so its R blends those partial exits. Past results, not a promise.',
          'Le R inclut spread et slippage ; le breakout or prend une partie à TP1 / TP2, son R mélange ces sorties partielles. Résultats passés, aucune garantie.',
          'الـ R فيه السبريد والانزلاق؛ اختراق الذهب كيسد جزء ف TP1 / TP2، داكشي علاش الـ R ديالو مخلط. نتائج فايتة، ماشي ضمان.')}
      </p>
    </section>
  );
};
