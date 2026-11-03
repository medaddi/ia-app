import React from 'react';
import { Bot, Check, ShieldCheck, X } from 'lucide-react';
import type { Language } from '../types';
import type { PairStrategy } from '../strategyTypes';
import { FSM_TONE, type AgentChartOverlayState } from '../agentOverlay';
import { tr } from './ui';

/** The pair agent's vote and the Multi-Agent Risk Coordinator's decision (backend core/risk_guard.coordinate). */
export interface DeskVote {
  key: 'agent' | 'risk';
  name: string;
  agree: boolean;
  summary: string;
  riskPct?: number;
  checks: { label: string; passed: boolean; detail: string }[];
}
export interface Consensus { approved: boolean; agreed: number; agents: DeskVote[]; summary: string; riskPct?: number }

/** The pair's agent (its state, its strategy steps) and the risk coordinator over it. */
export const AgentDesk: React.FC<{ consensus?: Consensus | null; overlay?: AgentChartOverlayState | null; plan?: PairStrategy | null; hasSetup: boolean; lang?: Language }> =
  ({ consensus, overlay, plan, hasSetup, lang = 'en' }) => {
    const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
    const risk = consensus?.agents.find(a => a.key === 'risk');
    return (
      <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="agent-desk-title">
        <header className="flex items-center justify-between gap-2 mb-3">
          <h3 id="agent-desk-title" className="flex items-center gap-2 text-sm font-semibold text-white">
            <span className="icon-tile icon-tile-gold w-7 h-7" aria-hidden="true"><Bot className="w-4 h-4" /></span>
            {overlay?.agentId ?? plan?.name ?? t('Pair agent', 'Agent de la paire', 'وكيل الزوج')}
          </h3>
          {overlay && <span className={`px-2 py-0.5 rounded-md text-[11px] font-mono font-bold ring-1 ring-inset ${FSM_TONE[overlay.fsmState]}`}>{overlay.fsmState.replace('_', ' ')}</span>}
        </header>

        {overlay && (
          <>
            <p className="text-xs text-slate-300 leading-relaxed">{overlay.statusBannerText.split(' · ').slice(2).join(' · ')}</p>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-mono">
              <span className="px-2 py-1 rounded-lg bg-surface-2 border border-line text-slate-300">{overlay.metrics.sessionName}</span>
              <span className="px-2 py-1 rounded-lg bg-surface-2 border border-line text-slate-300">spread {overlay.metrics.spreadPips.toFixed(1)}p</span>
              <span className="px-2 py-1 rounded-lg bg-surface-2 border border-line text-slate-300">ATR {overlay.metrics.atrPips.toFixed(1)}p</span>
              <span className="px-2 py-1 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-200">{overlay.metrics.confluenceTag}</span>
            </div>
          </>
        )}

        {plan?.steps && (
          <details className="group mt-3">
            <summary className="cursor-pointer list-none text-[11px] text-slate-400 hover:text-slate-200">{t('The agent’s strategy', 'La stratégie de l’agent', 'استراتيجية الوكيل')} · {plan.timeframe} · UTC+1</summary>
            <ol className="mt-1.5 space-y-1 list-decimal list-inside text-[11px] text-slate-300 leading-snug">
              {plan.steps.map((st, k) => <li key={k}>{st}</li>)}
            </ol>
            <p className="mt-1.5 text-[11px] text-slate-500 leading-relaxed">{plan.why}</p>
          </details>
        )}

        {risk && (
          <div className="mt-3 rounded-xl border border-line bg-surface-2/60">
            <div className="flex items-center gap-3 p-2.5">
              <span className="icon-tile w-8 h-8 text-slate-300" aria-hidden="true"><ShieldCheck className="w-4 h-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold text-white">{t('Risk coordinator', 'Coordinateur de risque', 'منسق المخاطرة')}</span>
                <span className="block text-[11px] text-slate-400 truncate">{risk.summary}</span>
              </span>
              {hasSetup && (
                <span className={`shrink-0 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold ring-1 ring-inset ${risk.agree ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' : 'bg-rose-500/10 text-rose-300 ring-rose-500/25'}`}>
                  {risk.agree ? `${risk.riskPct ?? 1} %` : t('blocked', 'bloqué', 'محبوس')}
                </span>
              )}
            </div>
            {risk.checks.length > 0 && (
              <ul className="px-3 pb-3 space-y-1.5">
                {risk.checks.map((c, k) => (
                  <li key={k} className="flex gap-2 text-[11px]">
                    <span className={`mt-0.5 w-3.5 h-3.5 shrink-0 rounded-full flex items-center justify-center ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
                      {c.passed ? <Check className="w-2.5 h-2.5" /> : <X className="w-2.5 h-2.5" />}
                    </span>
                    <span className="min-w-0"><span className="text-slate-200">{c.label}</span> <span className="block text-slate-500 break-words" dir="ltr">{c.detail}</span></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    );
  };
