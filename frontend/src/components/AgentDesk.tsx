import React from 'react';
import { AlertTriangle, Bot, Check, ClipboardList, ShieldCheck } from 'lucide-react';
import type { Language } from '../types';
import type { PairStrategy, StrategyResult } from '../strategyTypes';
import { FSM_TONE, type AgentChartOverlayState } from '../agentOverlay';
import { tr } from './ui';

/** The pair agent's order and the risk notes that go with it (backend core/risk_guard.coordinate): notes, never a block. */
export interface DeskVote {
  key: 'agent' | 'risk';
  name: string;
  agree: boolean;
  summary: string;
  riskPct?: number;
  checks: { label: string; passed: boolean; detail: string }[];
}
export interface Consensus { approved: boolean; agreed: number; agents: DeskVote[]; summary: string; riskPct?: number }

/** The pair's agent (its state, its strategy steps) and the risk notes of its order: the trader sets the risk. */
export const AgentDesk: React.FC<{ consensus?: Consensus | null; overlay?: AgentChartOverlayState | null; plan?: PairStrategy | null; hasSetup: boolean; lang?: Language;
  running?: StrategyResult['running']; decimals?: number; bare?: boolean }> =
  ({ consensus, overlay, plan, hasSetup, lang = 'en', running = [], decimals = 5, bare = false }) => {
    const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
    const risk = consensus?.agents.find(a => a.key === 'risk');
    const warnings = risk ? risk.checks.filter(c => !c.passed).length : 0;
    return (
      <section className={bare ? '' : 'mt-4 rounded-[var(--radius-card)] glass border p-4'} aria-labelledby="agent-desk-title">
        <header className={`flex items-center justify-between gap-2 mb-3 ${bare ? 'text-xs' : ''}`}>
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

        {plan?.test && (
          <div className="mt-3" aria-label={t('The 2-year test', 'Le test sur 2 ans', 'الاختبار على 2 سنين')}>
            <div className="text-[11px] text-slate-400">{t('Tested on 2 years', 'Testé sur 2 ans', 'مجرب على 2 سنين')}</div>
            <div className="mt-1 grid grid-cols-2 gap-1.5 text-[11px]">
              {([['tuned', t('Tuned (60 %)', 'Réglage (60 %)', 'الضبط (60%)')], ['unseen', t('Never seen (40 %)', 'Jamais vu (40 %)', 'ما شافوش (40%)')]] as const).map(([k, label]) => {
                const x = plan.test![k];
                return (
                  <div key={k} className={`rounded-lg border px-2 py-1.5 ${k === 'unseen' ? 'border-gold-500/30 bg-gold-500/[0.05]' : 'border-line bg-white/[0.02]'}`}>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
                    <div className={`font-mono font-semibold ${x.totalR >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{x.totalR >= 0 ? '+' : ''}{x.totalR}R</div>
                    <div className="font-mono text-slate-400">{x.trades} {t('trades', 'trades', 'صفقة')} · {t('won', 'gagnés', 'ربحات')} {x.winRate}%</div>
                  </div>
                );
              })}
            </div>
            {plan.note && <p className="mt-1.5 text-[11px] leading-snug text-gold-300/90">{plan.note}</p>}
          </div>
        )}

        {/* The trade-management agent: every order of this pair still running, followed to its end */}
        <div className="mt-3 rounded-xl border border-line bg-surface-2/60 p-2.5">
          <div className="flex items-center gap-3">
            <span className="icon-tile w-8 h-8 text-slate-300" aria-hidden="true"><ClipboardList className="w-4 h-4" /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-semibold text-white">{t('Trade manager', 'Gestionnaire de trades', 'مسير الصفقات')}</span>
              <span className="block text-[11px] text-slate-400">{running.length ? t(`${running.length} trade(s) followed to the target, the stop or the time limit`, `${running.length} trade(s) suivi(s) jusqu’à l’objectif, le stop ou la limite de durée`, `${running.length} صفقة متبوعة حتى الهدف، الستوب ولا نهاية المدة`) : t('No trade running', 'Aucun trade en cours', 'حتى صفقة ما خدامة')}</span>
            </span>
          </div>
          {running.length > 0 && (
            <ul className="mt-2 space-y-1 text-[11px] font-mono">
              {running.map(x => (
                <li key={x.id} className="flex flex-wrap gap-x-2 text-slate-300">
                  <span className={x.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{x.direction} {x.entryType}</span>
                  <span>{x.entry.toFixed(decimals)}</span><span className="text-slate-500">SL {x.sl.toFixed(decimals)} · TP1 {x.tp1.toFixed(decimals)} · TP2 {x.tp2.toFixed(decimals)}</span>
                  <span className="text-gold-200">{x.state.replace('_', ' ')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {risk && (
          <div className="mt-3 rounded-xl border border-line bg-surface-2/60">
            <div className="flex items-center gap-3 p-2.5">
              <span className="icon-tile w-8 h-8 text-slate-300" aria-hidden="true"><ShieldCheck className="w-4 h-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold text-white">{t('Risk notes · your own risk', 'Notes de risque · votre risque', 'ملاحظات المخاطرة · المخاطرة ديالك')}</span>
                <span className="block text-[11px] text-slate-400 truncate">{risk.summary}</span>
              </span>
              {hasSetup && (
                <span className={`shrink-0 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold ring-1 ring-inset ${warnings ? 'bg-amber-500/15 text-amber-200 ring-amber-500/30' : 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'}`}>
                  {warnings ? `${warnings} ${t('note(s)', 'note(s)', 'ملاحظة')}` : t('clear', 'RAS', 'واضح')}
                </span>
              )}
            </div>
            {risk.checks.length > 0 && (
              <ul className="px-3 pb-3 space-y-1.5">
                {risk.checks.map((c, k) => (
                  <li key={k} className="flex gap-2 text-[11px]">
                    <span className={`mt-0.5 w-3.5 h-3.5 shrink-0 rounded-full flex items-center justify-center ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'}`}>
                      {c.passed ? <Check className="w-2.5 h-2.5" /> : <AlertTriangle className="w-2.5 h-2.5" />}
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
