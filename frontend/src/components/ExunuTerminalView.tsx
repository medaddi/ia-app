import { apiFetch } from '../api';
import { markDataReady } from '../splash';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PriceChart, type ChartLevel, type PriceCandle } from './PriceChart';
import { TeamCard } from './TeamCard';
import { cachedTeams, prefetchTeams, useSmcTeam } from '../smcTeam';
import type { Language } from '../types';
import { useLivePrice } from '../livePrices';
import { TradingViewChart, useChartingLibrary } from '../tradingview/TradingViewChart';
import { PairFlags } from './PairFlags';
import { useDragScroll } from '../useDragScroll';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, PAIR_DECIMALS, PAIR_GROUPS, TIMEFRAMES, marketOpenNow, type InstrumentSymbol } from '../instruments';

/**
 * The live chart of each pair: its candles, its live price, and its team (the pair playbook strategy) with the setup it found drawn on the chart.
 */
interface ExunuTerminalViewProps {
  initialSymbol?: InstrumentSymbol;
  onSymbolChange?: (symbol: InstrumentSymbol) => void; // keeps the app header on the pair shown here
  lang?: string;
}

const PROVIDER_TF: Record<string, string> = { M1: '1M', M5: '5M', M15: '15M', M30: '30M', H1: '1H', H2: '2H', H4: '4H', D1: '1D', W1: '1W' };
const NO_CANDLES: PriceCandle[] = [];
const LIVE_MS = 5000; // candles every 5 s; the price every second (livePrices.ts)
const DEFAULT_TF = 'H1';
// the timeframes a tab shows: one chart, or the H1 + M5 split view
const chartTfs = (tab: string) => (tab === 'SPLIT' ? ['H4', 'H1'] : [tab]);

// Each pair's last candles, per pair AND timeframe, with the price info that came with them: a switch shows that pair's
// own last candles at once (never another pair's), and the fresh ones replace them a moment later
interface CandleEntry { key: string; list: PriceCandle[]; quote: { time: number; source: string } | null; at: number }
const candleCache = new Map<string, CandleEntry>();
const EMPTY_ENTRY: CandleEntry = { key: '', list: [], quote: null, at: 0 };

async function fetchCandles(sym: string, tf: string, signal?: AbortSignal): Promise<CandleEntry | null> {
  const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(sym)}&timeframe=${PROVIDER_TF[tf]}&count=400`, { cache: 'no-store', signal });
  const json = await res.json();
  if (!json.success || !Array.isArray(json.candles) || json.symbol !== sym) return null;  // an answer for another pair: dropped
  const entry = { key: `${sym}_${tf}`, list: json.candles, quote: json.quoteTime ? { time: json.quoteTime, source: json.priceSource || '' } : null, at: Date.now() };
  candleCache.set(entry.key, entry);
  return entry;
}

// Each pair remembers the timeframe it was last viewed on
const tfKey = (s: string) => `ld_chart_tf_${s}`;
const savedTf = (s: InstrumentSymbol) => {
  try { const v = localStorage.getItem(tfKey(s)); return v && TIMEFRAMES.includes(v) ? v : DEFAULT_TF; } catch { return DEFAULT_TF; }
};

export const ExunuTerminalView: React.FC<ExunuTerminalViewProps> = ({ initialSymbol = 'XAU/USD', onSymbolChange, lang = 'en' }) => {
  const [symbol, setSymbolState] = useState<InstrumentSymbol>(initialSymbol);
  const [timeframe, setTimeframeState] = useState<string>(() => savedTf(initialSymbol));
  const setSymbol = (s: InstrumentSymbol) => { setSymbolState(s); setTimeframeState(savedTf(s)); onSymbolChange?.(s); };
  const setTimeframe = (tf: string) => { setTimeframeState(tf); try { localStorage.setItem(tfKey(symbol), tf); } catch { /* storage blocked */ } };
  // The app picked another pair (search, dashboard card): follow it
  useEffect(() => { if (initialSymbol !== symbol) { setSymbolState(initialSymbol); setTimeframeState(savedTf(initialSymbol)); } }, [initialSymbol]);

  // The candles are kept under the key of the pair and timeframe they belong to (candleCache): a chart only gets its own
  const [, setRev] = useState(0);
  const tvChart = useChartingLibrary();  // TradingView Advanced Charts when its files are served (docs/TRADINGVIEW.md)
  const tfs = chartTfs(timeframe);
  const entryOf = (tf: string) => { const e = candleCache.get(`${symbol}_${tf}`) ?? EMPTY_ENTRY; return e.key === `${symbol}_${tf}` ? e : EMPTY_ENTRY; };
  const main = entryOf(tfs[0]);
  const candles = main.list.length ? main.list : NO_CANDLES;
  const live = useLivePrice(symbol);
  const team = useSmcTeam(symbol);  // THIS pair's team
  const abortRef = useRef<AbortController | null>(null);
  const viewRef = useRef({ symbol, timeframe });
  viewRef.current = { symbol, timeframe };

  const loadCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const entry = await fetchCandles(sym, tf, abortRef.current?.signal);
      if (!entry || viewRef.current.symbol !== sym || !chartTfs(viewRef.current.timeframe).includes(tf)) return;  // an answer for the old pair: dropped
      setRev(r => r + 1);
      markDataReady();
    } catch {
      // keep the last good candles
    }
  }, []);

  // A switch: the old pair's pending request is aborted, the new pair shows its own last candles (if any) and loads fresh ones
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setRev(r => r + 1);
    chartTfs(timeframe).forEach(tf => loadCandles(symbol, tf));
  }, [symbol, timeframe]);

  // Once the page is open: the other pairs' candles (their saved timeframe) and teams load quietly, one by one, so a switch is instant
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      for (const s of INSTRUMENT_SYMBOLS) {
        if (ctrl.signal.aborted) return;
        for (const tf of chartTfs(savedTf(s))) {
          if (!candleCache.has(`${s}_${tf}`)) { try { await fetchCandles(s, tf, ctrl.signal); } catch { /* loads when opened */ } }
        }
      }
      await prefetchTeams(INSTRUMENT_SYMBOLS, ctrl.signal);
    }, 2500);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, []);
  // Live loop: the candles every 5 s, paused while the tab is hidden
  useEffect(() => {
    let busy = false;
    const id = setInterval(async () => {
      if (busy || document.hidden) return;
      busy = true;
      await Promise.all(chartTfs(timeframe).map(tf => loadCandles(symbol, tf)));
      busy = false;
    }, LIVE_MS);
    return () => clearInterval(id);
  }, [symbol, timeframe, loadCandles]);

  const t = (en: string, fr: string, ar: string) => (lang === 'ar' ? ar : lang === 'fr' ? fr : en);
  const pairBar = useDragScroll<HTMLDivElement>();
  // the Sunday Swings watchlist: every pair's last read ranked by its 5-agent consensus, signals and radars first
  const [swings, setSwings] = useState<boolean>(() => { try { return localStorage.getItem('ld_sunday_swings') === '1'; } catch { return false; } });
  const [, setTick] = useState(0);
  useEffect(() => { const id = setInterval(() => setTick(x => x + 1), 15000); return () => clearInterval(id); }, []);
  const toggleSwings = () => setSwings(v => { try { localStorage.setItem('ld_sunday_swings', v ? '0' : '1'); } catch { /* storage blocked */ } return !v; });
  const rank = (x: ReturnType<typeof cachedTeams>[number]) => (x.signals?.length ? 2000 : x.radar ? 1000 : 0) + (x.consensus ?? 0);
  const top = cachedTeams().filter(x => x.success).sort((a, b) => rank(b) - rank(a)).slice(0, 5);
  const li = lang === 'ar' ? 2 : lang === 'fr' ? 1 : 0;
  const pairButton = (id: InstrumentSymbol, extra?: string) => (
    <button key={id} role="tab" aria-selected={symbol === id} onClick={() => setSymbol(id)}
      className={`h-10 ps-2 pe-3 shrink-0 inline-flex items-center gap-2 rounded-xl text-xs font-medium cursor-pointer transition-colors ${symbol === id ? 'glass-pill text-gold-100' : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]'}`}>
      <PairFlags symbol={id} size={18} />
      <span className="font-mono">{id}</span>{extra && <span className="font-mono text-[10px] text-gold-300">{extra}</span>}
    </button>
  );
  const decimals = PAIR_DECIMALS[symbol];
  const lastClose = candles.length ? candles[candles.length - 1].close : null;
  const shown = live?.price ?? lastClose;
  const open = marketOpenNow();
  // What THIS pair's team draws: its analysis (levels, zones, BOS / CHoCH / sweeps) and its setup when one passed the guide's checklist
  const mine = team?.success && team.symbol === symbol ? team : null;
  const sig = mine ? mine.signals[mine.signals.length - 1] : undefined;
  const ch = mine?.chart;
  const near = (v: number) => !lastClose || Math.abs(v - lastClose) / lastClose < 0.2;  // never another pair's level
  const levels: ChartLevel[] = (sig ? [{ price: sig.entry, label: `${sig.strategy} ${sig.direction}`, kind: 'entry' as const },
    { price: sig.sl, label: 'SL', kind: 'sl' as const }, { price: sig.tp, label: 'TP', kind: 'tp' as const }] : []).filter(l => near(l.price));
  // the position tool's numbers: the stop in pips and its 1 % risk, the target's pips and R:R (gold: 1 pip = $0.10)
  const pip = decimals === 2 ? 0.1 : decimals === 3 ? 0.01 : 0.0001;  // gold $0.10, JPY pairs 0.01
  const tool = (tr: NonNullable<typeof ch>['trade']) => tr && near(tr.entry) ? {
    ...tr, slPips: Math.abs(tr.entry - tr.sl) / pip, tpPips: Math.abs(tr.tp - tr.entry) / pip,
    rr: Math.abs(tr.tp - tr.entry) / (Math.abs(tr.entry - tr.sl) || 1), risk: `1 % = $100 / $10k`,
  } : null;
  const drawing = ch ? { boxes: ch.boxes.filter(b => near(b.top) && near(b.bottom)), segments: ch.segments.filter(x => near(x.price)),
    labels: ch.labels.filter(x => near(x.price)), trade: tool(ch.trade),
    // the strategy's own indicator lines (Bollinger 3σ, EMA 20/50/200) and its time windows (Silver Bullet, killzones…)
    lines: (ch.lines ?? []).map(l => ({ ...l, points: l.points.filter(([, v]) => near(v)) })), windows: ch.windows ?? [] } : null;

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-3 glass border rounded-[var(--radius-card)]">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Pairs: each with its flags; scrolls sideways on a phone without a visible scrollbar */}
          <div ref={pairBar} role="tablist" aria-label={t('Instrument', 'Instrument', 'الأداة')}
            className="no-scrollbar select-none cursor-grab flex items-center gap-1 overflow-x-auto max-w-full -mx-1 px-1 [mask-image:linear-gradient(90deg,transparent,#000_12px,#000_calc(100%-16px),transparent)]">
            {swings ? (
              <>
                <span className="shrink-0 px-2 text-[10px] uppercase tracking-wider text-gold-300">{t('Watchlist top picks', 'Meilleures paires', 'أحسن الأزواج')}</span>
                {top.length === 0 && <span className="shrink-0 text-[11px] text-slate-500">{t('Reading the 29 teams…', 'Lecture des 29 équipes…', 'كيقرا 29 فريق…')}</span>}
                {top.map(x => pairButton(x.symbol as InstrumentSymbol, `${x.signals?.length ? '🎯' : x.radar ? '👀' : ''}${x.consensus ?? ''}`))}
              </>
            ) : PAIR_GROUPS.map(g => (
              <React.Fragment key={g.id}>
                <span className="shrink-0 ps-2 pe-1 text-[10px] uppercase tracking-wider text-slate-500" title={INSTRUMENT_LABELS[g.pairs[0]]}>{g.label[li]}</span>
                {g.pairs.map(id => pairButton(id))}
              </React.Fragment>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <button type="button" onClick={toggleSwings} aria-pressed={swings}
            className={`h-8 px-2.5 rounded-lg border text-[11px] cursor-pointer ${swings ? 'border-gold-500/40 bg-gold-500/10 text-gold-200' : 'border-line text-slate-400 hover:text-white'}`}>
            {t('Sunday Swings', 'Sunday Swings', 'Sunday Swings')}
          </button>
          <span className={`w-1.5 h-1.5 rounded-full ${open ? 'bg-emerald-400' : 'bg-slate-500'}`} aria-hidden="true" />
          <span className="text-slate-400">{open ? t('Market open', 'Marché ouvert', 'السوق مفتوح') : t('Market closed', 'Marché fermé', 'السوق مغلق')}</span>
          <span className="text-white font-semibold tabular-nums">{shown != null ? shown.toFixed(decimals) : '—'}</span>
        </div>
      </div>

      {tvChart ? (
        <TradingViewChart symbol={symbol} timeframe={timeframe} lang={lang} onTimeframeChange={setTimeframe} />
      ) : (
        <div className={tfs.length > 1 ? 'grid gap-4 xl:grid-cols-2' : ''}>
          {tfs.map(tf => {
            const e = entryOf(tf);
            return (
              <PriceChart key={tf} symbol={symbol} candles={e.list.length ? e.list : NO_CANDLES} decimals={decimals} timeframe={tf} tabValue={timeframe}
                timeframes={TIMEFRAMES} onTimeframeChange={setTimeframe} compact={tfs.length > 1} livePrice={live?.price ?? null}
                quote={live?.quoteTime ? { time: live.quoteTime, source: live.source } : e.quote} updatedAt={e.at} lang={lang} levels={levels} drawing={drawing} />
            );
          })}
        </div>
      )}
      <TeamCard key={symbol} team={team} symbol={symbol} decimals={decimals} lang={lang as Language} />
    </div>
  );
};
