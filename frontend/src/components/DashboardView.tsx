import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChartSpline, Clock, Flame, Newspaper, Radar, ShieldAlert, Target, Trophy, Wallet } from 'lucide-react';
import { apiJson } from '../api';
import { Language } from '../types';
import { fmtMoney, fmtR, tr } from './ui';
import type { Stats, Today, Trade } from './AccountView';
import { strategyKind } from '../instruments';

// ---------------------------------------------------------------- API shape (/api/dashboard)

interface Day { day: string; value: number; trades: number; wins: number; losses: number }
interface Days {
  days: Day[]; profitDays: number; lossDays: number; flatDays: number; dayWinRate: number | null; bestDay: Day | null; worstDay: Day | null;
  avgProfitDay: number | null; avgLossDay: number | null; streak: number; today: number; week: number; month: number;
}
interface Edge { avgWin: number | null; avgLoss: number | null; expectancy: number | null; expectancyR: number | null; payoff: number | null;
  byPair: Record<string, { pnl: number; trades: number; wins: number }> }
interface SignalStats { closed: number; wins: number; losses: number; winRate: number | null; totalR: number; avgR: number | null; profitFactor: number | null;
  open: number; bestR: number | null; worstR: number | null;
  bySymbol: Record<string, { closed: number; wins: number; losses: number; totalR: number; winRate: number | null }> }
interface SignalRow { id: string; symbol: string; direction: string; state: string; outcome: string | null; rMultiple: number | null; signalTime: number }
interface MarketRow {
  loading?: boolean;  // first analysis still running after a cold start
  symbol: string; entryTf: string; price: number; decimals: number; status: string; score: number; bias: string;
  headline: string; isOpen: boolean; dataOk: boolean; dataReason: string; newsBlocked: boolean;
  setup: { direction: string; entry: number; sl: number; target: number; rr: number | null; state: string; outcome: string | null; r: number | null } | null;
  lastTrade: { state: string; outcome: string | null; r: number | null } | null;
  trend: { weekly?: string | null; daily?: string | null; h4?: string | null; h1?: string | null };
  liveGrade?: { score: number; grade: string } | null;
}
interface NewsRow { id: string; title: string; publishedAt: string; isLockoutEvent: boolean }
interface Dashboard {
  generatedAt: string;
  me: { username: string; riskUsd: number | null; stats: Stats; today: Today; days: Days; edge: Edge; openTrades: Trade[] };
  strategy: { stats: SignalStats; days: Days; recent: SignalRow[] };
  markets: MarketRow[];
  complete?: boolean;
  news: NewsRow[];
}

const REFRESH_MS = 3000; // live enough for a dashboard; the chart page is the 1 s view
const WARMUP_MS = 1500; // while some pairs are still being analysed
const EASE = [0.22, 1, 0.36, 1] as const; // ease-out: fast start, soft landing
const RUNNING = ['OPEN', 'PENDING', 'TP1_HIT', 'TP2_HIT'];
type Mode = 'me' | 'strategy';

// ---------------------------------------------------------------- formatting

const round2 = (v: number) => Math.round(v * 100) / 100;
const signed = (v: number, mode: Mode) => (mode === 'me' ? `${v > 0 ? '+' : ''}${fmtMoney(round2(v))}` : fmtR(round2(v)));
const r2 = (v: number | null | undefined) => fmtR(v === null || v === undefined ? v : round2(v));
const tone = (v: number | null | undefined) => (v === null || v === undefined || v === 0 ? 'text-slate-300' : v > 0 ? 'text-emerald-400' : 'text-rose-400');
// Forex trades are set & forget (one 3R target): TP1 / TP2 are progress marks, the trade is still running
const stateLabel = (symbol: string, state: string) =>
  symbol !== 'XAU/USD' && (state === 'TP1_HIT' || state === 'TP2_HIT') ? `OPEN · ${state === 'TP1_HIT' ? '1R' : '2R'} ✓` : state;

/** Forex session from the London clock, and the time left before the next H1 / H4 candle close. */
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

// ---------------------------------------------------------------- motion helpers

/** Number that counts from its previous value to the new one (instant when the user prefers reduced motion). */
function useCountUp(target: number, ms = 700) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (reduce) { setV(target); from.current = target; return; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      setV(a + (target - a) * e);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, reduce, ms]);
  return v;
}

function Counter({ value, format }: { value: number; format: (v: number) => string }) {
  return <>{format(useCountUp(value))}</>;
}

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
    <section className={`h-full rounded-2xl border border-line bg-surface-2/80 p-4 sm:p-5 ${className}`}>
      <header className="flex items-center justify-between gap-3 mb-4">
        <h3 className="flex items-center gap-2.5 text-sm font-semibold text-white"><span className="icon-tile w-8 h-8 text-gold-400" aria-hidden="true">{icon}</span>{title}</h3>
        {right}
      </header>
      {children}
    </section>
  );
}

function Chip({ kind, children }: { kind: 'signal' | 'watch' | 'none' | 'bull' | 'bear' | 'warn'; children: React.ReactNode }) {
  const c = {
    signal: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30', watch: 'bg-gold-500/15 text-gold-200 ring-gold-500/30',
    none: 'bg-slate-500/10 text-slate-400 ring-slate-500/25', bull: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25',
    bear: 'bg-rose-500/10 text-rose-300 ring-rose-500/25', warn: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  }[kind];
  return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md ring-1 ring-inset text-[11px] font-medium whitespace-nowrap ${c}`}>{children}</span>;
}

// ---------------------------------------------------------------- charts

/** Win rate as a ring; the number is written in the middle so the ring is never the only carrier. */
function Ring({ pct, size = 64 }: { pct: number | null; size?: number }) {
  const reduce = useReducedMotion();
  const r = (size - 8) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct ?? 0));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={6} className="stroke-surface-3" />
      <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={6} strokeLinecap="round"
        className={p >= 50 ? 'stroke-emerald-500' : 'stroke-gold-400'} strokeDasharray={c}
        initial={reduce ? false : { strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - p / 100) }} transition={{ duration: 0.9, ease: EASE }} />
    </svg>
  );
}

function EquityChart({ days, mode, lang }: { days: Day[]; mode: Mode; lang: Language }) {
  const reduce = useReducedMotion();
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const pts = useMemo(() => { let eq = 0; return days.map(d => ({ ...d, eq: (eq += d.value) })); }, [days]);
  if (pts.length < 2) {
    return <p className="text-xs text-slate-500 py-14 text-center">{tr(lang, 'The curve appears after two trading days with closed results.', 'La courbe apparaît après deux jours de trading avec des résultats clôturés.', 'المنحنى كيبان من بعد جوج أيام فيهم نتائج مسدودة.')}</p>;
  }
  const W = 640, H = 230, padL = 56, padR = 12, padT = 14, padB = 26;
  const vals = [0, ...pts.map(p => p.eq)];
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const x = (i: number) => padL + (i / (pts.length - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - min) / span) * (H - padT - padB);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.eq).toFixed(1)}`).join(' ');
  const area = `${line} L${x(pts.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const up = pts[pts.length - 1].eq >= 0;
  const h = hover !== null ? pts[hover] : null;
  const onMove = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.max(0, Math.min(pts.length - 1, Math.round(((px - padL) / (W - padL - padR)) * (pts.length - 1)))));
  };
  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full h-60 touch-none" role="img"
        aria-label={tr(lang, 'Cumulative result per trading day', 'Résultat cumulé par jour de trading', 'النتيجة التراكمية حسب اليوم')}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="eqFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={up ? '#16C784' : '#EA3943'} stopOpacity={0.28} />
            <stop offset="100%" stopColor={up ? '#16C784' : '#EA3943'} stopOpacity={0} />
          </linearGradient>
        </defs>
        {[min, (min + max) / 2, max].map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="stroke-line" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-500 text-[10px] font-mono">{signed(t, mode)}</text>
          </g>
        ))}
        <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} className="stroke-slate-500" strokeDasharray="3 3" strokeWidth={1} />
        <motion.path d={area} fill="url(#eqFill)" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.5 }} />
        <motion.path key={`${mode}-${pts.length}`} d={line} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
          className={up ? 'stroke-emerald-500' : 'stroke-rose-500'}
          initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: EASE }} />
        <text x={padL} y={H - 6} className="fill-slate-500 text-[10px] font-mono">{pts[0].day}</text>
        <text x={W - padR} y={H - 6} textAnchor="end" className="fill-slate-500 text-[10px] font-mono">{pts[pts.length - 1].day}</text>
        {h && hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} className="stroke-gold-400/60" strokeWidth={1} />
            <circle cx={x(hover)} cy={y(h.eq)} r={4.5} className={`${h.eq >= 0 ? 'fill-emerald-500' : 'fill-rose-500'} stroke-surface-2`} strokeWidth={2} />
          </g>
        )}
      </svg>
      {h && hover !== null && (
        <div className="absolute top-2 pointer-events-none rounded-lg border border-line bg-canvas/95 px-2.5 py-1.5 text-xs font-mono shadow-lg"
          style={{ left: `clamp(0px, calc(${(x(hover) / W) * 100}% - 70px), calc(100% - 150px))` }}>
          <div className="text-slate-400">{h.day} · {h.trades} trade(s)</div>
          <div className="text-slate-200">{tr(lang, 'Day', 'Jour', 'اليوم')} <span className={tone(h.value)}>{signed(h.value, mode)}</span></div>
          <div className="text-slate-200">{tr(lang, 'Total', 'Total', 'المجموع')} <span className={tone(h.eq)}>{signed(h.eq, mode)}</span></div>
        </div>
      )}
    </div>
  );
}

/** Result of each of the last 30 trading days: profit above the zero line, loss below (position and sign carry the polarity). */
function DailyBars({ days, mode, lang }: { days: Day[]; mode: Mode; lang: Language }) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);
  const last = days.slice(-30);
  if (!last.length) return <p className="text-xs text-slate-500 py-10 text-center">{tr(lang, 'No closed day yet.', 'Aucun jour clôturé.', 'ما كاين حتى نهار مسدود.')}</p>;
  const W = 640, H = 170, pad = 4;
  const maxUp = Math.max(...last.map(d => d.value), 0), maxDown = Math.max(...last.map(d => -d.value), 0);
  const mid = 8 + (H - 16) * (maxUp / ((maxUp + maxDown) || 1)); // the zero line sits where the data needs it
  const scale = (H - 16) / ((maxUp + maxDown) || 1);
  const slot = (W - pad * 2) / last.length;
  const bw = Math.max(3, Math.min(18, slot - 2));
  const h = hover !== null ? last[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-44" role="img" aria-label={tr(lang, 'Result per day', 'Résultat par jour', 'النتيجة ديال كل نهار')} onPointerLeave={() => setHover(null)}>
        <line x1={0} x2={W} y1={mid} y2={mid} className="stroke-line-2" strokeWidth={1} />
        {last.map((d, i) => {
          const len = Math.max(Math.abs(d.value) * scale, 1.5);
          const cx = pad + i * slot + slot / 2;
          return (
            <g key={d.day} onPointerEnter={() => setHover(i)}>
              <rect x={pad + i * slot} y={0} width={slot} height={H} fill="transparent" />
              <motion.rect x={cx - bw / 2} y={d.value >= 0 ? mid - len : mid} width={bw} height={len} rx={Math.min(4, bw / 2)}
                className={`${d.value > 0 ? 'fill-emerald-500' : d.value < 0 ? 'fill-rose-500' : 'fill-slate-500'} transition-opacity duration-150 ${hover === null || hover === i ? 'opacity-100' : 'opacity-50'}`}
                style={{ transformBox: 'fill-box', transformOrigin: d.value >= 0 ? 'bottom' : 'top' }}
                initial={reduce ? false : { scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ duration: 0.45, ease: EASE, delay: reduce ? 0 : i * 0.018 }} />
            </g>
          );
        })}
      </svg>
      {h && hover !== null && (
        <div className="absolute top-1 pointer-events-none rounded-lg border border-line bg-canvas/95 px-2.5 py-1.5 text-xs font-mono shadow-lg"
          style={{ left: `clamp(0px, calc(${((pad + hover * slot + slot / 2) / W) * 100}% - 70px), calc(100% - 150px))` }}>
          <div className="text-slate-400">{h.day}</div>
          <div className={tone(h.value)}>{signed(h.value, mode)}</div>
          <div className="text-slate-500">{h.trades} trade(s) · {h.wins}W / {h.losses}L</div>
        </div>
      )}
    </div>
  );
}

/** This month's trading days (Mon–Fri), each cell shows its signed result. */
function MonthCalendar({ days, mode, lang }: { days: Day[]; mode: Mode; lang: Language }) {
  const reduce = useReducedMotion();
  const byDay = new Map(days.map(d => [d.day, d]));
  const now = new Date();
  const y = now.getUTCFullYear(), m = now.getUTCMonth();
  const daysIn = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cells: (string | null)[] = [];
  const lead = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7; // Monday = 0
  for (let i = 0; i < Math.min(lead, 5); i++) cells.push(null);
  for (let d = 1; d <= daysIn; d++) {
    if ((new Date(Date.UTC(y, m, d)).getUTCDay() + 6) % 7 < 5) cells.push(`${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`);
  }
  const maxAbs = Math.max(...cells.map(k => (k && byDay.get(k) ? Math.abs(byDay.get(k)!.value) : 0)), 1e-9);
  const today = now.toISOString().slice(0, 10);
  const labels = lang === 'fr' ? ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven'] : lang === 'ar' ? ['إثنين', 'ثلاثاء', 'أربعاء', 'خميس', 'جمعة'] : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
  return (
    <div>
      <div className="grid grid-cols-5 gap-1.5 mb-1.5">{labels.map(l => <div key={l} className="text-[10px] uppercase tracking-wider text-slate-500 text-center">{l}</div>)}</div>
      <div className="grid grid-cols-5 gap-1.5">
        {cells.map((k, i) => {
          if (!k) return <div key={`e${i}`} />;
          const d = byDay.get(k);
          const a = d ? 0.16 + 0.54 * (Math.abs(d.value) / maxAbs) : 0;
          const bg = !d ? undefined : d.value > 0 ? `rgba(22,199,132,${a})` : d.value < 0 ? `rgba(234,57,67,${a})` : 'rgba(141,150,166,0.15)';
          return (
            <motion.div key={k} title={d ? `${k} · ${signed(d.value, mode)} · ${d.trades} trade(s)` : k}
              initial={reduce ? false : { opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3, delay: reduce ? 0 : i * 0.012 }}
              className={`rounded-lg border px-1.5 py-1 min-h-[48px] flex flex-col justify-between ${k === today ? 'border-gold-500/70 ring-1 ring-gold-500/30' : 'border-line'}`}
              style={{ background: bg }}>
              <span className="text-[10px] text-slate-400 font-mono">{Number(k.slice(8))}</span>
              {d && <span className="text-[11px] font-mono font-semibold text-white tabular-nums truncate">{d.value > 0 ? '▲' : d.value < 0 ? '▼' : ''}{signed(d.value, mode).replace(/^[+-]/, '')}</span>}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

/** Result per pair as bars from a zero line (gains right, losses left). */
function PairBars({ rows, mode }: { rows: { key: string; value: number; sub: string }[]; mode: Mode }) {
  const reduce = useReducedMotion();
  const max = Math.max(...rows.map(r => Math.abs(r.value)), 1e-9);
  return (
    <ul className="space-y-2">
      {rows.map((r, i) => (
        <li key={r.key} className="grid grid-cols-[72px_1fr_auto] items-center gap-2 text-xs">
          <span className="font-mono text-slate-300">{r.key}</span>
          <div className="relative h-2.5 rounded-full bg-surface-3/60">
            <div className="absolute inset-y-0 left-1/2 w-px bg-line-2" aria-hidden="true" />
            <motion.div className={`absolute inset-y-0 rounded-full ${r.value >= 0 ? 'left-1/2 bg-emerald-500' : 'right-1/2 bg-rose-500'}`}
              style={{ width: `${(Math.abs(r.value) / max) * 50}%`, transformOrigin: r.value >= 0 ? 'left' : 'right' }}
              initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.55, ease: EASE, delay: reduce ? 0 : i * 0.04 }} />
          </div>
          <span className="text-right"><span className={`font-mono ${tone(r.value)}`}>{signed(r.value, mode)}</span> <span className="text-slate-500">{r.sub}</span></span>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- page

export function DashboardView({ lang, onOpenChart }: { lang: Language; onOpenChart: (symbol: string) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('me');
  const [nowMs, setNowMs] = useState(Date.now());
  const picked = useRef(false);
  const completeRef = useRef(false);

  useEffect(() => {
    let stop = false, busy = false;
    const load = async () => {
      if (document.hidden || busy) return;
      busy = true;
      try {
        const d = await apiJson<Dashboard>('/api/dashboard');
        if (stop) return;
        setData(d);
        completeRef.current = d.complete !== false;
        setError(null);
        // Until the user has closed trades of their own, show what the strategies did
        if (!picked.current) { picked.current = true; if (!d.me.days.days.length && d.strategy.days.days.length) setMode('strategy'); }
      } catch (e: any) {
        if (!stop) setError(e.message);
      } finally {
        busy = false;
      }
    };
    // Faster refresh until every pair has its first analysis, then the normal pace
    let timer: ReturnType<typeof setTimeout>;
    const loop = async () => { await load(); if (!stop) timer = setTimeout(loop, completeRef.current ? REFRESH_MS : WARMUP_MS); };
    loop();
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener('visibilitychange', onVisible);
    const clock = setInterval(() => setNowMs(Date.now()), 1000);
    return () => { stop = true; clearTimeout(timer); clearInterval(clock); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  if (!data) {
    return (
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3" aria-busy="true" aria-label={t('Loading the dashboard', 'Chargement du tableau de bord', 'كيتحمل لوحة التحكم')}>
        {error ? <p className="col-span-full rounded-2xl border border-rose-500/30 bg-rose-500/5 p-6 text-sm text-rose-300">{error}</p>
          : Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-28 rounded-2xl border border-line bg-surface-2 animate-pulse" />)}
      </div>
    );
  }

  const { me, strategy } = data;
  const days = mode === 'me' ? me.days : strategy.days;
  const today = me.today;
  const todayValue = mode === 'me' ? today.pnl : days.today;
  const usedPct = today.limit ? Math.min(100, (-Math.min(0, today.pnl) / today.limit) * 100) : null;
  const age = Math.max(0, Math.round((nowMs - new Date(data.generatedAt).getTime()) / 1000));
  const session = sessionNow(nowMs);
  const ready = data.markets.filter(m => !m.loading);
  const anyOpen = ready.some(m => m.isOpen);
  const running = ready.filter(m => m.status === 'SIGNAL' && m.setup && RUNNING.includes(m.setup.state));
  const ss = strategy.stats, st = me.stats, edge = me.edge;
  const winRate = mode === 'me' ? st.winRate : ss.winRate;
  const pf = mode === 'me' ? st.profitFactor : ss.profitFactor;
  const pairRows = mode === 'me'
    ? Object.entries(edge.byPair).map(([k, b]) => ({ key: k, value: b.pnl, sub: `${b.trades}t` }))
    : Object.entries(ss.bySymbol).sort((a, b) => b[1].totalR - a[1].totalR).map(([k, b]) => ({ key: k, value: b.totalR, sub: `${b.closed}t · ${b.winRate ?? '—'}%` }));
  const profitShare = days.profitDays + days.lossDays ? (days.profitDays / (days.profitDays + days.lossDays)) * 100 : 0;
  const fmt = (v: number) => signed(v, mode);

  const tiles: { label: string; value: React.ReactNode; sub?: string; valueTone?: string }[] = [
    { label: t('This week', 'Cette semaine', 'هاد السيمانة'), value: <Counter value={days.week} format={fmt} />, valueTone: tone(days.week) },
    { label: t('This month', 'Ce mois', 'هاد الشهر'), value: <Counter value={days.month} format={fmt} />, valueTone: tone(days.month) },
    { label: t('Profit factor', 'Profit factor', 'معامل الربح'), value: pf ?? '—', valueTone: (pf ?? 0) >= 1 ? 'text-emerald-400' : 'text-rose-400',
      sub: mode === 'me' ? `${t('total', 'total', 'المجموع')} ${signed(st.totalPnl, 'me')}` : `${t('total', 'total', 'المجموع')} ${r2(ss.totalR)}` },
    mode === 'me'
      ? { label: t('Expectancy / trade', 'Espérance / trade', 'المتوقع لكل صفقة'), value: edge.expectancy !== null ? signed(edge.expectancy, 'me') : '—', valueTone: tone(edge.expectancy),
        sub: edge.expectancyR !== null ? `${r2(edge.expectancyR)} ${t('per trade', 'par trade', 'لكل صفقة')}` : undefined }
      : { label: t('Average / signal', 'Moyenne / signal', 'المعدل لكل إشارة'), value: r2(ss.avgR), valueTone: tone(ss.avgR) },
    mode === 'me'
      ? { label: t('Avg win / avg loss', 'Gain moy. / perte moy.', 'متوسط الربح / الخسارة'), value: edge.payoff !== null ? `${edge.payoff}×` : '—',
        sub: `${edge.avgWin !== null ? signed(edge.avgWin, 'me') : '—'} / ${edge.avgLoss !== null ? signed(edge.avgLoss, 'me') : '—'}` }
      : { label: t('Best / worst signal', 'Meilleur / pire signal', 'أحسن / أسوأ إشارة'), value: r2(ss.bestR), valueTone: tone(ss.bestR), sub: `${t('worst', 'pire', 'أسوأ')} ${r2(ss.worstR)}` },
    mode === 'me'
      ? { label: t('Max drawdown', 'Drawdown max', 'أقصى تراجع'), value: fmtMoney(st.maxDrawdown), valueTone: 'text-rose-300', sub: `${me.openTrades.length} ${t('open trade(s)', 'trade(s) ouvert(s)', 'صفقة مفتوحة')}` }
      : { label: t('Open signals', 'Signaux ouverts', 'إشارات مفتوحة'), value: ss.open, valueTone: 'text-gold-200', sub: t('followed until TP / SL', 'suivis jusqu’au TP / SL', 'كتتبع حتى TP / SL') },
  ];

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {/* Header */}
      <Reveal className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-gold-400">{t('Trading desk', 'Desk de trading', 'مكتب التداول')}</p>
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight text-white">{t('Hello', 'Bonjour', 'مرحبا')} {me.username}</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {t('Trading day', 'Jour de trading', 'يوم التداول')} {today.day} · {anyOpen ? t('market open', 'marché ouvert', 'السوق مفتوح') : t('market closed', 'marché fermé', 'السوق مغلق')}
            {me.riskUsd ? ` · ${t('risk', 'risque', 'المخاطرة')} $${me.riskUsd} / trade` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 text-xs font-mono ${age > 5 ? 'text-rose-300' : 'text-emerald-400'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${age > 5 ? 'bg-rose-400' : 'bg-emerald-400'}`} aria-hidden="true" />
            {age > 5 ? t('Stale', 'Ancien', 'قديم') : 'Live'} · {age}s
          </span>
          <div role="tablist" aria-label={t('Results shown', 'Résultats affichés', 'النتائج المعروضة')} className="relative flex items-center rounded-xl bg-surface border border-line p-1 text-xs">
            {(['me', 'strategy'] as Mode[]).map(k => (
              <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
                className={`relative h-8 px-3 rounded-lg font-medium cursor-pointer transition-colors duration-200 ${mode === k ? 'text-gold-100' : 'text-slate-400 hover:text-slate-100'}`}>
                {mode === k && <motion.span layoutId="dash-mode" className="absolute inset-0 rounded-lg bg-gold-500/15 ring-1 ring-gold-500/30" transition={{ duration: 0.25, ease: EASE }} />}
                <span className="relative">{k === 'me' ? t('My trades ($)', 'Mes trades ($)', 'صفقاتي ($)') : t('Strategies (R)', 'Stratégies (R)', 'الاستراتيجيات (R)')}</span>
              </button>
            ))}
          </div>
        </div>
      </Reveal>

      {/* Hero: today + session clock */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <Reveal i={1} className="lg:col-span-7">
          <section className="relative h-full overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-surface-2 via-surface-2 to-surface p-5">
            <div className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 rounded-full bg-gold-500/10 blur-3xl" aria-hidden="true" />
            <div className="relative flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500">{mode === 'me' ? t('My P&L today', 'Mon P&L du jour', 'الربح/الخسارة ديال اليوم') : t('Strategies today', 'Stratégies aujourd’hui', 'الاستراتيجيات اليوم')}</div>
                <div className={`mt-1 font-mono text-4xl sm:text-5xl font-semibold tabular-nums tracking-tight ${tone(todayValue)}`}>
                  <Counter value={todayValue} format={fmt} />
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
                  {todayValue >= 0 ? <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" /> : <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />}
                  {mode === 'me' ? `${today.trades} ${t('closed trade(s) today', 'trade(s) clôturé(s) aujourd’hui', 'صفقة مسدودة اليوم')}` : t('closed signals today', 'signaux clôturés aujourd’hui', 'إشارات مسدودة اليوم')}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Ring pct={winRate} size={76} />
                  <span className="absolute inset-0 flex items-center justify-center font-mono text-sm font-semibold text-white">{winRate !== null ? `${Math.round(winRate)}%` : '—'}</span>
                </div>
                <div className="text-xs">
                  <div className="text-slate-500">{t('Win rate', 'Taux de réussite', 'نسبة النجاح')}</div>
                  <div className="font-mono text-slate-200">{mode === 'me' ? `${st.wins}W / ${st.losses}L` : `${ss.wins}W / ${ss.losses}L`}</div>
                  <div className="text-slate-500">{mode === 'me' ? `${st.closed} ${t('closed', 'clôturés', 'مسدودة')}` : `${ss.closed} ${t('signals', 'signaux', 'إشارات')}`}</div>
                </div>
              </div>
            </div>
            {/* Daily loss limit as a bullet bar: the numbers are written next to it */}
            <div className="relative mt-5">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-slate-400 flex items-center gap-1.5"><ShieldAlert className="w-3.5 h-3.5 text-gold-500" aria-hidden="true" />{t('Daily loss limit', 'Perte journalière max', 'الخسارة اليومية القصوى')}</span>
                <span className="font-mono text-slate-300">
                  {today.limit ? `${fmtMoney(Math.max(0, -today.pnl))} / ${fmtMoney(today.limit)} · ${t('left', 'reste', 'باقي')} ${fmtMoney(today.remaining)}` : t('not set (Account page)', 'non définie (page Compte)', 'ما محددة (صفحة الحساب)')}
                </span>
              </div>
              <div className="h-2 rounded-full bg-surface-3/70 overflow-hidden" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(usedPct ?? 0)}
                aria-label={t('Daily loss limit used', 'Limite journalière utilisée', 'الحد اليومي المستعمل')}>
                <motion.div className={`h-full rounded-full ${(usedPct ?? 0) >= 100 ? 'bg-rose-500' : (usedPct ?? 0) >= 60 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                  initial={{ width: 0 }} animate={{ width: `${usedPct ?? 0}%` }} transition={{ duration: 0.7, ease: EASE }} />
              </div>
              {today.reached && <p className="mt-1.5 text-xs text-rose-300">{t('Limit reached: no new trade until 17:00 New York.', 'Limite atteinte : plus de trade jusqu’à 17:00 New York.', 'وصلتي للحد: ما كاين حتى صفقة حتى 17:00 نيويورك.')}</p>}
            </div>
          </section>
        </Reveal>

        <Reveal i={2} className="lg:col-span-5">
          <section className="h-full rounded-2xl border border-line bg-surface-2/80 p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2.5 text-sm font-semibold text-white"><span className="icon-tile w-8 h-8 text-gold-400" aria-hidden="true"><Clock className="w-4 h-4" /></span>{t('Market clock', 'Horloge du marché', 'ساعة السوق')}</h3>
              <Chip kind={anyOpen ? 'signal' : 'none'}>{anyOpen ? t('Open', 'Ouvert', 'مفتوح') : t('Closed', 'Fermé', 'مغلق')}</Chip>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('Session', 'Session', 'الجلسة')}</div>
                <div className="mt-1 text-sm font-semibold text-gold-200">{session.name}</div>
              </div>
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('Gold · H1 close', 'Or · clôture H1', 'الذهب · إغلاق H1')}</div>
                <div className="mt-1 font-mono text-sm text-white tabular-nums">{mmss(session.h1)}</div>
              </div>
              <div className="rounded-xl bg-surface border border-line p-2.5">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('Forex · H4 close', 'Forex · clôture H4', 'الفوركس · إغلاق H4')}</div>
                <div className="mt-1 font-mono text-sm text-white tabular-nums">{mmss(session.h4)}</div>
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1.5">{t('Running signals', 'Signaux en cours', 'إشارات جارية')}</div>
              {running.length === 0 ? <p className="text-xs text-slate-500">{t('None right now: the strategies are waiting for their setup.', 'Aucun pour l’instant : les stratégies attendent leur setup.', 'والو دابا: الاستراتيجيات كتسنى الإعداد ديالها.')}</p> : (
                <div className="flex flex-wrap gap-2">
                  {running.map(m => (
                    <button key={m.symbol} onClick={() => onOpenChart(m.symbol)}
                      className="group inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1.5 text-xs font-mono text-slate-200 cursor-pointer transition-all duration-200 hover:border-gold-500/60 hover:-translate-y-0.5">
                      <Flame className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                      <span className={m.setup!.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>{m.setup!.direction}</span> {m.symbol}
                      <span className="text-slate-500">{stateLabel(m.symbol, m.setup!.state)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </section>
        </Reveal>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {tiles.map((k, i) => (
          <Reveal key={k.label} i={3 + i}>
            <div className="h-full rounded-2xl border border-line bg-surface-2/80 p-4 transition-colors duration-200 hover:border-gold-500/30">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 truncate">{k.label}</div>
              <div className={`mt-1 font-mono text-xl font-semibold tabular-nums ${k.valueTone ?? 'text-white'}`}>{k.value}</div>
              {k.sub && <div className="mt-1 text-xs text-slate-500 truncate font-mono">{k.sub}</div>}
            </div>
          </Reveal>
        ))}
      </div>

      {/* Equity + profit/loss days */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <Reveal i={9} className="xl:col-span-8">
          <Panel icon={<ChartSpline className="w-4 h-4" />}
            title={mode === 'me' ? t('Equity curve ($, closed trades)', 'Courbe de capital ($, trades clôturés)', 'منحنى الرصيد ($، صفقات مسدودة)') : t('Strategies equity (R, closed signals)', 'Capital des stratégies (R, signaux clôturés)', 'منحنى الاستراتيجيات (R)')}>
            <EquityChart days={days.days} mode={mode} lang={lang} />
          </Panel>
        </Reveal>
        <Reveal i={10} className="xl:col-span-4">
          <Panel icon={<Trophy className="w-4 h-4" />} title={t('Profit days & loss days', 'Jours gagnants & perdants', 'أيام الربح وأيام الخسارة')}>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
                <div className="text-slate-400">{t('Profit days', 'Jours gagnants', 'أيام الربح')}</div>
                <div className="font-mono text-3xl font-semibold text-emerald-400">▲ <Counter value={days.profitDays} format={v => String(Math.round(v))} /></div>
                <div className="text-slate-500 font-mono">{t('avg', 'moy.', 'المعدل')} {days.avgProfitDay !== null ? fmt(days.avgProfitDay) : '—'}</div>
              </div>
              <div className="rounded-xl border border-rose-500/25 bg-rose-500/5 p-3">
                <div className="text-slate-400">{t('Loss days', 'Jours perdants', 'أيام الخسارة')}</div>
                <div className="font-mono text-3xl font-semibold text-rose-400">▼ <Counter value={days.lossDays} format={v => String(Math.round(v))} /></div>
                <div className="text-slate-500 font-mono">{t('avg', 'moy.', 'المعدل')} {days.avgLossDay !== null ? fmt(days.avgLossDay) : '—'}</div>
              </div>
            </div>
            {days.profitDays + days.lossDays > 0 && (
              <div className="mt-3 flex h-2 rounded-full overflow-hidden gap-0.5" aria-hidden="true">
                <motion.div className="bg-emerald-500 rounded-full" initial={{ width: 0 }} animate={{ width: `${profitShare}%` }} transition={{ duration: 0.7, ease: EASE }} />
                <motion.div className="bg-rose-500 rounded-full flex-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: 0.3 }} />
              </div>
            )}
            <dl className="mt-3 space-y-1.5 text-xs">
              {[
                [t('Day win rate', 'Jours gagnants %', 'نسبة الأيام الرابحة'), days.dayWinRate !== null ? `${days.dayWinRate}%` : '—', undefined],
                [t('Best day', 'Meilleur jour', 'أحسن نهار'), days.bestDay ? `${fmt(days.bestDay.value)} · ${days.bestDay.day.slice(5)}` : '—', tone(days.bestDay?.value)],
                [t('Worst day', 'Pire jour', 'أسوأ نهار'), days.worstDay ? `${fmt(days.worstDay.value)} · ${days.worstDay.day.slice(5)}` : '—', tone(days.worstDay?.value)],
                [t('Current streak', 'Série actuelle', 'السلسلة الحالية'), days.streak ? `${days.streak > 0 ? '▲' : '▼'} ${Math.abs(days.streak)} ${days.streak > 0 ? t('profit day(s)', 'jour(s) gagnant(s)', 'أيام ربح') : t('loss day(s)', 'jour(s) perdant(s)', 'أيام خسارة')}` : '—', tone(days.streak)],
                [t('Flat days', 'Jours neutres', 'أيام بلا نتيجة'), String(days.flatDays), undefined],
              ].map(([k, v, c]) => (
                <div key={k as string} className="flex items-center justify-between gap-2 border-t border-line pt-1.5">
                  <dt className="text-slate-500">{k}</dt><dd className={`font-mono ${c ?? 'text-slate-200'}`}>{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </Reveal>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <Reveal i={11} className="xl:col-span-7">
          <Panel icon={<Target className="w-4 h-4" />} title={t('Result per day · last 30 trading days', 'Résultat par jour · 30 derniers jours', 'النتيجة ديال كل نهار · آخر 30 يوم')}>
            <DailyBars days={days.days} mode={mode} lang={lang} />
          </Panel>
        </Reveal>
        <Reveal i={12} className="xl:col-span-5">
          <Panel icon={<CalendarDays className="w-4 h-4" />} title={t('This month', 'Ce mois', 'هاد الشهر')}>
            <MonthCalendar days={days.days} mode={mode} lang={lang} />
          </Panel>
        </Reveal>
      </div>

      {/* Live analysis */}
      <Reveal i={12}>
        <Panel icon={<Radar className="w-4 h-4" />} title={t('Live analysis', 'Analyse en direct', 'التحليل المباشر')}
          right={<span className="text-xs text-slate-500 hidden sm:inline">{t('Click a pair to open its chart', 'Cliquez une paire pour ouvrir son graphique', 'كليكي على زوج باش تحل الشارت')}</span>}>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {data.markets.map((m, i) => {
              if (m.loading) return (
                <div key={m.symbol} className="rounded-xl border border-line bg-surface p-3.5" aria-busy="true">
                  <div className="font-mono font-semibold text-white">{m.symbol} <span className="text-[10px] text-slate-500 font-normal">{m.entryTf}</span></div>
                  <div className="mt-2 h-3 w-24 rounded bg-surface-2 animate-pulse" />
                  <div className="mt-2 h-3 w-40 rounded bg-surface-2 animate-pulse" />
                  <div className="mt-2 text-[11px] text-slate-500">{t('Analysing…', 'Analyse en cours…', 'كيتحلل…')}</div>
                </div>
              );
              const f = (v: number) => v.toFixed(m.decimals);
              const trends = m.symbol === 'XAU/USD' ? [['H1', m.trend.h1]] : strategyKind(m.symbol) === 'rsi2' ? [['H4', m.trend.h4]] : [['W1', m.trend.weekly], ['D1', m.trend.daily], ['H4', m.trend.h4]];
              const live = !!m.setup && RUNNING.includes(m.setup.state);
              return (
                <motion.button key={m.symbol} onClick={() => onOpenChart(m.symbol)}
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: EASE, delay: Math.min(i, 9) * 0.04 }}
                  className={`text-left rounded-xl border p-3.5 cursor-pointer transition-[border-color,transform,background-color] duration-200 hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-gold-400 ${live ? 'border-emerald-500/40 bg-emerald-500/[0.04]' : 'border-line bg-surface hover:border-gold-500/40'}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-mono font-semibold text-white">{m.symbol} <span className="text-[10px] text-slate-500 font-normal">{m.entryTf}</span></div>
                      <div className="font-mono text-sm text-slate-300 tabular-nums">{m.price ? f(m.price) : '—'}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {!m.dataOk ? <Chip kind="warn">{t('No data', 'Pas de données', 'بلا معطيات')}</Chip>
                        : <Chip kind={m.status === 'SIGNAL' ? 'signal' : m.status === 'WATCH' ? 'watch' : 'none'}>{m.status === 'NO_TRADE' ? 'NO TRADE' : m.status}{m.setup ? ` · ${m.score}` : ''}</Chip>}
                      <div className="flex gap-1">
                        {trends.map(([k, v]) => <Chip key={k as string} kind={v === 'bullish' ? 'bull' : v === 'bearish' ? 'bear' : 'none'}>{k} {v === 'bullish' ? '▲' : v === 'bearish' ? '▼' : '–'}</Chip>)}
                        {m.newsBlocked && <Chip kind="warn"><Newspaper className="w-3 h-3" aria-hidden="true" />News</Chip>}
                      </div>
                    </div>
                  </div>
                  {m.setup ? (
                    <div className="mt-2.5 rounded-lg bg-canvas/60 border border-line px-2.5 py-1.5 font-mono text-xs">
                      <div className="flex items-center justify-between">
                        <span className={m.setup.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>{m.setup.direction === 'BUY' ? '▲' : '▼'} {m.setup.direction} {f(m.setup.entry)}</span>
                        <span className={live ? 'text-gold-300' : tone(m.setup.r)}>{live ? stateLabel(m.symbol, m.setup.state) : `${m.setup.outcome ?? m.setup.state} ${r2(m.setup.r)}`}</span>
                      </div>
                      <div className="text-slate-500">SL {f(m.setup.sl)} · TP {f(m.setup.target)}{m.setup.rr ? ` · 1:${m.setup.rr}` : ''}</div>
                    </div>
                  ) : m.lastTrade && (
                    <div className="mt-2 text-xs text-slate-500">{t('Last trade', 'Dernier trade', 'آخر صفقة')}: <span className={tone(m.lastTrade.r)}>{m.lastTrade.outcome ?? stateLabel(m.symbol, m.lastTrade.state)} {m.lastTrade.r !== null ? r2(m.lastTrade.r) : ''}</span></div>
                  )}
                  {m.liveGrade && m.dataOk && (
                    <div className="mt-2 flex items-center gap-2 text-[11px]">
                      <span className="text-slate-500">{t('Grade now', 'Note actuelle', 'التقييم دابا')}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-surface-3/70 overflow-hidden" aria-hidden="true">
                        <motion.div className={`h-full rounded-full ${m.liveGrade.score >= 60 ? 'bg-emerald-500' : m.liveGrade.score >= 50 ? 'bg-gold-400' : 'bg-slate-500'}`}
                          initial={{ width: 0 }} animate={{ width: `${m.liveGrade.score}%` }} transition={{ duration: 0.6, ease: EASE }} />
                      </div>
                      <span className={`font-mono ${m.liveGrade.score >= 60 ? 'text-emerald-300' : 'text-slate-300'}`}>{m.liveGrade.grade} · {m.liveGrade.score}%</span>
                    </div>
                  )}
                  <p className="mt-2 text-xs text-slate-400 leading-relaxed line-clamp-2">{m.dataOk ? m.headline : m.dataReason}</p>
                </motion.button>
              );
            })}
          </div>
        </Panel>
      </Reveal>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <Reveal i={13} className="xl:col-span-5">
          <Panel icon={<Activity className="w-4 h-4" />} title={mode === 'me' ? t('My result per pair ($)', 'Mon résultat par paire ($)', 'النتيجة ديالي حسب الزوج ($)') : t('Signals sent: result per pair', 'Signaux envoyés : résultat par paire', 'الإشارات المرسلة حسب الزوج')}>
            {pairRows.length === 0
              ? <p className="text-xs text-slate-500">{mode === 'me' ? t('Log the trades you take (Account page) to see your result per pair.', 'Enregistrez vos trades (page Compte) pour voir votre résultat par paire.', 'سجل الصفقات ديالك (صفحة الحساب) باش تشوف النتيجة حسب الزوج.') : t('No closed signal yet: results appear once a signal reaches its TP or SL.', 'Aucun signal clôturé : les résultats apparaissent quand un signal touche son TP ou SL.', 'ما كاين حتى إشارة مسدودة.')}</p>
              : <PairBars rows={pairRows} mode={mode} />}
            {strategy.recent.length > 0 && (
              <ul className="mt-4 space-y-1 text-xs font-mono">
                {strategy.recent.slice(0, 6).map(s => (
                  <li key={s.id} className="flex items-center justify-between gap-2 border-t border-line pt-1">
                    <span className="text-slate-400 truncate">{new Date(s.signalTime * 1000).toISOString().slice(5, 16).replace('T', ' ')} · <span className={s.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>{s.direction}</span> {s.symbol}</span>
                    <span className={s.state === 'CLOSED' ? tone(s.rMultiple) : 'text-gold-300'}>{s.state === 'CLOSED' ? `${s.outcome} ${r2(s.rMultiple)}` : stateLabel(s.symbol, s.state)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>
        <Reveal i={14} className="xl:col-span-4">
          <Panel icon={<Wallet className="w-4 h-4" />} title={t('My open trades', 'Mes trades ouverts', 'صفقاتي المفتوحة')}>
            {me.openTrades.length === 0 ? <p className="text-xs text-slate-500">{t('No open trade.', 'Aucun trade ouvert.', 'ما كاين حتى صفقة مفتوحة.')}</p> : (
              <ul className="space-y-2 text-xs font-mono">
                {me.openTrades.map(o => (
                  <li key={o.id} className="rounded-lg border border-line bg-surface px-2.5 py-2">
                    <div className="flex items-center justify-between"><span><span className={o.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>{o.direction}</span> {o.symbol}</span><span className="text-slate-300">{o.lots} lot</span></div>
                    <div className="text-slate-500">{o.entry} · SL {o.sl} · {t('risk', 'risque', 'مخاطرة')} {fmtMoney(o.riskAmount)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>
        <Reveal i={15} className="xl:col-span-3">
          <Panel icon={<Newspaper className="w-4 h-4" />} title={t('High-impact news', 'News à fort impact', 'أخبار قوية')}>
            {data.news.length === 0 ? <p className="text-xs text-slate-500">{t('Nothing scheduled.', 'Rien de prévu.', 'ما كاين والو.')}</p> : (
              <ul className="space-y-2 text-xs">
                {data.news.map(n => (
                  <li key={n.id} className={`border-t border-line pt-1.5 ${n.isLockoutEvent ? 'text-amber-300' : 'text-slate-300'}`}>
                    <div className="font-mono text-slate-500">{n.publishedAt.slice(5, 16).replace('T', ' ')} UTC</div>
                    <div className="truncate" title={n.title}>{n.title}</div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] text-slate-500">{t('No signal 30 min before and after these.', 'Aucun signal 30 min avant et après.', 'ما كاين حتى إشارة 30 دقيقة قبل وبعد.')}</p>
          </Panel>
        </Reveal>
      </div>
    </div>
  );
}
