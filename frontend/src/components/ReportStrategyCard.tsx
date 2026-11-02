import React from 'react';
import { BookOpen, ChevronDown } from 'lucide-react';
import type { ReportStrategy } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * The pair's strategy from the strategy report: what the report recommends, the rules the app runs, and the 2-year test
 * that decided whether it sends signals (LIVE) or only runs on the chart (OBSERVATION, the "Report" layer).
 */
export const ReportStrategyCard: React.FC<{ report?: ReportStrategy | null; decimals: number; lang: Language }> = ({ report, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  if (!report) return null;
  const f = (v: number) => v.toFixed(decimals);
  const T = report.test;
  const s = report.setup;
  const hs = report.historyStats;
  return (
    <section aria-labelledby="report-title" className="border-t border-line px-4 py-3">
      <header className="flex items-center gap-2.5">
        <span className={`icon-tile w-8 h-8 ${report.live ? 'icon-tile-gold' : 'text-slate-400'}`} aria-hidden="true"><BookOpen className="w-4 h-4" /></span>
        <div className="min-w-0 flex-1">
          <h4 id="report-title" className="text-xs font-semibold text-white">{t('Report strategy', 'Stratégie du rapport', 'استراتيجية التقرير')}</h4>
          <div className="text-[11px] text-slate-400 truncate" title={report.name}>{report.name.split('·').slice(-1)[0].replace(' (report)', '').trim()}</div>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${report.live ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' : 'bg-slate-500/15 text-slate-300 ring-slate-500/30'}`}>
          {report.live ? t('Live', 'En direct', 'مفعلة') : t('Observation', 'Observation', 'ملاحظة')}
        </span>
      </header>

      <div className="mt-2.5 grid grid-cols-3 gap-1.5 text-center font-mono text-[11px]">
        {[[t('Trades (2 y)', 'Trades (2 ans)', 'صفقات'), String(T.trades), 'text-slate-200'],
          [t('Win rate', 'Réussite', 'النجاح'), `${T.winRate}%`, 'text-slate-200'],
          [t('Result', 'Résultat', 'النتيجة'), `${T.totalR >= 0 ? '+' : ''}${T.totalR}R`, T.totalR >= 0 ? 'text-emerald-300' : 'text-rose-300']].map(([k, v, c]) => (
          <div key={k} className="rounded-lg bg-white/[0.02] border border-line py-1.5">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-sans">{k}</div>
            <div className={c}>{v}</div>
          </div>
        ))}
      </div>
      <p className={`mt-2 text-[11px] leading-snug ${report.live ? 'text-emerald-200' : 'text-slate-400'}`}>{T.verdict}</p>

      {!report.live && (
        <div className="mt-2 rounded-xl bg-white/[0.03] border border-line px-3 py-2 text-[11px]">
          {s ? (
            <span className="font-mono">
              <span className={s.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{s.direction}</span>{' '}
              <span className="text-slate-300">{f(s.entry)} · SL {f(s.sl)} · TP {f(s.tp3)}</span>{' '}
              <span className="text-slate-500">· {s.state}{s.r !== null && s.state === 'CLOSED' ? ` ${s.r >= 0 ? '+' : ''}${s.r.toFixed(2)}R` : ''}</span>
            </span>
          ) : <span className="text-slate-400">{report.headline}</span>}
          <div className="mt-1 text-slate-500">{t('No signal: on the chart, layer "Report strategy"', 'Aucun signal : sur le graphique, calque « Stratégie du rapport »', 'بلا إشارة: ف الشارت، طبقة "استراتيجية التقرير"')}</div>
        </div>
      )}

      <details className="group mt-2">
        <summary className="flex items-center gap-1 cursor-pointer list-none text-[11px] text-slate-400 hover:text-slate-200">
          <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
          {t('What the report recommends', 'Ce que recommande le rapport', 'شنو كيقترح التقرير')}
        </summary>
        <p className="mt-1.5 text-[11px] text-slate-300 leading-relaxed">{report.recommendation}</p>
        {report.note && <p className="mt-1 text-[11px] text-gold-300/90 leading-relaxed">{report.note}</p>}
        {hs && !report.live && <p className="mt-1 text-[11px] text-slate-500 font-mono">{t('Replay now', 'Rejoué maintenant', 'المحاكاة دابا')}: {hs.trades} · TP {hs.tp} · SL {hs.sl} · {hs.totalR >= 0 ? '+' : ''}{hs.totalR}R</p>}
      </details>
    </section>
  );
};
