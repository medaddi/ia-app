import React, { useEffect, useMemo, useState } from 'react';
import { Calculator, Copy, Check, ShieldCheck } from 'lucide-react';
import { apiJson } from '../api';
import type { StrategyResult } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * Lot calculator under the chart: the lot for my risk in $ with the trade's own stop (the stop stays at the structure,
 * only the lot changes). The backend does the maths (/api/lot): stop distance + spread + slippage, USD conversion for
 * CAD / CHF quotes, rounded DOWN to 0.01 so the loss at the stop is never above the risk.
 */
interface LotAnswer { lots: number; actualRisk: number; perLot: number; tooSmall: boolean; riskUsd: number; stopDistance: number; cost: number; usdPerPoint: number }

const num = (s: string) => { const v = Number(s.replace(',', '.')); return Number.isFinite(v) ? v : NaN; };
const RISK_KEY = 'ld_lot_risk_usd';

export const LotCalculator: React.FC<{ result: StrategyResult | null; lang?: Language }> = ({ result, lang = 'en' }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const s = result?.setup ?? null;
  const d = result?.spec.decimals ?? 5;
  const pip = result?.spec.pipSize ?? 0.0001;
  const sym = result?.spec.displaySymbol ?? '';
  const [risk, setRisk] = useState(() => { try { return localStorage.getItem(RISK_KEY) || ''; } catch { return ''; } });
  const [entry, setEntry] = useState('');
  const [sl, setSl] = useState('');
  const [ans, setAns] = useState<LotAnswer | null>(null);
  const [err, setErr] = useState('');
  const [copied, setCopied] = useState(false);

  // Follow the strategy's trade (its stop is the structure); without a trade, start from the live price
  const setupKey = s ? `${s.id}|${s.entry}|${s.sl}` : `${sym}|none`;
  useEffect(() => {
    if (s) { setEntry(s.entry.toFixed(d)); setSl(s.sl.toFixed(d)); }
    else if (result?.price) { setEntry(result.price.toFixed(d)); setSl(''); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setupKey]);

  // My saved risk (profile) the first time, when nothing was typed here
  useEffect(() => {
    if (risk) return;
    apiJson<{ user?: { effectiveRisk?: number | null } }>('/api/me').then(r => { if (r.user?.effectiveRisk) setRisk(String(r.user.effectiveRisk)); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const e = num(entry), st = num(sl), rk = num(risk);
  const valid = sym && e > 0 && st > 0 && e !== st && rk > 0;
  useEffect(() => {
    try { if (rk > 0) localStorage.setItem(RISK_KEY, String(rk)); } catch { /* storage unavailable */ }
    if (!valid) { setAns(null); return; }
    const id = setTimeout(() => {
      apiJson<LotAnswer>(`/api/lot?symbol=${encodeURIComponent(sym)}&entry=${e}&sl=${st}&riskUsd=${rk}`)
        .then(r => { setAns(r); setErr(''); }).catch(x => setErr(String(x.message || x)));
    }, 250);
    return () => clearTimeout(id);
  }, [sym, e, st, rk, valid]);

  const buy = s ? s.direction === 'BUY' : e > st;
  const tp = s?.tp3 ?? null;
  const stopPips = e > 0 && st > 0 ? Math.abs(e - st) / pip : 0;
  const atTp = useMemo(() => (ans && tp ? ans.lots * Math.abs(tp - e) * ans.usdPerPoint - ans.lots * ans.cost * ans.usdPerPoint : null), [ans, tp, e]);
  const moved = !!s && (Math.abs(st - s.sl) > pip / 100);
  const gold = result?.symbol === 'XAUUSD';
  const unit = (v: number) => (gold ? `$${v.toFixed(2)}` : `${(v / pip).toFixed(1)} pips`);

  const field = 'w-full h-10 px-3 rounded-lg bg-surface-2 border border-line text-sm font-mono text-white focus:outline-none focus:border-gold-500/60 focus:ring-2 focus:ring-gold-500/20 transition';
  return (
    <section className="mt-4 p-4 rounded-[var(--radius-card)] bg-surface border border-line" aria-labelledby="lotcalc-title">
      <header className="flex items-center justify-between gap-3 mb-3">
        <h3 id="lotcalc-title" className="flex items-center gap-2 text-sm font-semibold text-white">
          <Calculator className="w-4 h-4 text-gold-400" aria-hidden="true" />
          {t('Lot calculator', 'Calculateur de lot', 'حاسبة اللوت')}
          <span className="text-xs font-normal text-slate-500">· {sym}{s ? ` · ${s.direction}` : ''}</span>
        </h3>
        <span className="hidden sm:flex items-center gap-1 text-[11px] text-slate-400"><ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
          {t('Stop stays at the structure, the lot adapts', 'Le stop reste sur la structure, le lot s’adapte', 'الستوب كيبقى ف البلاصة ديالو، اللوت هو لي كيتبدل')}</span>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="text-xs text-slate-400 space-y-1">
          <span>{t('My risk on this trade ($)', 'Mon risque sur ce trade ($)', 'المخاطرة ديالي ف هاد الصفقة ($)')}</span>
          <input inputMode="decimal" value={risk} placeholder="80" onChange={x => setRisk(x.target.value)} className={field} aria-describedby="lotcalc-out" />
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          <span>{t('Entry', 'Entrée', 'الدخول')}</span>
          <input inputMode="decimal" value={entry} onChange={x => setEntry(x.target.value)} className={field} />
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          <span>{t('Stop loss (structure)', 'Stop loss (structure)', 'الستوب (الهيكل)')}</span>
          <input inputMode="decimal" value={sl} placeholder={t('price', 'prix', 'الثمن')} onChange={x => setSl(x.target.value)} className={field} />
        </label>
      </div>

      <div id="lotcalc-out" role="status" aria-live="polite" className="mt-4 grid grid-cols-2 xl:grid-cols-4 gap-3">
        <div className="col-span-2 xl:col-span-1 rounded-xl border border-gold-500/30 bg-gold-500/[0.06] px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-wide text-gold-300/80">{t('Lot to enter', 'Lot à prendre', 'اللوت لي تدخل بيه')}</div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-mono font-semibold text-gold-200 tabular-nums">{ans ? ans.lots.toFixed(2) : '—'}</span>
            {ans && (
              <button type="button" onClick={() => { navigator.clipboard?.writeText(ans.lots.toFixed(2)).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => {}); }}
                className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-line text-slate-300 hover:bg-surface-2 cursor-pointer" aria-label={t('Copy the lot', 'Copier le lot', 'نسخ اللوت')}>
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>
        <Out label={t('Loss at the stop', 'Perte au stop', 'الخسارة ف الستوب')} value={ans ? `−$${ans.actualRisk.toFixed(2)}` : '—'} tone="text-rose-300" />
        <Out label={t('Stop + costs', 'Stop + frais', 'الستوب + المصاريف')} value={ans ? `${unit(ans.stopDistance)} + ${unit(ans.cost)}` : stopPips ? unit(Math.abs(e - st)) : '—'} />
        <Out label={tp ? t(`At the target ${tp.toFixed(d)}`, `À l’objectif ${tp.toFixed(d)}`, `ف الهدف ${tp.toFixed(d)}`) : t('Value per lot at the stop', 'Valeur par lot au stop', 'القيمة لكل لوت ف الستوب')}
          value={ans ? (atTp !== null ? `+$${atTp.toFixed(2)}` : `$${ans.perLot.toFixed(2)}`) : '—'} tone={atTp !== null ? 'text-emerald-300' : undefined} />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        {err ? <span className="text-rose-300">{err}</span>
          : ans?.tooSmall ? <span className="text-gold-300">{t('Risk too small for this stop: 0.01 lot is the minimum and risks more than your amount.', 'Risque trop petit pour ce stop : 0,01 lot est le minimum et risque plus que votre montant.', 'المخاطرة صغيرة على هاد الستوب: 0.01 هو أقل لوت وكيخاطر بكثر من المبلغ ديالك.')}</span>
          : moved ? <span className="text-gold-300">{t('You changed the stop: the strategy’s stop is', 'Vous avez changé le stop : celui de la stratégie est', 'بدلتي الستوب: ستوب الاستراتيجية هو')} {s!.sl.toFixed(d)}</span>
          : s ? t(`${buy ? 'BUY' : 'SELL'} with the strategy's stop. Spread and slippage are included and the lot is rounded down, so the loss at the stop never exceeds your risk.`,
              `${buy ? 'ACHAT' : 'VENTE'} avec le stop de la stratégie. Spread et slippage inclus, lot arrondi vers le bas : la perte au stop ne dépasse jamais votre risque.`,
              `${buy ? 'شراء' : 'بيع'} بالستوب ديال الاستراتيجية. السبريد والانزلاق محسوبين واللوت مقرب للتحت، الخسارة ف الستوب عمرها ما تفوت المخاطرة ديالك.`)
          : ans ? t('No strategy trade right now: lot for the stop you typed, spread and slippage included, rounded down.', 'Pas de trade de la stratégie : lot pour le stop saisi, spread et slippage inclus, arrondi vers le bas.', 'ما كاينة صفقة ديال الاستراتيجية: اللوت على الستوب لي كتبتي، السبريد والانزلاق محسوبين.')
          : t('No trade right now: type a stop to size a position.', 'Pas de trade en ce moment : saisissez un stop pour calculer.', 'ما كاينة حتى صفقة دابا: كتب الستوب باش تحسب.')}
      </p>
    </section>
  );
};

const Out: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone }) => (
  <div className="rounded-xl border border-line bg-surface-2 px-3 py-2.5 min-w-0">
    <div className="text-[11px] uppercase tracking-wide leading-tight text-slate-500">{label}</div>
    <div className={`text-base font-mono font-semibold tabular-nums truncate ${tone ?? 'text-white'}`}>{value}</div>
  </div>
);
