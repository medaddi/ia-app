import React from 'react';
import { Check, Radar, ShieldCheck, Workflow, X } from 'lucide-react';
import type { Language } from '../types';
import { tr } from './ui';

/** The three agents' votes on the pair's trade: market analysis, strategy, risk & execution. A trade goes out on 3/3. */
export interface AgentVote {
  key: 'market' | 'strategy' | 'risk';
  name: string;
  agree: boolean;
  summary: string;
  checks: { label: string; passed: boolean; detail: string }[];
  report?: { dailyTrend: string; volatility: string; atrRatio: number; newsAhead: { currency: string; title: string; inMin: number }[] };
}
export interface Consensus { approved: boolean; agreed: number; agents: AgentVote[]; summary: string }

const ICON = { market: Radar, strategy: Workflow, risk: ShieldCheck } as const;

export const AgentsConsensus: React.FC<{ consensus: Consensus; hasSetup: boolean; lang?: Language }> = ({ consensus, hasSetup, lang = 'en' }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const names: Record<string, string> = {
    market: t('Market analysis', 'Analyse du marché', 'تحليل السوق'),
    strategy: t('Strategy', 'Stratégie', 'الاستراتيجية'),
    risk: t('Risk & execution', 'Risque & exécution', 'المخاطرة والتنفيذ'),
  };
  const market = consensus.agents.find(a => a.key === 'market');
  const trendWord = (w?: string) => (w === 'bullish' ? t('bullish', 'haussière', 'صاعد') : w === 'bearish' ? t('bearish', 'baissière', 'هابط') : t('neutral', 'neutre', 'محايد'));
  return (
    <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="agents-title">
      <header className="flex items-center justify-between gap-2 mb-3">
        <h3 id="agents-title" className="text-sm font-semibold text-white">{t('3 agents', '3 agents', '3 وكلاء')}</h3>
        {hasSetup && (
          <span className={`px-2 py-0.5 rounded-md text-[11px] font-mono font-bold ring-1 ring-inset ${consensus.approved ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' : 'bg-rose-500/10 text-rose-300 ring-rose-500/25'}`}>
            {consensus.agreed}/3 {consensus.approved ? t('agree', 'd’accord', 'متفقين') : ''}
          </span>
        )}
      </header>

      {/* The market report, even without a trade */}
      {market?.report && (
        <div className="mb-3 flex flex-wrap gap-1.5 text-[11px] font-mono">
          <span className={`px-2 py-1 rounded-lg border ${market.report.dailyTrend === 'bullish' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : market.report.dailyTrend === 'bearish' ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' : 'bg-surface-2 border-line text-slate-300'}`}>
            D1 {trendWord(market.report.dailyTrend)}
          </span>
          <span className={`px-2 py-1 rounded-lg border ${market.report.volatility === 'spike' ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' : 'bg-surface-2 border-line text-slate-300'}`}>
            {t('volatility', 'volatilité', 'التقلب')} {market.report.volatility} · {market.report.atrRatio}×
          </span>
          {market.report.newsAhead.slice(0, 2).map((n, i) => (
            <span key={i} className={`px-2 py-1 rounded-lg border ${n.inMin <= 60 ? 'bg-gold-500/10 border-gold-500/30 text-gold-200' : 'bg-surface-2 border-line text-slate-400'}`}>{n.currency} {n.title} · {n.inMin} min</span>
          ))}
        </div>
      )}

      <ol className="space-y-2">
        {consensus.agents.map((a, i) => {
          const Icon = ICON[a.key] ?? Radar;
          const vote = hasSetup ? a.agree : null;  // without a trade there is nothing to vote on
          return (
            <li key={a.key}>
              <details className="group rounded-xl border border-line bg-surface-2/60">
                <summary className="flex items-center gap-3 p-2.5 cursor-pointer list-none">
                  <span className={`icon-tile w-8 h-8 ${vote ? 'icon-tile-gold' : 'text-slate-400'}`} aria-hidden="true"><Icon className="w-4 h-4" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-white">{i + 1}. {names[a.key] ?? a.name}</span>
                  </span>
                  {vote !== null && (
                    <span className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center ${vote ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}
                      aria-label={vote ? t('agrees', 'd’accord', 'موافق') : t('objects', 'contre', 'معارض')}>
                      {vote ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                    </span>
                  )}
                </summary>
                {a.checks.length > 0 && (
                  <ul className="px-3 pb-3 space-y-1.5">
                    {a.checks.map((c, k) => (
                      <li key={k} className="flex gap-2 text-[11px]">
                        <span className={`mt-0.5 w-3.5 h-3.5 shrink-0 rounded-full flex items-center justify-center text-[9px] ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>{c.passed ? '✓' : '✕'}</span>
                        <span className="min-w-0"><span className="text-slate-200">{c.label}</span> <span className="block text-slate-500 break-words" dir="ltr">{c.detail}</span></span>
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
