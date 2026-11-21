import React, { useEffect, useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { apiJson } from '../api';
import { readCache, writeCache } from '../cache';
import { useLivePrice } from '../livePrices';
import { PairFlags } from './PairFlags';
import { RiskInline, useMySizing } from './RiskSizing';
import { tr } from './ui';
import type { Language } from '../types';

/**
 * Every pair's FXAlexG state at a glance (the owner, 2026-11-19: "a pro dashboard that gives the details without opening
 * each pair"). One read for all the pairs (/api/smc/overview: what the notifier saved at its last pass), kept on this
 * device so it shows at once. Counters on top (tap one to filter), then the pairs ranked: trades first, then the ones
 * waiting for their trigger, then by score. Each row: the live price, the W1 / D1 / H4 trend, the grade and its score, the
 * 5 agents, the verdict, and the trade with your own lot. A tap opens the pair's chart.
 */
export interface PairSummary {
  symbol: string; at?: number; decision?: string; direction?: 'BUY' | 'SELL'; grade?: string; gpa?: number; consensus?: number; setupType?: string | null;
  trend?: Partial<Record<'W1' | 'D1' | 'H4', number>>; agents?: string[]; watching?: string | null; marketOpen?: boolean; price?: number | null; decimals?: number;
  signal?: { id: string; direction: 'BUY' | 'SELL'; entry: number; sl: number; tp: number; rr: number; etf?: string; time: number; grade?: string; setupType?: string } | null;
}
type Filter = 'all' | 'trade' | 'wait' | 'watch';
const RANK: Record<string, number> = { EXECUTE: 0, WAIT_FOR_TRIGGER: 1, WATCH_ONLY: 2, VETOED: 3 };
const CACHE_MS = 24 * 3600 * 1000;
const POLL_MS = 30000;
const DOT: Record<string, string> = { ok: 'bg-emerald-400', warn: 'bg-amber-400', wait: 'bg-slate-500', veto: 'bg-rose-400' };
const GRADE_TONE: Record<string, string> = { 'A+': 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', A: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30',
  B: 'bg-gold-500/15 text-gold-200 ring-gold-500/30', C: 'bg-amber-500/10 text-amber-200 ring-amber-500/25', D: 'bg-white/[0.04] text-slate-400 ring-line',
  WAIT: 'bg-white/[0.04] text-slate-400 ring-line' };

function Price({ p }: { p: PairSummary }) {
  const live = useLivePrice(p.symbol);
  const v = live?.price ?? p.price;
  return <span className="font-mono tabular-nums text-slate-100">{v ? v.toFixed(p.decimals ?? 5) : '—'}</span>;
}

function MyLot({ id, lang }: { id: string; lang: Language }) {
  const z = useMySizing(id);
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  if (!z) return null;
  return z.status === 'ok'
    ? <span className="font-mono text-gold-200">{z.lots} lot</span>
    : <span className="text-slate-500" title={z.reason}>{z.riskUsd == null && /risk/i.test(z.reason ?? '') ? t('lot: set your risk ↑', 'lot : réglez votre risque ↑', 'اللوت: حدد الريسك ↑') : t('lot unavailable', 'lot indisponible', 'اللوت ما متوفرش')}</span>;
}

export function PairsOverview({ lang, onOpenChart }: { lang: Language; onOpenChart: (symbol: string) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [pairs, setPairs] = useState<PairSummary[]>(() => readCache<PairSummary[]>('dash', 'overview', CACHE_MS) ?? []);
  const [ageSec, setAgeSec] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    let stop = false;
    const load = () => {
      if (document.hidden) return;
      apiJson<{ pairs: PairSummary[]; ageSec: number | null }>('/api/smc/overview').then(r => {
        if (stop) return;
        if (r.pairs?.length) { setPairs(r.pairs); writeCache('dash', 'overview', r.pairs); }
        setAgeSec(r.ageSec);
      }).catch(() => {});
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const word = (d?: string) => ({ EXECUTE: t('Trade', 'Trade', 'صفقة'), WAIT_FOR_TRIGGER: t('Waiting', 'En attente', 'كيتسنا'), WATCH_ONLY: t('Watching', 'En veille', 'كيراقب'),
    VETOED: t('No trade', 'Pas de trade', 'ما كاين') } as Record<string, string>)[d ?? ''] ?? '—';
  const tone = (d?: string) => ({ EXECUTE: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/40', WAIT_FOR_TRIGGER: 'bg-sky-500/10 text-sky-200 ring-sky-500/30',
    WATCH_ONLY: 'bg-white/[0.04] text-slate-300 ring-line', VETOED: 'bg-white/[0.02] text-slate-500 ring-line' } as Record<string, string>)[d ?? ''] ?? 'bg-white/[0.02] text-slate-500 ring-line';
  const isTrade = (p: PairSummary) => !!p.signal || p.decision === 'EXECUTE';
  // a waiting pair may also carry a watch note: it counts once, under "waiting"
  const isWatch = (p: PairSummary) => !isTrade(p) && p.decision !== 'WAIT_FOR_TRIGGER' && (p.decision === 'WATCH_ONLY' || !!p.watching);
  const counts = {
    trade: pairs.filter(isTrade).length,
    wait: pairs.filter(p => !isTrade(p) && p.decision === 'WAIT_FOR_TRIGGER').length,
    watch: pairs.filter(isWatch).length,
  };
  const shown = useMemo(() => [...pairs]
    .filter(p => filter === 'all' || (filter === 'trade' ? isTrade(p) : filter === 'wait' ? !isTrade(p) && p.decision === 'WAIT_FOR_TRIGGER'
      : isWatch(p)))
    .sort((a, b) => (isTrade(b) ? 1 : 0) - (isTrade(a) ? 1 : 0) || (RANK[a.decision ?? ''] ?? 9) - (RANK[b.decision ?? ''] ?? 9) || (b.gpa ?? 0) - (a.gpa ?? 0)),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [pairs, filter]);

  const tiles: [Filter, string, number, string][] = [
    ['trade', t('Trades now', 'Trades maintenant', 'صفقات دابا'), counts.trade, 'text-emerald-300'],
    ['wait', t('Waiting for trigger', 'Attendent le déclencheur', 'كيتسناو الزناد'), counts.wait, 'text-sky-300'],
    ['watch', t('Watching', 'En veille', 'كيراقبو'), counts.watch, 'text-slate-200'],
    ['all', t('All pairs', 'Toutes les paires', 'كل الأزواج'), pairs.length, 'text-gold-200'],
  ];
  const trendCell = (p: PairSummary) => (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px]">
      {(['W1', 'D1', 'H4'] as const).map(k => {
        const v = p.trend?.[k];
        return <span key={k} className={v === 1 ? 'text-emerald-300' : v === -1 ? 'text-rose-300' : 'text-slate-600'}>{k.replace('W1', 'W').replace('D1', 'D').replace('H4', '4H')}{v === 1 ? '▲' : v === -1 ? '▼' : '·'}</span>;
      })}
    </span>
  );
  const scoreCell = (p: PairSummary) => (
    <span className="inline-flex items-center gap-2 min-w-0">
      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ring-1 ring-inset ${GRADE_TONE[p.grade ?? 'D'] ?? GRADE_TONE.D}`}>{p.grade ?? 'D'}</span>
      <span className="relative h-1.5 w-14 rounded-full bg-white/[0.06]" aria-hidden="true">
        <span className={`absolute inset-y-0 start-0 rounded-full ${(p.gpa ?? 0) >= 100 ? 'bg-emerald-400' : (p.gpa ?? 0) >= 80 ? 'bg-emerald-500/80' : (p.gpa ?? 0) >= 65 ? 'bg-amber-400' : 'bg-slate-500'}`}
          style={{ width: `${Math.min(100, ((p.gpa ?? 0) / 120) * 100)}%` }} />
      </span>
      <span className="font-mono text-[11px] text-slate-400 tabular-nums">{p.gpa ?? 0}%</span>
    </span>
  );
  const agentsCell = (p: PairSummary) => (
    <span className="inline-flex items-center gap-1" title={t('The 2 agents: strategy & confirmation, then stop loss / take profit / lot', 'Les 2 agents : stratégie & confirmation, puis stop / take profit / lot', '2 agents: الستراتيجية والتأكيد، والستوب / الهدف / اللوت')}>
      {(p.agents ?? []).map((s, i) => <span key={i} className={`w-1.5 h-1.5 rounded-full ${DOT[s] ?? 'bg-slate-600'}`} />)}
    </span>
  );
  const tradeCell = (p: PairSummary) => {
    const s = p.signal;
    if (!s) return <span className="text-slate-600">—</span>;
    const d = p.decimals ?? 5;
    return (
      <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[11px]">
        <span className={`font-bold ${s.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{s.direction} {s.entry.toFixed(d)}</span>
        <span className="text-rose-300/90">SL {s.sl.toFixed(d)}</span>
        <span className="text-emerald-300/90">TP {s.tp.toFixed(d)}</span>
        <span className="text-slate-400">1:{s.rr}</span>
        <MyLot id={s.id} lang={lang} />
      </span>
    );
  };

  return (
    <section className="rounded-2xl border glass p-4 sm:p-5" aria-labelledby="overview-title">
      <header className="flex items-center justify-between gap-3 mb-3">
        <h3 id="overview-title" className="flex items-center gap-2.5 text-sm font-semibold text-white">
          <span className="icon-tile w-8 h-8 text-gold-400" aria-hidden="true"><Activity className="w-4 h-4" /></span>
          {t('Market overview', 'Vue du marché', 'نظرة على السوق')}
        </h3>
        <span className="flex items-center gap-2">
          <span className="hidden sm:inline text-[11px] text-slate-500">{ageSec != null ? (ageSec < 120 ? t('updated just now', 'à jour', 'محدث دابا') : `${t('updated', 'mis à jour', 'محدث')} ${Math.round(ageSec / 60)} min`) : ''}</span>
          {/* my risk per trade, right here: every pair's lot is calculated from it */}
          <RiskInline lang={lang} />
        </span>
      </header>

      {/* the counters: a tap filters the list */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3" role="tablist" aria-label={t('Filter', 'Filtre', 'فيلتر')}>
        {tiles.map(([f, label, n, c]) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
            className={`rounded-xl border px-3 py-2.5 text-start cursor-pointer transition-colors ${filter === f ? 'border-gold-500/50 bg-gold-500/[0.07]' : 'border-line bg-surface hover:border-gold-500/30'}`}>
            <span className={`block font-mono text-xl font-semibold tabular-nums ${c}`}>{n}</span>
            <span className="block text-[11px] text-slate-400 leading-tight">{label}</span>
          </button>
        ))}
      </div>

      {pairs.length === 0 && <div className="h-40 rounded-xl bg-white/[0.03] animate-pulse" aria-busy="true" aria-label={t('Reading the pairs…', 'Lecture des paires…', 'كيقرا الأزواج…')} />}
      {pairs.length > 0 && shown.length === 0 && <p className="py-6 text-center text-xs text-slate-500">{t('No pair in this group right now.', 'Aucune paire dans ce groupe pour le moment.', 'حتى زوج ف هاد المجموعة دابا.')}</p>}

      {/* desktop: one table */}
      {shown.length > 0 && (
        <div className="hidden md:block overflow-hidden rounded-xl border border-line">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2 text-start font-medium">{t('Pair', 'Paire', 'الزوج')}</th>
                <th className="px-3 py-2 text-end font-medium">{t('Price', 'Prix', 'الثمن')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('Trend', 'Tendance', 'الترند')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('Score', 'Score', 'السكور')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('Agents', 'Agents', 'Agents')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('Status', 'Statut', 'الحالة')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('Trade', 'Trade', 'الصفقة')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(p => (
                <tr key={p.symbol} onClick={() => onOpenChart(p.symbol)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onOpenChart(p.symbol); }}
                  className={`border-t border-line cursor-pointer transition-colors hover:bg-white/[0.03] focus-visible:outline-2 focus-visible:outline-gold-400 ${isTrade(p) ? 'bg-emerald-500/[0.04]' : ''}`}>
                  <td className="px-3 py-2"><span className="inline-flex items-center gap-2 font-mono font-semibold text-white"><PairFlags symbol={p.symbol as any} size={16} />{p.symbol}</span></td>
                  <td className="px-3 py-2 text-end"><Price p={p} /></td>
                  <td className="px-3 py-2">{trendCell(p)}</td>
                  <td className="px-3 py-2">{scoreCell(p)}</td>
                  <td className="px-3 py-2">{agentsCell(p)}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap ${tone(isTrade(p) ? 'EXECUTE' : p.decision)}`}>
                      {word(isTrade(p) ? 'EXECUTE' : p.decision)}{!isTrade(p) && p.direction && p.decision !== 'VETOED' ? ` · ${p.direction}` : ''}
                    </span>
                  </td>
                  <td className="px-3 py-2">{tradeCell(p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* phone: one compact card per pair */}
      {shown.length > 0 && (
        <ul className="md:hidden space-y-1.5">
          {shown.map(p => (
            <li key={p.symbol}>
              <button type="button" onClick={() => onOpenChart(p.symbol)}
                className={`w-full text-start rounded-xl border px-3 py-2.5 cursor-pointer ${isTrade(p) ? 'border-emerald-500/40 bg-emerald-500/[0.05]' : 'border-line bg-surface'}`}>
                <span className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-2 font-mono text-sm font-semibold text-white"><PairFlags symbol={p.symbol as any} size={16} />{p.symbol}</span>
                  <span className="text-xs"><Price p={p} /></span>
                  <span className={`ms-auto px-1.5 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap ${tone(isTrade(p) ? 'EXECUTE' : p.decision)}`}>
                    {word(isTrade(p) ? 'EXECUTE' : p.decision)}
                  </span>
                </span>
                <span className="mt-1.5 flex items-center gap-3">{trendCell(p)}{scoreCell(p)}<span className="ms-auto">{agentsCell(p)}</span></span>
                {p.signal && <span className="mt-1.5 block">{tradeCell(p)}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
