import React from 'react';
import { Check, ChevronDown, Compass, X } from 'lucide-react';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * Agent 4 · Trade management: runs the open trade like a disciplined professional (server side, app/agent/agents.py).
 * The stop and the target never move (the tested plan); it applies the strategy's own exits on time and reads the market
 * around the trade, then says one thing to do. Its EXIT SOON / CANCEL calls also go out on Telegram and to the phones.
 */
export type ManagerVerdict = 'HOLD' | 'CAUTION' | 'EXIT_SOON' | 'WAIT' | 'CANCEL';
export interface ManagerVote {
  key: 'manager';
  verdict: ManagerVerdict;
  action: { en: string; fr: string; ar: string };
  summary: string;
  checks: { label: string; passed: boolean; detail: string }[];
  rNow?: number;
  bestR?: number;
  worstR?: number;
  targetR?: number;
  bars?: number;
}

export const verdictStyle = (v: ManagerVerdict) => ({
  HOLD: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  WAIT: 'bg-slate-500/15 text-slate-200 ring-slate-500/30',
  CAUTION: 'bg-gold-500/15 text-gold-200 ring-gold-500/40',
  EXIT_SOON: 'bg-rose-500/15 text-rose-200 ring-rose-500/40',
  CANCEL: 'bg-rose-500/15 text-rose-200 ring-rose-500/40',
}[v]);

export const verdictLabel = (v: ManagerVerdict, t: (en: string, fr: string, ar: string) => string) => ({
  HOLD: t('Hold', 'Garder', 'خلي'),
  WAIT: t('Wait', 'Attendre', 'تسنى'),
  CAUTION: t('Caution', 'Prudence', 'حذر'),
  EXIT_SOON: t('Exit soon', 'Sortie proche', 'الخروج قريب'),
  CANCEL: t('Cancel', 'Annuler', 'إلغاء'),
}[v]);

const signed = (v?: number) => (v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`);

export const TradeManagement: React.FC<{ manager?: ManagerVote | null; lang: Language }> = ({ manager, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  if (!manager) return null;
  const urgent = manager.verdict === 'EXIT_SOON' || manager.verdict === 'CANCEL';
  const careful = manager.verdict === 'CAUTION';
  return (
    <section aria-labelledby="mgmt-title" className={`mt-3 rounded-2xl border p-3 ${urgent ? 'border-rose-500/40 bg-rose-500/[0.05]' : careful ? 'border-gold-500/40 bg-gold-500/[0.05]' : 'border-line bg-surface/60'}`}>
      <header className="flex items-center gap-2.5">
        <span className={`icon-tile w-8 h-8 ${urgent || careful ? 'icon-tile-gold' : 'text-gold-300'}`} aria-hidden="true"><Compass className="w-4 h-4" /></span>
        <div className="min-w-0 flex-1">
          <h4 id="mgmt-title" className="text-xs font-semibold text-white">{t('Trade management', 'Gestion du trade', 'تسيير الصفقة')}</h4>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('Agent 4', 'Agent 4', 'الوكيل 4')}</div>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${verdictStyle(manager.verdict)}`}>{verdictLabel(manager.verdict, t)}</span>
      </header>

      {/* What to do now */}
      <p className={`mt-2.5 rounded-xl px-3 py-2 text-xs leading-snug ${urgent ? 'bg-rose-500/10 text-rose-100 font-medium' : careful ? 'bg-gold-500/10 text-gold-100 font-medium' : 'bg-white/[0.03] text-slate-200'}`} role="status">
        👉 {manager.action[lang] ?? manager.action.en}
      </p>

      {manager.rNow !== undefined && (
        <div className="mt-2 grid grid-cols-3 gap-1.5 text-center font-mono text-[11px]">
          {[[t('Now', 'Maintenant', 'دابا'), manager.rNow], [t('Best', 'Meilleur', 'أحسن'), manager.bestR], [t('Worst', 'Pire', 'أسوأ'), manager.worstR]].map(([k, v]) => (
            <div key={k as string} className="rounded-lg bg-white/[0.02] border border-line py-1.5">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-sans">{k as string}</div>
              <div className={(v as number) >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{signed(v as number)}</div>
            </div>
          ))}
        </div>
      )}

      <details className="group mt-2">
        <summary className="flex items-center gap-1 cursor-pointer list-none text-[11px] text-slate-400 hover:text-slate-200">
          <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
          {t('What the agent checks', 'Ce que l’agent vérifie', 'شنو كيتحقق الوكيل')} · {manager.checks.filter(c => c.passed).length}/{manager.checks.length}
        </summary>
        <ul className="mt-2 space-y-1.5">
          {manager.checks.map((c, k) => (
            <li key={k} className="flex gap-2 text-[11px]">
              <span className={`mt-0.5 w-3.5 h-3.5 shrink-0 rounded-full flex items-center justify-center ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-gold-500/20 text-gold-200'}`}>
                {c.passed ? <Check className="w-2.5 h-2.5" /> : <X className="w-2.5 h-2.5" />}
              </span>
              <span className="min-w-0"><span className="text-slate-200">{c.label}</span><span className="block text-slate-500 break-words" dir="ltr">{c.detail}</span></span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
};
