import React, { useState } from 'react';
import { History } from 'lucide-react';
import type { StrategyResult } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/** The strategy's closed trades on this pair, newest first: when, which side, entry → exit, result and how far it went. */
const SHOWN = 8;

export const PastTrades: React.FC<{ result: StrategyResult | null; lang?: Language }> = ({ result, lang = 'en' }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [all, setAll] = useState(false);
  const d = result?.spec.decimals ?? 5;
  const list = (result?.history ?? []).filter(h => h.exitTime && h.id !== result?.setup?.id).slice().reverse();
  if (!list.length) return null;
  const wins = list.filter(h => h.outcome === 'WIN').length, losses = list.filter(h => h.outcome === 'LOSS').length;
  const total = list.reduce((a, h) => a + (h.r ?? 0), 0);
  const when = (s: number) => new Date(s * 1000).toLocaleString(lang === 'ar' ? 'ar-MA' : lang === 'fr' ? 'fr-FR' : 'en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });
  const exitName = (x: string | null) => ({ SL: 'SL', TP3: 'TP', TP2: 'TP2', TP1: 'TP1', SIGNAL_EXIT: 'EMA5', TIME_EXIT: t('time', 'durée', 'الوقت'), BE: 'BE' } as Record<string, string>)[x ?? ''] ?? (x ?? '—');
  return (
    <section className="mt-4 rounded-[var(--radius-card)] bg-surface border border-line" aria-labelledby="past-title">
      <header className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 pb-3">
        <h3 id="past-title" className="flex items-center gap-2 text-sm font-semibold text-white">
          <History className="w-4 h-4 text-gold-400" aria-hidden="true" />{t('Past trades', 'Trades passés', 'الصفقات الفايتة')}
          <span className="text-xs font-normal text-slate-500">· {result?.spec.displaySymbol}</span>
        </h3>
        <span className="font-mono text-xs text-slate-400">
          {list.length} · <span className="text-emerald-400">{wins}W</span> / <span className="text-rose-400">{losses}L</span> · <span className={total >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{total >= 0 ? '+' : ''}{total.toFixed(1)}R</span>
        </span>
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
            {(all ? list : list.slice(0, SHOWN)).map(h => (
              <tr key={h.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-2 text-slate-400 whitespace-nowrap">{when(h.signalTime)}</td>
                <td className={`px-2 py-2 font-semibold ${h.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{h.direction}</td>
                <td className="px-2 py-2 text-end text-slate-200">{h.entry.toFixed(d)}</td>
                <td className="px-2 py-2 text-end text-slate-300 whitespace-nowrap">{h.exitPrice !== null ? h.exitPrice.toFixed(d) : '—'} <span className="text-slate-500">{exitName(h.exitType)}</span></td>
                <td className="px-2 py-2 text-end text-slate-400">{h.reachR != null ? `${h.reachR.toFixed(1)}R` : '—'}</td>
                <td className={`px-4 py-2 text-end font-semibold ${h.outcome === 'WIN' ? 'text-emerald-300' : h.outcome === 'LOSS' ? 'text-rose-300' : 'text-slate-300'}`}>
                  {h.r !== null ? `${h.r > 0 ? '+' : ''}${h.r.toFixed(2)}R` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.length > SHOWN && (
        <button onClick={() => setAll(a => !a)} className="w-full py-2.5 text-xs text-slate-400 hover:text-gold-300 border-t border-line cursor-pointer">
          {all ? t('Show less', 'Afficher moins', 'بان أقل') : t(`Show all ${list.length}`, `Afficher les ${list.length}`, `بان كلهم (${list.length})`)}
        </button>
      )}
    </section>
  );
};
