import React, { useState } from 'react';
import { ChevronDown, Layers } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';

const TONE: Record<string, string> = {
  READY_TO_EXECUTE: 'bg-emerald-500/20 text-emerald-200', RUNNING: 'bg-sky-500/15 text-sky-200', BLOCKED: 'bg-rose-500/15 text-rose-200',
  WAITING: 'bg-slate-500/15 text-slate-300', NO_TRADE: 'bg-slate-500/15 text-slate-300',
};

/** The six SMC agents' report of a pair, agent by agent, with the Darija summary (backend analysis/smc_agents.py). */
export const SmcReportCard: React.FC<{ report: any; decimals: number; lang: Language }> = ({ report, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState(false);
  if (!report) return null;
  const { meta, agent1_structure: a1, agent2_liquidity: a2, agent3_pdArrays: a3, agent4_strategy: a4, agent5_riskAndTrade: a5 } = report;
  const f = (v?: number | null) => (typeof v === 'number' ? v.toFixed(decimals) : '—');
  const row = (n: number, title: string, body: React.ReactNode) => (
    <li className="rounded-lg border border-line bg-white/[0.02] px-2.5 py-2">
      <p className="text-[11px] font-semibold text-slate-200"><span className="me-1.5 text-gold-300 font-mono">{n}</span>{title}</p>
      <div className="mt-0.5 text-[11px] text-slate-400 leading-snug">{body}</div>
    </li>
  );
  return (
    <section className="mt-4 rounded-xl border border-sky-500/25 bg-sky-500/[0.03] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold text-sky-200"><Layers className="w-4 h-4" aria-hidden="true" />{t('SMC agents', 'Agents SMC', 'وكلاء SMC')}
          <span className="text-[10px] font-normal text-slate-500">{meta.symbol} · 1h / 15m / 5m</span></h4>
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${TONE[a5.status] ?? TONE.WAITING}`}>{a5.status.replace(/_/g, ' ')}{a5.checklistScore ? ` · ${a5.checklistScore}` : ''}</span>
      </div>
      <p className="mt-2 text-[12px] text-slate-100 leading-relaxed" dir="rtl">{report.summaryDarija}</p>
      {!meta.guard.ok && <p className="mt-1 text-[11px] text-amber-300">{meta.guard.checks.filter((c: any) => !c.ok).map((c: any) => c.label).join(' · ')}</p>}
      <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open} className="mt-2 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer">
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />{open ? t('Hide the agents', 'Masquer les agents', 'خبي الوكلاء') : t('The six agents, one by one', 'Les six agents, un par un', 'الوكلاء الستة واحد بواحد')}
      </button>
      {open && (
        <ol className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {row(0, t('Pair guard', 'Garde de la paire', 'حارس الزوج'), <>{meta.guard.checks.map((c: any) => `${c.ok ? '✓' : '✗'} ${c.label}`).join(' · ')}</>)}
          {row(1, t('Structure', 'Structure', 'الهيكلة'), <>
            H1 <b className="text-slate-200">{a1.htfBias}</b> · M15 {a1.itfBias} · M5 {a1.ltfBias}
            {a1.lastStructuralEvent && <> · {t('last', 'dernier', 'آخر')} {a1.lastStructuralEvent.type} {f(a1.lastStructuralEvent.price)}</>}
            {a1.dealingRange && <> · {t('range', 'range', 'النطاق')} {f(a1.dealingRange.confirmedSwingLow.price)} – {f(a1.dealingRange.confirmedSwingHigh.price)}, EQ {f(a1.dealingRange.equilibrium50)}, <b className="text-slate-200">{a1.dealingRange.currentValuation}</b>, OTE {f(a1.dealingRange.ote.from)}–{f(a1.dealingRange.ote.to)}</>}
            {a1.lastSweep && <> · {a1.lastSweep.side} {t('swept at', 'balayée à', 'تسحبات ف')} {f(a1.lastSweep.price)}</>}
          </>)}
          {row(2, t('Liquidity & IDM', 'Liquidité & IDM', 'السيولة والـ IDM'), <>
            {a2.idm ? <>IDM {f(a2.idm.price)} <b className={a2.idm.status === 'SWEPT' ? 'text-emerald-300' : 'text-amber-300'}>{a2.idm.status}</b></> : t('no clear IDM', 'pas d’IDM clair', 'حتى IDM واضح')}
            {a2.drawOnLiquidity && <> · {t('draw on', 'cible', 'الهدف')} {a2.drawOnLiquidity.label} {f(a2.drawOnLiquidity.price)}</>}
            <br />{a2.liquidityLevels.map((l: any) => `${l.label} ${f(l.price)}${l.swept ? ' ✓' : ''}`).join(' · ')}
            {a2.retailTrapWarning && <><br /><span className="text-amber-300">⚠ {a2.retailTrapWarning}</span></>}
          </>)}
          {row(3, t('PD arrays', 'Zones PD', 'مناطق PD'), <>{a3.zones.length ? a3.zones.map((z: any) => `${z.type.replace(/_/g, ' ').toLowerCase()} ${f(z.bottomPrice)}–${f(z.topPrice)}${z.scoreOutOf4 ? ` (${z.scoreOutOf4}/4)` : ''}`).join(' · ') : t('no zone near price', 'aucune zone proche', 'حتى منطقة قريبة')}</>)}
          {row(4, t('Strategy', 'Stratégie', 'الاستراتيجية'), <>
            <span dir="rtl">{a4.strategyNameDarija}</span> · <b className="text-slate-200">{a4.ltfConfirmationStatus}</b>
            {a4.executionStepsDarija?.length > 0 && <ul className="mt-0.5" dir="rtl">{a4.executionStepsDarija.map((s: string, k: number) => <li key={k}>{s}</li>)}</ul>}
          </>)}
          {row(5, t('Risk & trade', 'Risque & trade', 'المخاطرة والصفقة'), a5.direction ? <>
            {a5.direction} {f(a5.entryPrice)} · SL {f(a5.stopLoss)} ({a5.slPips}p) · TP1 50 % {f(a5.tp1_partial50)} · TP2 {f(a5.tp2_finalRunner)} · 1:{a5.riskRewardRatio}
            <br />BE {t('after the first M5 BOS', 'après le premier BOS M5', 'من بعد أول BOS ف 5M')} ({f(a5.breakevenTriggerPrice)}){a5.lots?.['1000$'] != null ? ` · ${t('lot', 'lot', 'لوت')} $1000 ${a5.lots['1000$']}` : ''}
          </> : t('no trade: RR ≥ 3 and the 7 questions first', 'pas de trade : RR ≥ 3 et les 7 questions d’abord', 'حتى صفقة: RR ≥ 3 والأسئلة 7 قبل'))}
        </ol>
      )}
    </section>
  );
};
