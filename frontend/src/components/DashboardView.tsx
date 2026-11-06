import { markDataReady } from '../splash';
import React, { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Clock, Newspaper, Radar, Users } from 'lucide-react';
import { apiJson } from '../api';
import { Language, MarketAsset, NewsItem } from '../types';
import { tr } from './ui';
import { useLivePrice } from '../livePrices';
import { marketOpenNow } from '../instruments';
import { PairFlags } from './PairFlags';
import type { TeamSetup } from '../smcTeam';

/**
 * The dashboard: every pair's live price and 24 h move, the setups the pair teams sent, the market clock and the news.
 */
const REFRESH_MS = 30000;
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

function LivePriceText({ symbol, fallback, decimals }: { symbol: string; fallback: number; decimals: number }) {
  const live = useLivePrice(symbol);
  const p = live?.price ?? fallback;
  const prev = React.useRef(p);
  const dir = p > prev.current ? 'text-emerald-300' : p < prev.current ? 'text-rose-300' : 'text-slate-200';
  React.useEffect(() => { prev.current = p; }, [p]);
  return <div className={`font-mono text-lg tabular-nums transition-colors duration-300 ${dir}`}>{p ? p.toFixed(decimals) : '—'}</div>;
}

export function DashboardView({ lang, username, onOpenChart }: { lang: Language; username?: string; onOpenChart: (symbol: string) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [assets, setAssets] = useState<MarketAsset[] | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sent, setSent] = useState<TeamSetup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    let stop = false;
    const load = async () => {
      if (document.hidden) return;
      try {
        const [a, n, g] = await Promise.all([apiJson<{ assets: MarketAsset[] }>('/api/market/assets'), apiJson<{ news: NewsItem[] }>('/api/news').catch(() => ({ news: [] as NewsItem[] })),
          apiJson<{ signals: TeamSetup[] }>('/api/smc/signals').catch(() => ({ signals: [] as TeamSetup[] }))]);
        if (stop) return;
        setAssets(a.assets);
        setNews(n.news);
        setSent(g.signals);
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

      {/* Pairs */}
      <Reveal i={1}>
        <Panel icon={<Radar className="w-4 h-4" />} title={t('Pairs', 'Paires', 'الأزواج')}>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {assets.map((m, i) => {
              const up = m.change24h >= 0;
              return (
                <motion.div key={m.symbol} role="button" tabIndex={0} onClick={() => onOpenChart(m.symbol)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenChart(m.symbol); } }}
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: EASE, delay: Math.min(i, 9) * 0.04 }}
                  className="text-left rounded-xl border border-line bg-surface p-3.5 cursor-pointer transition-[border-color,transform,background-color] duration-200 hover:-translate-y-0.5 hover:border-gold-500/40 focus-visible:outline-2 focus-visible:outline-gold-400">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 font-mono font-semibold text-white"><PairFlags symbol={m.symbol as any} size={18} />{m.symbol}</div>
                      <LivePriceText symbol={m.symbol} fallback={m.price} decimals={m.decimalPlaces} />
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Chip kind={m.isMarketOpen ? 'open' : 'none'}>{m.isMarketOpen ? t('Open', 'Ouvert', 'مفتوح') : t('Closed', 'Fermé', 'مغلق')}</Chip>
                      <span className={`font-mono text-xs tabular-nums ${up ? 'text-emerald-400' : 'text-rose-400'}`}>{up ? '▲' : '▼'} {up ? '+' : ''}{m.change24h.toFixed(2)}%</span>
                    </div>
                  </div>
                  <div className="mt-2 flex justify-between font-mono text-[11px] text-slate-500">
                    <span>24h H {m.high24h ? m.high24h.toFixed(m.decimalPlaces) : '—'}</span>
                    <span>L {m.low24h ? m.low24h.toFixed(m.decimalPlaces) : '—'}</span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </Panel>
      </Reveal>

      {/* What the pair teams sent (each setup once, to Telegram and the phone) */}
      <Reveal i={2}>
        <Panel icon={<Users className="w-4 h-4" />} title={t('Team setups', 'Setups des équipes', 'سيتابات الفرق')}
          right={<span className="text-[11px] text-slate-500">{t('research, not advice', 'recherche, pas un conseil', 'بحث، ماشي نصيحة')}</span>}>
          {sent.length === 0 ? <p className="text-xs text-slate-500">{t('No setup has passed the 7 questions yet.', 'Aucun setup n’a encore passé les 7 questions.', 'حتى سيتاب ما دوز الأسئلة 7 باقي.')}</p> : (
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
