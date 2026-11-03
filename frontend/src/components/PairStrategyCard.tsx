import React from 'react';
import { ChevronDown, Compass } from 'lucide-react';
import type { PairStrategy } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * The pair's strategy: what the analysis of the pair found (does it trend or come back), the plan built for it, and the
 * test that decided it (tuned on the first 60 % of 2 years, judged on the last 40 % it never saw). A pair where nothing
 * held up shows its analysis and "no strategy".
 */
export const PairStrategyCard: React.FC<{ plan?: PairStrategy | null; lang: Language }> = ({ plan, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  if (!plan) return null;
  const pr = plan.profile;
  const p = plan.params;
  const character = { trending: t('Trending', 'Tendanciel', 'كيتبع الاتجاه'), reverting: t('Reverting', 'Retour à la moyenne', 'كيرجع'), mixed: t('Mixed', 'Mixte', 'مختلط') }[pr.character];
  const rule = plan.rule === 'channel_breakout'
    ? t(`A close beyond the ${p.channel}-candle high / low in the EMA50 / EMA200 trend → in the breakout's direction`,
        `Clôture au-delà du plus haut / bas de ${p.channel} bougies dans la tendance EMA50 / EMA200 → dans le sens de la cassure`,
        `إغلاق فوق / تحت أعلى / أدنى ${p.channel} شمعة ف اتجاه EMA50 / EMA200 → مع الكسر`)
    : plan.rule === 'channel_fade'
      ? t(`A close beyond the ${p.channel}-candle high / low → faded at the close`, `Clôture au-delà du plus haut / bas de ${p.channel} bougies → prise à contre-sens`,
          `إغلاق فوق / تحت أعلى / أدنى ${p.channel} شمعة → عكسها`)
      : null;
  const filters = [p.hours ? `${String(p.hours[0]).padStart(2, '0')}:00–${String(p.hours[1]).padStart(2, '0')}:00 GMT` : null, p.adxMax ? `ADX < ${p.adxMax}` : null].filter(Boolean).join(' · ');
  const T = plan.test;
  const signed = (v: number) => `${v >= 0 ? '+' : ''}${v}R`;
  return (
    <section aria-labelledby="pair-plan-title" className="border-t border-line px-4 py-3">
      <header className="flex items-center gap-2.5">
        <span className={`icon-tile w-8 h-8 ${plan.live ? 'icon-tile-gold' : 'text-slate-400'}`} aria-hidden="true"><Compass className="w-4 h-4" /></span>
        <div className="min-w-0 flex-1">
          <h4 id="pair-plan-title" className="text-xs font-semibold text-white">{t('Pair strategy', 'Stratégie de la paire', 'استراتيجية الزوج')}</h4>
          <div className="text-[11px] text-slate-400 truncate" title={plan.name}>{plan.live ? plan.name : t('No validated strategy', 'Aucune stratégie validée', 'ما كايناش استراتيجية مجربة')}</div>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${plan.live ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' : 'bg-slate-500/15 text-slate-300 ring-slate-500/30'}`}>
          {plan.live ? t('Live', 'En direct', 'مفعلة') : t('No signals', 'Pas de signaux', 'بلا إشارات')}
        </span>
      </header>

      <div className="mt-2.5 rounded-xl bg-white/[0.03] border border-line px-3 py-2 text-[11px]">
        <div className="flex items-center justify-between gap-2">
          <span className="text-slate-500">{t('Analysis', 'Analyse', 'التحليل')}</span>
          <span className={`font-semibold ${pr.character === 'trending' ? 'text-sky-300' : pr.character === 'reverting' ? 'text-violet-300' : 'text-slate-300'}`}>{character}</span>
        </div>
        <div className="mt-1 text-slate-400 leading-snug">
          {t(`After a close beyond its 20-candle channel (${pr.tf}), price went on 2 ATR ${pr.follow}% of the time and came back ${pr.fade}% (break-even 33%).`,
             `Après une clôture hors de son canal de 20 bougies (${pr.tf}), le prix a continué de 2 ATR ${pr.follow} % du temps et est revenu ${pr.fade} % (seuil 33 %).`,
             `من بعد إغلاق برا قناة 20 شمعة (${pr.tf})، الثمن كمل 2 ATR ف ${pr.follow}% ورجع ف ${pr.fade}% (العتبة 33%).`)}
        </div>
        <div className="mt-1 text-slate-500">{t('Most active', 'Plus actif', 'أنشط وقت')}: {pr.activeHours}</div>
      </div>

      {plan.live && rule && (
        <div className="mt-2 text-[11px] leading-snug">
          <div className="text-slate-200">{rule}</div>
          <div className="mt-1 font-mono text-slate-400">
            {plan.timeframe}{filters ? ` · ${filters}` : ''} · SL {p.slAtr} × ATR · TP {plan.targetR}R · {t(`max ${plan.maxBars} candles`, `${plan.maxBars} bougies max`, `${plan.maxBars} شمعة ماكس`)}
          </div>
        </div>
      )}

      {T && (
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 text-[11px]">
          {([['tuned', t('Tuned (60 %)', 'Réglage (60 %)', 'الضبط (60%)')], ['unseen', t('Unseen (40 %)', 'Jamais vu (40 %)', 'ما شافوش (40%)')]] as const).map(([k, label]) => (
            <div key={k} className={`rounded-lg border px-2 py-1.5 ${k === 'unseen' ? 'border-gold-500/30 bg-gold-500/[0.05]' : 'border-line bg-white/[0.02]'}`}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
              <div className={`font-mono font-semibold ${T[k].totalR >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{signed(T[k].totalR)}</div>
              <div className="font-mono text-slate-400">{T[k].trades} · {T[k].winRate}% · 2R {T[k].tp2R}%</div>
            </div>
          ))}
        </div>
      )}

      {!plan.live && <p className="mt-2 text-[11px] leading-snug text-slate-400">{plan.why}</p>}
      {plan.note && <p className="mt-2 text-[11px] leading-snug text-gold-300/90">{plan.note}</p>}

      {plan.live && (
        <details className="group mt-2">
          <summary className="flex items-center gap-1 cursor-pointer list-none text-[11px] text-slate-400 hover:text-slate-200">
            <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
            {t('Why this strategy', 'Pourquoi cette stratégie', 'علاش هاد الاستراتيجية')}
          </summary>
          <p className="mt-1.5 text-[11px] text-slate-300 leading-relaxed">{plan.why}</p>
          {T && <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">{t('Neighbouring settings', 'Réglages voisins', 'الإعدادات القريبة')}: {T.neighbours} · {t('double costs', 'coûts ×2', 'التكاليف ×2')} {signed(T.costsX2)}</p>}
        </details>
      )}
    </section>
  );
};
