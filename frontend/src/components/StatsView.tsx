import React, { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { apiJson } from '../api';
import { readCache, writeCache } from '../cache';
import { tr } from './ui';
import type { Language } from '../types';

/**
 * The pips calendar (/api/smc/calendar): every trade closed since Monday 2026-11-23 (the owner's request of 2026-11-22),
 * grouped in the viewer's own time zone by day, by week (Monday → Sunday) and by month. Net pips = pips won − pips lost.
 * The month total is the headline. Kept on the device and shown at once, refreshed every minute.
 */
interface CalTrade { id: string; symbol: string; direction: 'BUY' | 'SELL'; outcome: 'WIN' | 'LOSS' | 'BREAKEVEN' | null; r: number | null; pips: number; exitTime: number }
interface Calendar { since: number; trades: CalTrade[] }
interface Agg { pips: number; won: number; lost: number; wins: number; losses: number; be: number; n: number }

const REFRESH_MS = 60000;
const empty = (): Agg => ({ pips: 0, won: 0, lost: 0, wins: 0, losses: 0, be: 0, n: 0 });
const add = (a: Agg, t: CalTrade) => {
  a.n += 1; a.pips += t.pips;
  if (t.pips > 0) a.won += t.pips; else a.lost += -t.pips;
  if (t.outcome === 'WIN') a.wins += 1; else if (t.outcome === 'LOSS') a.losses += 1; else a.be += 1;
};
const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const fmt = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v * 10) / 10).toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
const tone = (v: number, n: number) => (!n ? 'text-slate-500' : v > 0 ? 'text-emerald-300' : v < 0 ? 'text-rose-300' : 'text-slate-200');
const cellTone = (v: number, n: number) => (!n ? '' : v > 0 ? 'bg-emerald-500/10 border-emerald-500/30' : v < 0 ? 'bg-rose-500/10 border-rose-500/30' : 'bg-white/5');

export const StatsView: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [cal, setCal] = useState<Calendar | null>(() => readCache<Calendar>('dash', 'calendar', 7 * 24 * 3600 * 1000));
  const [month, setMonth] = useState(() => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); });
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const load = () => {
      if (document.hidden) return;
      apiJson<Calendar & { success: boolean }>('/api/smc/calendar')
        .then(j => { if (!stop && j.success) { setCal(j); writeCache('dash', 'calendar', j); } }).catch(() => {});
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const since = cal ? new Date(cal.since * 1000) : null;
  const startDay = since ? new Date(since.getFullYear(), since.getMonth(), since.getDate()) : null;
  const firstMonth = startDay ? new Date(startDay.getFullYear(), startDay.getMonth(), 1) : null;
  const thisMonth = (() => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); })();

  // day → trades and totals, in the viewer's time zone
  const byDay = useMemo(() => {
    const m = new Map<string, { agg: Agg; trades: CalTrade[] }>();
    for (const x of cal?.trades ?? []) {
      const k = key(new Date(x.exitTime * 1000));
      if (!m.has(k)) m.set(k, { agg: empty(), trades: [] });
      const d = m.get(k)!; add(d.agg, x); d.trades.push(x);
    }
    return m;
  }, [cal]);

  // the month's weeks, Monday → Sunday, each with its total
  const weeks = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first); start.setDate(first.getDate() - ((first.getDay() + 6) % 7));  // back to Monday
    const out: { days: Date[]; agg: Agg }[] = [];
    const cur = new Date(start);
    for (let w = 0; w < 6; w++) {
      const days: Date[] = []; const agg = empty();
      for (let i = 0; i < 7; i++) {
        days.push(new Date(cur));
        for (const x of byDay.get(key(cur))?.trades ?? []) add(agg, x);
        cur.setDate(cur.getDate() + 1);
      }
      if (!startDay || cur > startDay) out.push({ days, agg });  // a week that ended before the calendar began is not shown
      if (cur.getMonth() !== month.getMonth() && cur > first) break;
    }
    return out;
  }, [month, byDay, startDay?.getTime()]);

  const monthAgg = useMemo(() => {
    const a = empty();
    for (const x of cal?.trades ?? []) { const d = new Date(x.exitTime * 1000); if (d.getFullYear() === month.getFullYear() && d.getMonth() === month.getMonth()) add(a, x); }
    return a;
  }, [cal, month]);

  const locale = lang === 'ar' ? 'ar-MA' : lang === 'fr' ? 'fr-FR' : 'en-GB';
  const monthName = month.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
  const wd = [t('Mon', 'Lun', 'إث'), t('Tue', 'Mar', 'ثل'), t('Wed', 'Mer', 'أر'), t('Thu', 'Jeu', 'خم'), t('Fri', 'Ven', 'جم'), t('Sat', 'Sam', 'سب'), t('Sun', 'Dim', 'أح')];
  const canPrev = !firstMonth || month > firstMonth;
  const canNext = month < thisMonth;
  const shift = (n: number) => { setPicked(null); setMonth(m => new Date(m.getFullYear(), m.getMonth() + n, 1)); };
  const winRate = monthAgg.wins + monthAgg.losses ? Math.round((100 * monthAgg.wins) / (monthAgg.wins + monthAgg.losses)) : null;
  const pickedDay = picked ? byDay.get(picked) : null;
  const today = key(new Date());

  return (
    <div className="space-y-4">
      {/* the month: the headline */}
      <div className="rounded-2xl border border-gold-500/30 bg-surface p-4">
        <div className="flex items-center justify-between gap-2">
          <button onClick={() => shift(-1)} disabled={!canPrev} aria-label={t('Previous month', 'Mois précédent', 'الشهر اللي فات')}
            className="p-2 rounded-lg border border-line text-slate-300 disabled:opacity-30 hover:bg-white/5"><ChevronLeft className="w-4 h-4 rtl:rotate-180" /></button>
          <div className="text-center">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">{monthName}</div>
            <div className={`mt-1 font-mono text-3xl font-bold ${tone(monthAgg.pips, monthAgg.n)}`}>{monthAgg.n ? fmt(monthAgg.pips) : '0'} <span className="text-base font-semibold">pips</span></div>
          </div>
          <button onClick={() => shift(1)} disabled={!canNext} aria-label={t('Next month', 'Mois suivant', 'الشهر الجاي')}
            className="p-2 rounded-lg border border-line text-slate-300 disabled:opacity-30 hover:bg-white/5"><ChevronRight className="w-4 h-4 rtl:rotate-180" /></button>
        </div>
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
          {[
            [t('Pips won', 'Pips gagnés', 'بيبس ربح'), monthAgg.won ? `+${fmt(monthAgg.won).replace('+', '')}` : '0', 'text-emerald-300'],
            [t('Pips lost', 'Pips perdus', 'بيبس خسارة'), monthAgg.lost ? `−${fmt(monthAgg.lost).replace('+', '')}` : '0', 'text-rose-300'],
            [t('Trades won · lost', 'Trades gagnés · perdus', 'صفقات ربح · خسارة'), `${monthAgg.wins} · ${monthAgg.losses}${monthAgg.be ? ` · ${monthAgg.be} BE` : ''}`, 'text-slate-200'],
            [t('Win rate', 'Taux de réussite', 'نسبة الربح'), winRate != null ? `${winRate} %` : '—', 'text-gold-200'],
          ].map(([label, value, c]) => (
            <div key={label} className="rounded-xl bg-white/[0.03] border border-line p-2">
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
              <div className={`mt-0.5 font-mono text-sm font-semibold ${c}`}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* the calendar: one row per week, its total on the right */}
      <div className="rounded-2xl border border-line bg-surface p-2 sm:p-3">
        <div className="grid grid-cols-[repeat(7,minmax(0,1fr))_minmax(0,1.25fr)] gap-1 sm:gap-1.5">
          {wd.map(d => <div key={d} className="text-center text-[10px] uppercase tracking-wider text-slate-500 py-1">{d}</div>)}
          <div className="text-center text-[10px] uppercase tracking-wider text-gold-300 py-1">{t('Week', 'Semaine', 'السيمانة')}</div>
          {weeks.map((w, wi) => (
            <React.Fragment key={wi}>
              {w.days.map(d => {
                const k = key(d);
                const inMonth = d.getMonth() === month.getMonth();
                const before = startDay ? d < startDay : true;
                const x = byDay.get(k);
                const a = x?.agg;
                return (
                  <button key={k} disabled={!x} onClick={() => setPicked(p => (p === k ? null : k))}
                    className={`relative min-h-[52px] sm:min-h-[72px] rounded-lg border p-1 sm:p-1.5 text-left flex flex-col justify-between transition-colors
                      ${inMonth ? 'border-line' : 'border-transparent opacity-40'} ${before ? 'opacity-30' : ''} ${a ? cellTone(a.pips, a.n) : ''}
                      ${picked === k ? 'ring-1 ring-gold-400' : ''} ${x ? 'hover:bg-white/5 cursor-pointer' : 'cursor-default'}`}>
                    <span className={`text-[10px] sm:text-xs ${k === today ? 'text-gold-300 font-bold' : 'text-slate-400'}`}>{d.getDate()}</span>
                    {a && <span className={`font-mono text-[10px] sm:text-sm font-semibold leading-tight ${tone(a.pips, a.n)}`}>{fmt(a.pips)}</span>}
                    {a && <span className="hidden sm:block text-[10px] text-slate-500">{a.n} {t(a.n > 1 ? 'trades' : 'trade', a.n > 1 ? 'trades' : 'trade', 'صفقة')}</span>}
                  </button>
                );
              })}
              <div className={`min-h-[52px] sm:min-h-[72px] rounded-lg border border-gold-500/20 bg-gold-500/5 p-1 sm:p-1.5 flex flex-col justify-center items-center text-center`}>
                <span className={`font-mono text-[11px] sm:text-sm font-bold ${tone(w.agg.pips, w.agg.n)}`}>{w.agg.n ? fmt(w.agg.pips) : '—'}</span>
                {w.agg.n > 0 && <span className="text-[9px] sm:text-[10px] text-slate-500">{w.agg.wins}✓ {w.agg.losses}✗</span>}
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* the day that was tapped: its trades */}
      {pickedDay && (
        <div className="rounded-2xl border border-line bg-surface p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
            {new Date(pickedDay.trades[0].exitTime * 1000).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
            {' · '}<span className={tone(pickedDay.agg.pips, pickedDay.agg.n)}>{fmt(pickedDay.agg.pips)} pips</span>
          </div>
          <ul className="divide-y divide-line">
            {pickedDay.trades.map(x => (
              <li key={x.id} className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-slate-200">{x.symbol} <span className={x.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{x.direction}</span></span>
                <span className="font-mono text-xs text-slate-400">{x.r != null ? `${x.r > 0 ? '+' : ''}${x.r}R` : ''}</span>
                <span className={`font-mono font-semibold ${tone(x.pips, 1)}`}>{fmt(x.pips)} pips</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-slate-500">
        {since
          ? `${t('Counting since', 'Compté depuis', 'كيتحسب من')} ${since.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} · ${t('every closed trade, by the day it closed · net pips = pips won − pips lost', 'chaque trade clôturé, au jour de sa clôture · pips nets = pips gagnés − pips perdus', 'كل صفقة تسدات، فالنهار اللي تسدات فيه · الصافي = البيبس اللي ربحتي ناقص اللي خسرتي')}`
          : '…'}
      </p>
    </div>
  );
};
