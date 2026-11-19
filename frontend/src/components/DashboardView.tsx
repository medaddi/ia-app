import { readCache, writeCache } from '../cache';
import { markDataReady } from '../splash';
import React, { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Clock, Newspaper, Users } from 'lucide-react';
import { apiJson } from '../api';
import { Language, MarketAsset, NewsItem } from '../types';
import { tr } from './ui';
import { marketOpenNow } from '../instruments';
import { PairsOverview } from './PairsOverview';
import type { TeamSetup } from '../smcTeam';

/**
 * The dashboard: every pair's FXAlexG state at a glance (PairsOverview), the trades sent and their results, the market
 * clock and the news.
 */
const REFRESH_MS = 30000;
const DASH_CACHE_MS = 24 * 3600 * 1000;
const EASE = [0.22, 1, 0.36, 1] as const; // ease-out: fast start, soft landing

function sessionNow(nowMs: number) {
  const london = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', hour: '2-digit', hour12: false }).format(nowMs)) % 24;
  const name = london < 7 ? 'Asia' : london < 13 ? 'London' : london < 17 ? 'London / New York' : london < 22 ? 'New York' : 'Rollover';
  const s = nowMs / 1000;
  const left = (tf: number) => tf - (s % tf);
  return { name, h1: left(3600), h4: left(14400) };
}
const mmss = (sec: number) => {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), x = Math.floor(sec % 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(x).padStart(2, '0')}s`;
};

/** Fades and lifts its content in, `i` sets its place in the stagger. */
function Reveal({ i = 0, className = '', children }: { i?: number; className?: string; children: React.ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE, delay: reduce ? 0 : Math.min(i, 12) * 0.05 }}>
      {children}
    </motion.div>
  );
}

function Panel({ title, icon, right, className = '', children }: { title: React.ReactNode; icon: React.ReactNode; right?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={`h-full rounded-2xl border glass p-4 sm:p-5 ${className}`}>
      <header className="flex items-center justify-between gap-3 mb-4">
        <h3 className="flex items-center gap-2.5 text-sm font-semibold text-white"><span className="icon-tile w-8 h-8 text-gold-400" aria-hidden="true">{icon}</span>{title}</h3>
        {right}
      </header>
      {children}
    </section>
  );
}

function Chip({ kind, children }: { kind: 'open' | 'none'; children: React.ReactNode }) {
  const c = kind === 'open' ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' : 'bg-slate-500/10 text-slate-400 ring-slate-500/25';
  return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md ring-1 ring-inset text-[11px] font-medium whitespace-nowrap ${c}`}>{children}</span>;
}

export function DashboardView({ lang, username, onOpenChart }: { lang: Language; username?: string; onOpenChart: (symbol: string) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  // the last values this device saw (an earlier visit) are shown at once; the fresh ones replace them a moment later
  const kept = <T,>(k: string): T | null => readCache<T>('dash', k, DASH_CACHE_MS);
  const [assets, setAssets] = useState<MarketAsset[] | null>(() => kept<MarketAsset[]>('assets'));
  const [news, setNews] = useState<NewsItem[]>(() => kept<NewsItem[]>('news') ?? []);
  const [sent, setSent] = useState<TeamSetup[]>(() => kept<TeamSetup[]>('sent') ?? []);
  const [results, setResults] = useState<{ trades: number; wins: number; losses: number; breakeven: number; winRate: number | null; totalR: number } | null>(() => kept('results'));
  useEffect(() => { if (assets) markDataReady(); }, []);  // the cached screen is there: the intro can go
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    let stop = false;
    const load = async () => {
      if (document.hidden) return;
      try {
        // each part fills in as soon as its own answer arrives: the screen never waits for the slowest one
        apiJson<{ news: NewsItem[] }>('/api/news').then(n => { if (!stop) { setNews(n.news); writeCache('dash', 'news', n.news); } }).catch(() => {});
        apiJson<{ signals: TeamSetup[] }>('/api/smc/signals').then(g => { if (!stop) { setSent(g.signals); writeCache('dash', 'sent', g.signals); } }).catch(() => {});
        apiJson<{ all: { trades: number; wins: number; losses: number; breakeven: number; winRate: number | null; totalR: number } }>('/api/smc/results')
          .then(x => { if (!stop) { setResults(x.all); writeCache('dash', 'results', x.all); } }).catch(() => {});
        const a = await apiJson<{ assets: MarketAsset[] }>('/api/market/assets');
        if (stop) return;
        setAssets(a.assets);
        writeCache('dash', 'assets', a.assets);
        setError(null);
        markDataReady();
      } catch (e: any) {
        if (!stop) setError(e.message);
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    const clock = setInterval(() => setNowMs(Date.now()), 1000);
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { stop = true; clearInterval(id); clearInterval(clock); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  if (!assets) {
    return (
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-3" aria-busy="true" aria-label={t('Loading the dashboard', 'Chargement du tableau de bord', 'كيتحمل لوحة التحكم')}>
        {error ? <p className="col-span-full rounded-2xl border border-rose-500/30 bg-rose-500/5 p-6 text-sm text-rose-300">{error}</p>
          : Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-28 rounded-2xl border border-line bg-surface-2 animate-pulse" />)}
      </div>
    );
  }

  const session = sessionNow(nowMs);
  const open = marketOpenNow(new Date(nowMs));
  const upcoming = news.filter(n => new Date(n.publishedAt).getTime() > nowMs - 30 * 60000).sort((a, b) => a.publishedAt.localeCompare(b.publishedAt)).slice(0, 6);

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {/* Header */}
      <Reveal className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-400">{t('Trading desk', 'Desk de trading', 'مكتب التداول')}</p>
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight text-white">{t('Hello', 'Bonjour', 'مرحبا')}{username ? ` ${username}` : ''}</h2>
          <p className="text-xs text-slate-500 mt-0.5">{open ? t('Market open', 'Marché ouvert', 'السوق مفتوح') : t('Market closed', 'Marché fermé', 'السوق مغلق')} · {session.name}</p>
        </div>
      </Reveal>

      {/* Every pair's FXAlexG state at a glance: no need to open each one */}
      <Reveal i={1}>
        <PairsOverview lang={lang} onOpenChart={onOpenChart} />
      </Reveal>

      {/* What the pair teams sent (each setup once, to Telegram and the phone) */}
      <Reveal i={2}>
        <Panel icon={<Users className="w-4 h-4" />} title={t('Results & sent trades', 'Résultats & trades envoyés', 'النتائج والصفقات المرسلة')}
          right={<span className="text-[11px] text-slate-500">{t('signals, not advice', 'signaux, pas un conseil', 'إشارات، ماشي نصيحة')}</span>}>
          {/* the teams' REAL results: each setup sent, followed by the trade manager to its end */}
          <div className="mb-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            {[
              [t('Closed trades', 'Trades clôturés', 'صفقات سدات'), results ? String(results.trades) : '—', 'text-white'],
              [t('Win rate', 'Taux de réussite', 'نسبة الربح'), results?.winRate != null ? `${results.winRate} %` : '—', 'text-gold-200'],
              [t('Won · BE · lost', 'Gagnés · BE · perdus', 'ربح · BE · خسارة'), results ? `${results.wins} · ${results.breakeven} · ${results.losses}` : '—', 'text-slate-200'],
              [t('Result', 'Résultat', 'النتيجة'), results ? `${results.totalR >= 0 ? '+' : ''}${results.totalR}R` : '—', results && results.totalR < 0 ? 'text-rose-300' : 'text-emerald-300'],
            ].map(([label, value, tone]) => (
              <div key={label} className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
                <div className={`mt-1 font-mono text-sm font-semibold ${tone}`}>{value}</div>
              </div>
            ))}
          </div>
          {sent.length === 0 ? <p className="text-xs text-slate-500">{t('No trade sent yet.', 'Aucun trade envoyé pour le moment.', 'حتى صفقة ما تصيفطات باقي.')}</p> : (
            <ul className="space-y-1.5">
              {sent.slice(0, 8).map(x => {
                const dec = x.symbol === 'XAU/USD' ? 2 : 5;
                return (
                  <li key={x.id}>
                    <button type="button" onClick={() => onOpenChart(x.symbol!)} className="w-full flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border border-line bg-surface px-3 py-2 text-xs font-mono text-start cursor-pointer hover:border-gold-500/40">
                      <span className="text-slate-500">{new Date(x.time * 1000).toISOString().slice(5, 16).replace('T', ' ')}</span>
                      <span className="text-white font-semibold">{x.symbol}</span>
                      <span className="text-gold-300">{x.strategy}</span>
                      <span className={x.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{x.direction} {x.entry.toFixed(dec)}</span>
                      <span className="text-slate-400">SL {x.sl.toFixed(dec)} · TP {x.tp.toFixed(dec)} · 1:{x.rr}</span>
                      <span className={`ms-auto ${x.outcome === 'WIN' ? 'text-emerald-300' : x.outcome === 'LOSS' ? 'text-rose-300' : x.status === 'OPEN' ? 'text-sky-300' : 'text-slate-400'}`}>
                        {x.status === 'CLOSED' ? `${x.outcome === 'WIN' ? t('won', 'gagné', 'ربح') : x.outcome === 'LOSS' ? t('lost', 'perdu', 'خسارة') : 'BE'} ${x.resultR != null ? `${x.resultR >= 0 ? '+' : ''}${x.resultR.toFixed(2)}R` : ''}`
                          : x.status === 'OPEN' ? t('in trade', 'en cours', 'خدامة') : x.status === 'EXPIRED' ? t('expired', 'expiré', 'سالا') : x.status === 'MISSED' ? t('missed', 'raté', 'فاتت') : t('pending', 'en attente', 'كتسنا')}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </Reveal>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Market clock */}
        <Reveal i={2} className="lg:col-span-5">
          <Panel icon={<Clock className="w-4 h-4" />} title={t('Market clock', 'Horloge du marché', 'ساعة السوق')}
            right={<Chip kind={open ? 'open' : 'none'}>{open ? t('Open', 'Ouvert', 'مفتوح') : t('Closed', 'Fermé', 'مغلق')}</Chip>}>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('Session', 'Session', 'الجلسة')}</div>
                <div className="mt-1 text-sm font-semibold text-gold-200">{session.name}</div>
              </div>
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('H1 close', 'Clôture H1', 'إغلاق H1')}</div>
                <div className="mt-1 font-mono text-sm text-white tabular-nums">{mmss(session.h1)}</div>
              </div>
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('H4 close', 'Clôture H4', 'إغلاق H4')}</div>
                <div className="mt-1 font-mono text-sm text-white tabular-nums">{mmss(session.h4)}</div>
              </div>
            </div>
          </Panel>
        </Reveal>

        {/* Next high-impact news */}
        <Reveal i={3} className="lg:col-span-7">
          <Panel icon={<Newspaper className="w-4 h-4" />} title={t('High-impact news', 'News à fort impact', 'أخبار قوية')}>
            {upcoming.length === 0 ? <p className="text-xs text-slate-500">{t('Nothing scheduled', 'Rien de prévu', 'ما كاين والو')}</p> : (
              <ul className="space-y-1.5 text-xs">
                {upcoming.map(n => (
                  <li key={n.id} className={`flex items-center gap-2 min-w-0 ${n.isLockoutEvent ? 'text-amber-300' : 'text-slate-300'}`}>
                    <span className="font-mono text-slate-500 shrink-0">{n.publishedAt.slice(5, 16).replace('T', ' ')}</span>
                    <span className="truncate" title={n.title}>{n.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>
      </div>
    </div>
  );
}
