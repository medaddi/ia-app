import React from 'react';
import { ArrowDownRight, ArrowUpRight, Check, PenLine, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { AnalysisDrawing } from '../analysisDrawing';

export interface Trigger {
  family: 'plan' | 'smc'; id: string; name: string; dir: 'BUY' | 'SELL'; trigger: string; order: string; level: number; entry: number; sl: number; tp: number;
  rr: number; distPips: number; blockers: string[]; ready: boolean; weight: number; note?: string; maxHours: number;
  test: { kind: string; trades: number; winRate: number; totalR: number };
}
interface Side { side: 'BUY' | 'SELL'; main: Trigger | null; others: Trigger[]; context: { label: string; ok: boolean }[]; supporters: number; score: number; draw?: AnalysisDrawing }
export interface Scenarios { buy: Side; sell: Side; buyPct: number; sellPct: number; bias: 'BUY' | 'SELL' | 'NEUTRAL'; compare: Trigger[]; bothDraw?: AnalysisDrawing }

const signed = (v: number) => `${v >= 0 ? '+' : ''}${v}`;

/**
 * The two scenarios of the Analyse button (backend analysis/scenarios.py): what would make the pair a BUY and what
 * would make it a SELL now, each from the strongest strategy waiting on that side, drawn on the chart; and every
 * strategy compared in one table.
 */
export const ScenarioPanel: React.FC<{ sc: Scenarios; decimals: number; lang: Language; onDraw: (d: AnalysisDrawing) => void }> = ({ sc, decimals, lang, onDraw }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const f = (v: number) => v.toFixed(decimals);
  const card = (s: Side) => {
    const buy = s.side === 'BUY';
    const m = s.main;
    return (
      <div className={`rounded-xl border p-3 ${buy ? 'border-emerald-500/30 bg-emerald-500/[0.05]' : 'border-rose-500/30 bg-rose-500/[0.05]'}`}>
        <div className="flex items-center justify-between gap-2">
          <span className={`inline-flex items-center gap-1 text-sm font-bold ${buy ? 'text-emerald-300' : 'text-rose-300'}`}>
            {buy ? <ArrowUpRight className="w-4 h-4" aria-hidden="true" /> : <ArrowDownRight className="w-4 h-4" aria-hidden="true" />}
            {buy ? t('BUY scenario', 'Scénario BUY', 'سيناريو BUY') : t('SELL scenario', 'Scénario SELL', 'سيناريو SELL')}
          </span>
          <span className="font-mono text-[11px] text-slate-400">{buy ? sc.buyPct : sc.sellPct}%</span>
        </div>
        {m ? (
          <>
            <p className="mt-1.5 text-[12px] text-slate-100 leading-snug">{t('If', 'Si', 'إلا')} {m.trigger}</p>
            <div className="mt-2 grid grid-cols-3 gap-1 text-[11px] font-mono">
              <div className="rounded-md bg-white/[0.04] px-1.5 py-1 text-slate-200">{t('Entry', 'Entrée', 'الدخول')}<br />{f(m.entry)}</div>
              <div className="rounded-md bg-rose-500/10 px-1.5 py-1 text-rose-200">SL<br />{f(m.sl)}</div>
              <div className="rounded-md bg-emerald-500/10 px-1.5 py-1 text-emerald-200">TP 1:{m.rr}<br />{f(m.tp)}</div>
            </div>
            <p className="mt-1.5 text-[10px] text-slate-400 leading-snug">
              {m.family === 'smc' ? `SMC ${m.id}` : m.name} · {m.distPips} pips {t('away', 'de distance', 'بعيد')} · {m.order} · {t('out within', 'sortie sous', 'خروج قبل')} {m.maxHours} h
              {m.note ? ` · ${m.note}` : ''}
            </p>
            {!m.ready && <p className="mt-1 text-[10px] text-amber-200/90">{t('Not yet', 'Pas encore', 'مازال')}: {m.blockers.join(' · ')}</p>}
            <ul className="mt-1.5 space-y-0.5">
              {s.context.map((c, k) => (
                <li key={k} className="flex items-start gap-1 text-[10px] leading-snug">
                  {c.ok ? <Check className="w-3 h-3 mt-px text-emerald-400 shrink-0" aria-hidden="true" /> : <X className="w-3 h-3 mt-px text-slate-500 shrink-0" aria-hidden="true" />}
                  <span className={c.ok ? 'text-slate-300' : 'text-slate-500'}>{c.label}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[10px] text-slate-500">{s.supporters} {t('strategies on this side', 'stratégies de ce côté', 'استراتيجيات ف هاد الجهة')}</span>
              {s.draw && (
                <button type="button" onClick={() => onDraw(s.draw!)} className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-line text-[11px] text-slate-200 hover:bg-white/[0.05] cursor-pointer">
                  <PenLine className="w-3 h-3" aria-hidden="true" />{t('Draw', 'Tracer', 'رسم')}
                </button>
              )}
            </div>
          </>
        ) : <p className="mt-2 text-[11px] text-slate-500">{t('No strategy trades this side now', 'Aucune stratégie ne prend ce côté maintenant', 'حتى استراتيجية ما كتاخد هاد الجهة دابا')}</p>}
      </div>
    );
  };
  return (
    <section className="mt-4">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-white">{t('Scenarios now', 'Scénarios maintenant', 'السيناريوهات دابا')}</h4>
        {sc.bothDraw && (
          <button type="button" onClick={() => onDraw(sc.bothDraw!)} className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-sky-500/40 text-[11px] text-sky-200 hover:bg-sky-500/10 cursor-pointer">
            <PenLine className="w-3 h-3" aria-hidden="true" />{t('Draw both', 'Tracer les deux', 'رسم بجوج')}
          </button>
        )}
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-rose-500/40" role="img" aria-label={`BUY ${sc.buyPct}% / SELL ${sc.sellPct}%`}>
        <div className="h-full bg-emerald-500/80" style={{ width: `${sc.buyPct}%` }} />
      </div>
      <p className="mt-1 text-[11px] text-slate-400">
        {sc.bias === 'NEUTRAL' ? t('No clear side: wait for the first trigger', 'Pas de côté clair : attendre le premier déclencheur', 'حتى جهة واضحة: تسنا أول شرط يتحقق')
          : `${t('Preference', 'Préférence', 'الأفضلية')}: ${sc.bias} (${sc.bias === 'BUY' ? sc.buyPct : sc.sellPct}%) · ${t('the market decides which trigger comes first', 'le marché décide quel déclencheur vient en premier', 'السوق هو لي كيقرر أشمن شرط يجي اللول')}`}
      </p>
      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">{card(sc.buy)}{card(sc.sell)}</div>

      <h4 className="mt-4 text-sm font-semibold text-white">{t('Every strategy compared', 'Comparaison de chaque stratégie', 'مقارنة كل الاستراتيجيات')}</h4>
      <div className="mt-1.5 overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-[11px]">
          <thead className="bg-white/[0.03] text-slate-500">
            <tr>
              <th className="px-2 py-1.5 text-start font-medium">{t('Strategy', 'Stratégie', 'الاستراتيجية')}</th>
              <th className="px-2 py-1.5 text-start font-medium">{t('Side', 'Côté', 'الجهة')}</th>
              <th className="px-2 py-1.5 text-end font-medium">{t('Trigger', 'Déclencheur', 'الشرط')}</th>
              <th className="px-2 py-1.5 text-end font-medium">{t('Away', 'Distance', 'البعد')}</th>
              <th className="px-2 py-1.5 text-end font-medium">{t('Test', 'Test', 'الاختبار')}</th>
              <th className="px-2 py-1.5 text-end font-medium">{t('Weight', 'Poids', 'الوزن')}</th>
            </tr>
          </thead>
          <tbody>
            {sc.compare.map((r, k) => (
              <tr key={k} className="border-t border-line">
                <td className="px-2 py-1.5 text-slate-200"><span className={`me-1 px-1 rounded text-[9px] font-bold ${r.family === 'plan' ? 'bg-gold-500/15 text-gold-200' : 'bg-sky-500/15 text-sky-200'}`}>{r.family === 'plan' ? t('PLAN', 'PLAN', 'خطة') : 'SMC'}</span>{r.family === 'smc' ? r.id : r.name}</td>
                <td className={`px-2 py-1.5 font-bold ${r.dir === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{r.dir}</td>
                <td className="px-2 py-1.5 text-end font-mono text-slate-300">{f(r.level)}</td>
                <td className="px-2 py-1.5 text-end font-mono text-slate-400">{r.distPips}p{r.ready ? '' : ' ⏳'}</td>
                <td className={`px-2 py-1.5 text-end font-mono ${r.test.totalR >= 0 ? 'text-emerald-300/90' : 'text-rose-300/90'}`} title={r.test.kind}>{r.test.trades ? `${r.test.winRate}% ${signed(r.test.totalR)}R` : '—'}</td>
                <td className="px-2 py-1.5 text-end">
                  <span className="inline-block h-1.5 rounded-full bg-gold-400/80 align-middle" style={{ width: `${Math.max(4, Math.min(56, r.weight * 50))}px` }} aria-hidden="true" />
                  <span className="ms-1 font-mono text-slate-400">{r.weight.toFixed(2)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-[10px] text-slate-500 leading-relaxed">
        {t('Weight = the strategy\'s own test × how close price is to its trigger × whether it can fire now (⏳: waits for its hours or filter). Proven plans: 2 years, unseen 40 %. SMC: the last ~2 months of M5. A scenario is a plan, not a signal: it becomes a setup only when its rules confirm.',
          'Poids = le test de la stratégie × la proximité du déclencheur × s’il peut se déclencher maintenant (⏳ : attend ses horaires ou son filtre). Plans prouvés : 2 ans, 40 % jamais vus. SMC : les ~2 derniers mois en M5. Un scénario est un plan, pas un signal : il devient un setup quand ses règles se confirment.',
          'الوزن = الاختبار ديال الاستراتيجية × قرب الثمن من الشرط × واش تقدر تخدم دابا (⏳: كتسنا الوقت ولا الفلتر). الخطط المجربة: 2 سنين، 40% ما شافتهاش. SMC: آخر شهرين ف M5. السيناريو خطة، ماشي إشارة: كيولي سيتاب ملي القواعد ديالو كيتأكدو.')}
      </p>
    </section>
  );
};
