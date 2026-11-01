import React, { useEffect, useState } from 'react';
import { DoorOpen, ShieldCheck, Target, Timer } from 'lucide-react';
import type { StrategyResult } from '../strategyTypes';
import type { Language } from '../types';
import { tr } from './ui';

/**
 * Trade management: what to do with the stop, the target and the exit right now, from the strategy's own rules.
 * Every strategy is set & forget (SL and TP never move); the only early exits are RSI(2)'s H4 close back across EMA5
 * (EUR/USD, GBP/USD) and the time exits (gold reversion after 24 H1 candles, RSI(2) after 48 H4 candles).
 * A row that asks for an action now is lit in gold.
 */
const TF_SEC: Record<string, number> = { M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400 };

interface Row { key: string; icon: React.ReactNode; label: string; text: string; action?: boolean }

const hhmm = (sec: number) => new Date(sec * 1000).toISOString().slice(11, 16);
const dayHhmm = (sec: number) => new Date(sec * 1000).toISOString().slice(5, 16).replace('T', ' ');
const left = (sec: number) => {
  const s = Math.max(0, Math.round(sec)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m} min`;
};

export const TradeManagement: React.FC<{ result: StrategyResult; lang: Language }> = ({ result, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => { const id = setInterval(() => setNow(Date.now() / 1000), 15000); return () => clearInterval(id); }, []);
  const s = result.setup;
  if (!s) return null;
  const state = s.lifecycle.state;
  const live = ['OPEN', 'TP1_HIT', 'TP2_HIT'].includes(state);
  if (!live && state !== 'PENDING') return null;

  const d = result.spec.decimals;
  const f = (v: number) => v.toFixed(d);
  const buy = s.direction === 'BUY';
  const p = s.params ?? {};
  const tfSec = TF_SEC[result.timeframes.entry] ?? 3600;
  const maxBars = typeof p.maxBars === 'number' ? p.maxBars : null;
  const timeExit = maxBars ? s.signalTime + maxBars * tfSec : null;
  const rows: Row[] = [];

  if (state === 'PENDING') {
    rows.push({ key: 'order', icon: <Timer className="w-4 h-4" />, label: t('Order', 'Ordre', 'الأمر'),
      text: t(`Limit order at ${f(s.entry)}: wait for the price`, `Ordre limite à ${f(s.entry)} : attendez le prix`, `أمر معلق ف ${f(s.entry)}: تسنى الثمن`) });
    if (s.expiresAt) {
      const soon = s.expiresAt - now < 1800;
      rows.push({ key: 'expiry', icon: <DoorOpen className="w-4 h-4" />, label: t('Cancel', 'Annuler', 'إلغاء'), action: soon,
        text: t(`Delete the order if not filled by ${hhmm(s.expiresAt)} UTC`, `Supprimez l’ordre s’il n’est pas déclenché avant ${hhmm(s.expiresAt)} UTC`,
          `مسح الأمر إلا ما تفعلش قبل ${hhmm(s.expiresAt)} UTC`) });
    }
  } else {
    // The stop: set & forget, unless an old multi-target trade reached TP1 with "stop to entry"
    const toEntry = p.breakeven !== false && state !== 'OPEN';
    rows.push(toEntry
      ? { key: 'sl', icon: <ShieldCheck className="w-4 h-4" />, label: 'SL', action: true,
          text: t(`Move the stop to the entry ${f(s.entry)}`, `Montez le stop à l’entrée ${f(s.entry)}`, `حط الستوب ف الدخول ${f(s.entry)}`) }
      : { key: 'sl', icon: <ShieldCheck className="w-4 h-4" />, label: 'SL',
          text: t(`Keep it at ${f(s.sl)}: never move it`, `Gardez-le à ${f(s.sl)} : ne le bougez pas`, `خليه ف ${f(s.sl)}: ما تحركوش`) });
    rows.push({ key: 'tp', icon: <Target className="w-4 h-4" />, label: 'TP',
      text: t(`Keep it at ${f(s.tp3)}`, `Gardez-le à ${f(s.tp3)}`, `خليه ف ${f(s.tp3)}`) });

    // The exit
    const ema5 = typeof result.facts?.ema5 === 'number' ? (result.facts.ema5 as number) : null;
    if (s.setup === 'RSI2' && ema5 !== null) {
      const nextClose = (Math.floor(now / 14400) + 1) * 14400;
      const across = buy ? result.price > ema5 : result.price < ema5;  // the exit condition, if this H4 candle closes like this
      rows.push(across
        ? { key: 'exit', icon: <DoorOpen className="w-4 h-4" />, label: t('Exit', 'Sortie', 'الخروج'), action: true,
            text: t(`Price is ${buy ? 'above' : 'below'} EMA5 (${f(ema5)}): if the H4 candle closes there in ${left(nextClose - now)}, close the trade`,
              `Le prix est ${buy ? 'au-dessus' : 'en dessous'} de l’EMA5 (${f(ema5)}) : si la bougie H4 clôture ainsi dans ${left(nextClose - now)}, fermez le trade`,
              `الثمن ${buy ? 'فوق' : 'تحت'} EMA5 (${f(ema5)}): إلا سدات شمعة H4 هكا من بعد ${left(nextClose - now)}، سد الصفقة`) }
        : { key: 'exit', icon: <DoorOpen className="w-4 h-4" />, label: t('Exit', 'Sortie', 'الخروج'),
            text: t(`At the first H4 close ${buy ? 'above' : 'below'} EMA5 (${f(ema5)})`, `À la 1re clôture H4 ${buy ? 'au-dessus' : 'en dessous'} de l’EMA5 (${f(ema5)})`,
              `ف أول إغلاق H4 ${buy ? 'فوق' : 'تحت'} EMA5 (${f(ema5)})`) });
    }
    if (timeExit) {
      const soon = timeExit - now <= tfSec;
      rows.push({ key: 'time', icon: <Timer className="w-4 h-4" />, label: t('Time', 'Durée', 'الوقت'), action: soon,
        text: soon
          ? t(`Close the trade at ${hhmm(timeExit)} UTC (${left(timeExit - now)})`, `Fermez le trade à ${hhmm(timeExit)} UTC (${left(timeExit - now)})`, `سد الصفقة ف ${hhmm(timeExit)} UTC (${left(timeExit - now)})`)
          : t(`Closed at ${dayHhmm(timeExit)} UTC at the latest`, `Fermé au plus tard le ${dayHhmm(timeExit)} UTC`, `كتسد على أبعد تقدير ${dayHhmm(timeExit)} UTC`) });
    }
    if (s.setup !== 'RSI2' && !timeExit) {
      rows.push({ key: 'exit', icon: <DoorOpen className="w-4 h-4" />, label: t('Exit', 'Sortie', 'الخروج'),
        text: t('No early exit: TP or SL closes it', 'Pas de sortie anticipée : TP ou SL la clôture', 'ما كاين خروج بكري: TP ولا SL') });
    }
  }

  const act = rows.some(r => r.action);
  return (
    <section aria-labelledby="mgmt-title" className="mt-3 rounded-2xl border border-line bg-surface/60 p-3">
      <header className="flex items-center justify-between gap-2 mb-2">
        <h4 id="mgmt-title" className="text-[11px] uppercase tracking-wider text-slate-400">{t('Trade management', 'Gestion du trade', 'تسيير الصفقة')}</h4>
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ring-1 ring-inset ${act ? 'bg-gold-500/15 text-gold-200 ring-gold-500/40' : 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30'}`}>
          {act ? t('Action needed', 'Action à faire', 'خاصك دير شي حاجة') : t('Nothing to do', 'Rien à faire', 'ما كاين ما تدير')}
        </span>
      </header>
      <ul className="space-y-1.5">
        {rows.map(r => (
          <li key={r.key} className={`flex items-center gap-2.5 rounded-xl px-2.5 py-2 border transition-colors ${r.action ? 'border-gold-500/40 bg-gold-500/[0.08]' : 'border-transparent bg-white/[0.02]'}`}>
            <span className={`icon-tile w-7 h-7 ${r.action ? 'icon-tile-gold' : 'text-slate-400'}`} aria-hidden="true">{r.icon}</span>
            <span className="min-w-0 flex-1">
              <span className={`block text-[10px] uppercase tracking-wider ${r.action ? 'text-gold-300' : 'text-slate-500'}`}>{r.label}</span>
              <span className={`block text-xs leading-snug ${r.action ? 'text-gold-100 font-medium' : 'text-slate-200'}`}>{r.text}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
};
