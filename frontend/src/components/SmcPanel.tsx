import React from 'react';
import { Check, PenLine, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { AnalysisDrawing } from '../analysisDrawing';

interface Step { label: string; ok: boolean; detail: string }
interface Stat { setups: number; trades: number; winRate: number; totalR: number; avgR: number }
interface Test extends Stat { days: number; checklist: Stat }
export interface SmcRow {
  id: 'A' | 'B' | 'C' | 'D' | 'E'; name: string; status: 'CONFIRMED' | 'RUNNING' | 'BLOCKED' | 'FORMING' | 'WAITING'; reason: string; steps: Step[]; checklist: Step[]; test: Test;
  setup?: { direction: 'BUY' | 'SELL'; entryType: string; entry: number; sl: number; tp: number; rr: number; since: number; validUntil: number; slPips: number; lots: Record<string, number>; rNow: number };
  last?: { direction: string; at: number; result: string; r: number };
  draw?: AnalysisDrawing | null;
}
export interface SmcAnalysis {
  success: boolean; verdict: string; decimals: number;
  read: { trend: string; lastBreak: { kind: string; dir: string; level: number; at: number } | null; zone: string | null; bsl: number | null; ssl: number | null };
  strategies: SmcRow[]; test: Test; dataNote: string | null;
}

const TONE: Record<SmcRow['status'], string> = {
  CONFIRMED: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30', RUNNING: 'bg-sky-500/15 text-sky-200 ring-sky-500/30',
  BLOCKED: 'bg-rose-500/15 text-rose-200 ring-rose-500/30', FORMING: 'bg-amber-500/15 text-amber-200 ring-amber-500/30', WAITING: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
};
const hm = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const signed = (v: number) => `${v >= 0 ? '+' : ''}${v}`;

const Checks: React.FC<{ items: Step[]; bad: string }> = ({ items, bad }) => (
  <ol className="mt-1 space-y-0.5">
    {items.map((st, k) => (
      <li key={k} className="flex items-start gap-1.5 text-[11px] leading-snug">
        {st.ok ? <Check className="w-3.5 h-3.5 mt-px text-emerald-400 shrink-0" aria-hidden="true" /> : <X className={`w-3.5 h-3.5 mt-px shrink-0 ${bad}`} aria-hidden="true" />}
        <span className={st.ok ? 'text-slate-200' : 'text-slate-500'}>{st.label} <span className="font-mono text-slate-500">· {st.detail}</span></span>
      </li>
    ))}
  </ol>
);

/**
 * The SMC part of the Analyse button (backend analysis/smc_setups.py): the course's five strategies checked
 * mechanically, a setup CONFIRMED only when its rules AND the 7-question master checklist are met.
 */
export const SmcSection: React.FC<{ data: SmcAnalysis; lang: Language; drawnId?: string | null; onDraw: (d: AnalysisDrawing) => void }> = ({ data, lang, drawnId, onDraw }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const d = data.decimals;
  const status = (s: SmcRow['status']) => s === 'CONFIRMED' ? t('CONFIRMED', 'CONFIRMÉ', 'مأكد') : s === 'RUNNING' ? t('RUNNING', 'EN COURS', 'خدام')
    : s === 'BLOCKED' ? t('CHECKLIST: NO', 'CHECKLIST : NON', 'الشيكليست: لا') : s === 'FORMING' ? t('FORMING', 'EN FORMATION', 'كيتكون') : t('WAITING', 'EN ATTENTE', 'كيتسنا');
  return (
    <section className="mt-4">
      <h4 className="text-sm font-semibold text-sky-200">{t('SMC strategies (course rules)', 'Stratégies SMC (règles du cours)', 'استراتيجيات SMC (قواعد الدروس)')}</h4>
      <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px] font-mono">
        <span className={`px-2 py-1 rounded-lg border border-line ${data.read.trend === 'bullish' ? 'text-emerald-300' : data.read.trend === 'bearish' ? 'text-rose-300' : 'text-slate-300'}`}>H1 {data.read.trend}</span>
        {data.read.lastBreak && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">{data.read.lastBreak.kind} {data.read.lastBreak.dir} {data.read.lastBreak.level.toFixed(d)} · {hm(data.read.lastBreak.at)}</span>}
        {data.read.zone && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">{data.read.zone}</span>}
        {data.read.bsl != null && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">BSL {data.read.bsl.toFixed(d)}</span>}
        {data.read.ssl != null && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">SSL {data.read.ssl.toFixed(d)}</span>}
      </div>
      {data.dataNote && <p className="mt-2 text-[11px] text-amber-200/90">{data.dataNote}</p>}
      <ul className="mt-2 space-y-2">
        {data.strategies.map(s => (
          <li key={s.id} className={`rounded-xl border bg-white/[0.02] p-3 ${drawnId === `smc-${s.id}` ? 'border-sky-500/50' : 'border-line'}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-white">{s.id} · {s.name}</span>
              <span className={`shrink-0 px-2 py-0.5 rounded-md text-[11px] font-bold ring-1 ring-inset ${TONE[s.status]}`}>{status(s.status)}</span>
            </div>
            {s.setup && (
              <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-xs font-mono">
                <div className={`rounded-lg px-2 py-1.5 ${s.setup.direction === 'BUY' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-rose-500/10 text-rose-300'}`}>{s.setup.direction} LIMIT {s.setup.entry.toFixed(d)}</div>
                <div className="rounded-lg px-2 py-1.5 bg-rose-500/10 text-rose-200">SL {s.setup.sl.toFixed(d)} <span className="text-slate-500">({s.setup.slPips}p)</span></div>
                <div className="rounded-lg px-2 py-1.5 bg-emerald-500/10 text-emerald-200">TP {s.setup.tp.toFixed(d)} <span className="text-slate-500">(1:{s.setup.rr})</span></div>
                <div className="rounded-lg px-2 py-1.5 bg-white/[0.04] text-slate-300">{t('lot', 'lot', 'لوت')} $1000 · {s.setup.lots['1000$']}</div>
              </div>
            )}
            {s.steps.length > 0 && <Checks items={s.steps} bad="text-slate-500" />}
            {s.checklist.length > 0 && (
              <div className="mt-2 rounded-lg border border-line bg-black/20 p-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{t('Master checklist (7 questions)', 'Checklist (7 questions)', 'الشيكليست (7 أسئلة)')}</p>
                <Checks items={s.checklist} bad="text-rose-400" />
              </div>
            )}
            <p className="mt-1.5 text-[11px] text-slate-400 leading-snug">{s.reason}</p>
            <div className="mt-1 flex items-center justify-between gap-2">
              <p className="text-[10px] text-slate-500 font-mono">
                {t(`last ${s.test.days} days`, `${s.test.days} derniers jours`, `آخر ${s.test.days} يوم`)}: {s.test.trades}{s.test.trades ? ` · ${s.test.winRate}% · ${signed(s.test.totalR)}R` : ''}
                {' · '}{t('with the checklist', 'avec la checklist', 'بالشيكليست')}: {s.test.checklist.trades}{s.test.checklist.trades ? ` · ${signed(s.test.checklist.totalR)}R` : ''}
                {s.last ? ` · ${t('last', 'dernier', 'آخر')} ${s.last.direction} ${s.last.result} ${signed(s.last.r)}R` : ''}
              </p>
              {s.draw && (
                <button type="button" onClick={() => onDraw(s.draw!)} className="shrink-0 inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-sky-500/40 text-[11px] text-sky-200 hover:bg-sky-500/10 cursor-pointer">
                  <PenLine className="w-3 h-3" aria-hidden="true" />{t('Draw on chart', 'Tracer sur le graphique', 'رسم ف الشارت')}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-slate-500 leading-relaxed">
        {t(`SMC rules checked mechanically on closed M5 / H1 candles. This pair's last ${data.test.days} days: ${data.test.trades} trades, ${data.test.winRate}% won, ${signed(data.test.totalR)}R; with the 7 questions ${data.test.checklist.trades} trades, ${signed(data.test.checklist.totalR)}R. Confirmed means every rule is met, not that it wins.`,
          `Règles SMC vérifiées mécaniquement sur les bougies M5 / H1 clôturées. ${data.test.days} derniers jours : ${data.test.trades} trades, ${data.test.winRate} % gagnés, ${signed(data.test.totalR)}R ; avec les 7 questions ${data.test.checklist.trades} trades, ${signed(data.test.checklist.totalR)}R. Confirmé = chaque règle respectée, pas un gain garanti.`,
          `قواعد SMC كتشيكا آليا على شموع M5 / H1 المسدودة. آخر ${data.test.days} يوم: ${data.test.trades} صفقة، ${data.test.winRate}% ربحات، ${signed(data.test.totalR)}R؛ بالشيكليست ${data.test.checklist.trades} صفقة، ${signed(data.test.checklist.totalR)}R. مأكد معناه القواعد تحققات، ماشي ربح مضمون.`)}
      </p>
    </section>
  );
};
