import React, { useEffect, useState } from 'react';
import { apiJson } from '../api';
import { readCache, writeCache } from '../cache';
import { tr } from './ui';
import type { Language } from '../types';

/**
 * The app's trade history (/api/smc/history): every trade sent since the history began (counted from that moment on,
 * the owner's request of 2026-11-19), its state and result, the counts, the win rate (won / closed), the R total, and
 * the win rate after each closed trade as a small line. Kept on the device and shown at once, refreshed every 30 s.
 */
interface Item {
  id: string; symbol: string; direction: 'BUY' | 'SELL'; time: number; entry: number; sl: number; tp: number; rr: number | null;
  state: string; outcome: 'WIN' | 'LOSS' | 'BREAKEVEN' | null; resultR: number | null; exitTime: number | null;
  setupType?: string | null; grade?: string | null; etf?: string | null; score?: number | null; market?: boolean | null;
}
interface Summary { given: number; running: number; closed: number; wins: number; breakeven: number; losses: number; notFilled: number; winRate: number | null; totalR: number }
interface History { since: number; summary: Summary; curve: { time: number; winRate: number; totalR: number }[]; items: Item[] }

const REFRESH_MS = 30000;
const dec = (s: string) => (s.startsWith('XAU') ? 2 : s.endsWith('JPY') ? 3 : 5);
const day = (t: number) => new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ');

/** The win rate after each closed trade, 0 → 100 %, with the 50 % line. */
const Curve: React.FC<{ pts: number[] }> = ({ pts }) => {
  if (pts.length < 2) return null;
  const w = 100, h = 28;
  const d = pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1)) * w},${h - (v / 100) * h}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-8" aria-hidden="true">
      <line x1="0" x2={w} y1={h / 2} y2={h / 2} stroke="currentColor" className="text-slate-600" strokeDasharray="2 2" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
      <path d={d} fill="none" stroke="currentColor" className="text-gold-300" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

export const TradeHistory: React.FC<{ lang: Language; onOpenChart: (symbol: string) => void }> = ({ lang, onOpenChart }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [h, setH] = useState<History | null>(() => readCache<History>('dash', 'history', 24 * 3600 * 1000));
  const [all, setAll] = useState(false);

  useEffect(() => {
    let stop = false;
    const load = () => {
      if (document.hidden) return;
      apiJson<History & { success: boolean }>('/api/smc/history')
        .then(j => { if (!stop && j.summary) { setH(j); writeCache('dash', 'history', j); } }).catch(() => {});
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const s = h?.summary;
  const status = (x: Item) => x.state === 'CLOSED'
    ? { word: x.outcome === 'WIN' ? t('Won', 'Gagné', 'ربح') : x.outcome === 'LOSS' ? t('Lost', 'Perdu', 'خسارة') : 'BE',
        tone: x.outcome === 'WIN' ? 'text-emerald-300' : x.outcome === 'LOSS' ? 'text-rose-300' : 'text-slate-300' }
    : x.state === 'OPEN' ? { word: t('In trade', 'En cours', 'خدامة'), tone: 'text-sky-300' }
    : x.state === 'EXPIRED' || x.state === 'MISSED' ? { word: t('Not filled', 'Non exécuté', 'ما تفعلاتش'), tone: 'text-slate-500' }
    : { word: t('Waiting for entry', 'Attend l’entrée', 'كتسنا الدخول'), tone: 'text-amber-300' };
  const shown = all ? h?.items ?? [] : (h?.items ?? []).slice(0, 10);

  return (
    <div>
      <p className="mb-2 text-[11px] text-slate-500">
        {h ? `${t('Counting since', 'Compté depuis', 'كيتحسب من')} ${day(h.since)} UTC · ${t('every trade sent is counted', 'chaque trade envoyé compte', 'كل صفقة تصيفطات كتتحسب')}` : '…'}
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
        {[
          [t('Trades given', 'Trades donnés', 'صفقات تعطات'), s ? String(s.given) : '—', 'text-white'],
          [t('In progress', 'En cours', 'خدامين'), s ? String(s.running) : '—', 'text-sky-300'],
          [t('Win rate', 'Taux de réussite', 'نسبة الربح'), s?.winRate != null ? `${s.winRate} %` : '—', 'text-gold-200'],
          [t('Won · BE · lost', 'Gagnés · BE · perdus', 'ربح · BE · خسارة'), s ? `${s.wins} · ${s.breakeven} · ${s.losses}` : '—', 'text-slate-200'],
          [t('Result', 'Résultat', 'النتيجة'), s ? `${s.totalR >= 0 ? '+' : ''}${s.totalR}R` : '—', s && s.totalR < 0 ? 'text-rose-300' : 'text-emerald-300'],
        ].map(([label, value, tone], i) => (
          <div key={label} className={`rounded-xl bg-surface border border-line p-2.5 ${i === 2 ? 'col-span-2 sm:col-span-1 border-gold-500/30' : ''}`}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`mt-1 font-mono text-sm font-semibold ${tone}`}>{value}</div>
          </div>
        ))}
      </div>
      {h && h.curve.length >= 2 && (
        <div className="mt-2 rounded-xl bg-surface border border-line px-3 py-2">
          <div className="flex justify-between text-[10px] text-slate-500">
            <span>{t('Win rate after each closed trade', 'Taux de réussite après chaque trade clôturé', 'نسبة الربح من بعد كل صفقة سدات')}</span><span>50 %</span>
          </div>
          <Curve pts={h.curve.map(c => c.winRate)} />
        </div>
      )}
      {s && s.closed === 0 && <p className="mt-2 text-[11px] text-slate-500">{t('The win rate appears with the first closed trade.', 'Le taux de réussite apparaît au premier trade clôturé.', 'نسبة الربح كتبان مع أول صفقة كتسد.')}</p>}

      <div className="mt-3">
        {!h || h.items.length === 0 ? <p className="text-xs text-slate-500">{t('No trade sent since the history began.', 'Aucun trade envoyé depuis le début de l’historique.', 'حتى صفقة ما تصيفطات من بداية التاريخ.')}</p> : (
          <>
            <ul className="space-y-1.5">
              {shown.map(x => {
                const st = status(x);
                const d = dec(x.symbol);
                return (
                  <li key={x.id}>
                    <button type="button" onClick={() => onOpenChart(x.symbol)}
                      className="w-full flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border border-line bg-surface px-3 py-2 text-xs font-mono text-start cursor-pointer hover:border-gold-500/40">
                      <span className="text-slate-500">{day(x.time).slice(5)}</span>
                      <span className="text-white font-semibold">{x.symbol}</span>
                      <span className={x.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{x.direction} {x.entry.toFixed(d)}</span>
                      {x.grade && <span className="text-gold-300">{x.grade}</span>}
                      <span className="text-slate-400">SL {x.sl.toFixed(d)} · TP {x.tp.toFixed(d)}{x.rr != null ? ` · 1:${x.rr.toFixed(1)}` : ''}</span>
                      <span className={`ms-auto font-semibold ${st.tone}`}>
                        {st.word}{x.state === 'CLOSED' && x.resultR != null ? ` ${x.resultR >= 0 ? '+' : ''}${x.resultR.toFixed(2)}R` : ''}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {h.items.length > 10 && (
              <button type="button" onClick={() => setAll(v => !v)} className="mt-2 text-[11px] text-gold-300 hover:text-gold-200 cursor-pointer">
                {all ? t('Show less', 'Voir moins', 'بين أقل') : `${t('Show all', 'Tout voir', 'بين الكل')} (${h.items.length})`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
};
