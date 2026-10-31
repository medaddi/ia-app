import React from 'react';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * A trade as a live bar: the stop on the left, the entry, the target on the right (the profit side is always on the right,
 * BUY or SELL), and the price now as a marker. The part between the entry and the price fills green toward the target or
 * red toward the stop, with the result in R so far.
 */
export interface TradeProgressProps {
  direction: 'BUY' | 'SELL' | string;
  entry: number;
  sl: number;
  tp: number;
  price: number | null | undefined;
  decimals: number;
  pip?: number;  // price units per pip (gold 0.1, forex 0.0001)
  lang?: Language;
  compact?: boolean;  // dashboard cards: smaller labels
}

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));

export const TradeProgress: React.FC<TradeProgressProps> = ({ direction, entry, sl, tp, price, decimals, pip, lang = 'en', compact = false }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const f = (v: number) => v.toFixed(decimals);
  const span = tp - sl;
  if (!span || !(entry !== sl)) return null;
  const pos = (v: number) => clamp((v - sl) / span);  // 0 = stop, 1 = target, for BUY and SELL alike
  const ePos = pos(entry);
  const p = price && price > 0 ? price : entry;
  const pPos = pos(p);
  const r = (p - entry) / (entry - sl);  // R so far (positive = in profit)
  const win = r >= 0;
  const hitTp = pPos >= 1, hitSl = pPos <= 0;
  const away = (target: number) => {
    const d = Math.abs(target - p);
    if (decimals === 2) return `$${d.toFixed(2)}`;  // gold: dollars per ounce read better than pips
    return pip ? `${(d / pip).toFixed(1)} pips` : f(d);
  };
  const fillFrom = Math.min(ePos, pPos), fillTo = Math.max(ePos, pPos);
  const label = compact ? 'text-[10px]' : 'text-[11px]';

  return (
    <div className="select-none" dir="ltr" aria-label={t(`Trade progress: ${r >= 0 ? '+' : ''}${r.toFixed(2)}R`, `Progression du trade : ${r >= 0 ? '+' : ''}${r.toFixed(2)}R`, `تقدم الصفقة: ${r.toFixed(2)}R`)}>
      {/* Live result */}
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className={`${label} uppercase tracking-wider text-slate-500`}>{t('Price now', 'Prix actuel', 'الثمن دابا')}</div>
          <div className={`font-mono font-semibold tabular-nums text-white ${compact ? 'text-base' : 'text-lg'}`}>{f(p)}</div>
        </div>
        <div className="text-end">
          <div className={`font-mono font-bold tabular-nums transition-colors duration-500 ${compact ? 'text-lg' : 'text-2xl'} ${win ? 'text-emerald-300' : 'text-rose-300'}`}>
            {r >= 0 ? '+' : ''}{r.toFixed(2)}R
          </div>
          <div className={`${label} font-mono text-slate-500`}>
            {hitTp ? t('target reached', 'objectif atteint', 'وصل للهدف') : hitSl ? t('stop touched', 'stop touché', 'ضرب الستوب')
              : `${away(tp)} ${t('to TP', 'du TP', 'للهدف')} · ${away(sl)} ${t('to SL', 'du SL', 'للستوب')}`}
          </div>
        </div>
      </div>

      {/* The bar */}
      <div className={`relative ${compact ? 'mt-3 h-2.5' : 'mt-4 h-3'}`}>
        <div className="absolute inset-0 rounded-full overflow-hidden bg-surface-3">
          <div className="absolute inset-y-0 start-0 bg-rose-500/20" style={{ width: `${ePos * 100}%` }} />
          <div className="absolute inset-y-0 end-0 bg-emerald-500/15" style={{ width: `${(1 - ePos) * 100}%` }} />
          <div className={`absolute inset-y-0 transition-[left,width,background-color] duration-700 ease-out ${win ? 'bg-gradient-to-r from-emerald-500/60 to-emerald-300' : 'bg-gradient-to-l from-rose-500/60 to-rose-300'}`}
            style={{ left: `${fillFrom * 100}%`, width: `${(fillTo - fillFrom) * 100}%` }} />
        </div>
        {/* entry tick */}
        <div className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-gold-300" style={{ left: `calc(${ePos * 100}% - 1px)` }} aria-hidden="true" />
        {/* price marker */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 transition-[left] duration-700 ease-out" style={{ left: `${pPos * 100}%` }} aria-hidden="true">
          <span className={`absolute inset-0 -m-1.5 rounded-full blur-md ${win ? 'bg-emerald-400/50' : 'bg-rose-400/50'}`} />
          <span className={`relative block rounded-full ring-2 ring-canvas ${compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} ${win ? 'bg-emerald-300' : 'bg-rose-300'}`} />
        </div>
      </div>

      {/* Levels under the bar */}
      <div className={`relative mt-2 ${compact ? 'h-8' : 'h-9'}`}>
        <div className="absolute start-0 top-0 text-start">
          <div className={`${label} uppercase tracking-wider text-rose-300/80`}>SL</div>
          <div className={`font-mono tabular-nums text-rose-300 ${compact ? 'text-xs' : 'text-sm'}`}>{f(sl)}</div>
        </div>
        <div className="absolute top-0 -translate-x-1/2 text-center" style={{ left: `${clamp(ePos, 0.22, 0.78) * 100}%` }}>
          <div className={`${label} uppercase tracking-wider text-gold-300/80`}>{t('Entry', 'Entrée', 'الدخول')} · {direction}</div>
          <div className={`font-mono tabular-nums text-gold-200 ${compact ? 'text-xs' : 'text-sm'}`}>{f(entry)}</div>
        </div>
        <div className="absolute end-0 top-0 text-end">
          <div className={`${label} uppercase tracking-wider text-emerald-300/80`}>TP</div>
          <div className={`font-mono tabular-nums text-emerald-300 ${compact ? 'text-xs' : 'text-sm'}`}>{f(tp)}</div>
        </div>
      </div>
    </div>
  );
};
