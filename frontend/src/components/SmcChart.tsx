import { apiFetch } from '../api';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { strategyKind, type InstrumentSymbol } from '../instruments';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  IPriceLine,
  createSeriesMarkers,
  Time,
} from 'lightweight-charts';
import { Check, ChevronDown, Expand, Layers as LayersIcon, Maximize2, Minimize2, RefreshCw, X } from 'lucide-react';
import type { StrategyResult, DrawingLayer } from '../strategyTypes';
import { DrawingsPrimitive, OverlayTheme } from '../chart-overlays/drawingsPrimitive';

export interface SmcChartCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface SmcChartProps {
  symbol: InstrumentSymbol;
  candles: SmcChartCandle[];
  result: StrategyResult | null;
  timeframe: string;
  timeframes: string[];
  entryTf: string; // the timeframe the strategy decides on (its candle close = new evaluation)
  emas: number[]; // the moving averages the strategy's rules use
  emaNote: string;
  updatedAt: number; // ms of the last live reload (0 = review mode)
  onTimeframeChange: (tf: string) => void;
  isLoading?: boolean;
  onRefresh?: () => void;
  lang?: string;
}

const TF_SEC: Record<string, number> = { M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800 };
type Layer = DrawingLayer | 'ema' | 'bands';
const LAYERS: { key: Layer; label: [string, string, string] }[] = [
  { key: 'sessions', label: ['Sessions', 'Sessions', 'الجلسات'] },
  { key: 'levels', label: ['Key levels', 'Niveaux clés', 'المستويات'] },
  { key: 'liquidity', label: ['Liquidity', 'Liquidité', 'السيولة'] },
  { key: 'structure', label: ['Structure', 'Structure', 'الهيكل'] },
  { key: 'swings', label: ['Swings', 'Swings', 'القمم والقيعان'] },
  { key: 'fvg', label: ['FVG', 'FVG', 'FVG'] },
  { key: 'ob', label: ['OB', 'OB', 'OB'] },
  { key: 'fib', label: ['Fib', 'Fib', 'فيبو'] },
  { key: 'ema', label: ['EMA', 'EMA', 'EMA'] },
  { key: 'bands', label: ['Bollinger 2.2σ', 'Bollinger 2,2σ', 'بولينجر 2.2σ'] },
  { key: 'trade', label: ['Trade', 'Trade', 'الصفقة'] },
];
const DEFAULT_LAYERS = Object.fromEntries(LAYERS.map(l => [l.key, true])) as Record<Layer, boolean>;
// Candles shown when a pair / timeframe opens (the rest of the history stays one scroll away): close enough to read
// each candle, wide enough for the structure. Daily ≈ 3 months, weekly ≈ 1 year.
const VISIBLE_BARS: Record<string, number> = { M15: 150, M30: 130, H1: 120, H4: 100, D1: 66, W1: 52 };
const layerKey = (kind: string) => `ld_chart_layers_${kind}_v2`;
const ALWAYS_SHOWN: Layer[] = ['ema', 'trade'];

function bollinger(values: number[], period: number, k: number): { mid: (number | null)[]; up: (number | null)[]; lo: (number | null)[] } {
  const mid: (number | null)[] = new Array(values.length).fill(null), up = [...mid], lo = [...mid];
  for (let i = period - 1; i < values.length; i++) {
    const w = values.slice(i - period + 1, i + 1);
    const m = w.reduce((a, b) => a + b, 0) / period;
    const sd = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / period);
    mid[i] = m; up[i] = m + k * sd; lo[i] = m - k * sd;
  }
  return { mid, up, lo };
}

const fmtLeft = (sec: number) => {
  const s = Math.max(0, Math.floor(sec));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s % 60).padStart(2, '0')}s`;
};
const str = (v: unknown) => (typeof v === 'string' ? v : '');
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

const PAL = {
  dark: { bg: '#0D1016', grid: 'rgba(255,255,255,0.035)', text: '#8D96A6', border: '#1F2430', bull: '#16C784', bear: '#EA3943', ema50: '#4B85B8', ema200: '#C9A04A' },
  light: { bg: '#FFFFFF', grid: 'rgba(0,0,0,0.05)', text: '#4D5566', border: '#DDD6C8', bull: '#0E9F6E', bear: '#D92D3A', ema50: '#386A99', ema200: '#A8843A' },
};

function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let e = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = e;
  for (let i = period; i < values.length; i++) { e = values[i] * k + e * (1 - k); out[i] = e; }
  return out;
}

const readTheme = (): OverlayTheme => (typeof document !== 'undefined' && !document.documentElement.classList.contains('dark') ? 'light' : 'dark');

export const SmcChart: React.FC<SmcChartProps> = ({ symbol, candles, result, timeframe, timeframes, entryTf, emas, emaNote, updatedAt, onTimeframeChange, isLoading, onRefresh, lang = 'en' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const bandRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const frameRef = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(() => typeof window === 'undefined' || window.matchMedia('(min-width: 768px)').matches);
  const kind = strategyKind(symbol);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const primitiveRef = useRef<DrawingsPrimitive | null>(null);
  const fitKeyRef = useRef('');
  const [theme, setTheme] = useState<OverlayTheme>(readTheme);
  const [hover, setHover] = useState<{ c: SmcChartCandle | null; x: number; y: number; onSignal: boolean }>({ c: null, x: 0, y: 0, onSignal: false });
  const [explain, setExplain] = useState<{ x: number; y: number; title: string; text: string } | null>(null);
  const langRef = useRef(lang);
  langRef.current = lang;
  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;
  const li = lang === 'fr' ? 1 : lang === 'ar' ? 2 : 0;
  const t = (en: string, fr: string, ar: string) => [en, fr, ar][li];
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNowMs(Date.now()), 1000); return () => clearInterval(id); }, []);
  const loadLayers = (k: string): Record<Layer, boolean> => {
    try { return { ...DEFAULT_LAYERS, ...JSON.parse(localStorage.getItem(layerKey(k)) || '{}') }; } catch { return DEFAULT_LAYERS; }
  };
  const [layers, setLayers] = useState<Record<Layer, boolean>>(() => loadLayers(kind));
  useEffect(() => { setLayers(loadLayers(kind)); }, [kind]);

  const decimals = result?.spec.decimals ?? (symbol === 'XAU/USD' ? 2 : 5);
  const fmt = (v: number) => v.toFixed(decimals);
  const tfSec = TF_SEC[timeframe] || 900;
  const setup = result?.setup ?? null;
  const signalBarTime = setup ? setup.signalTime - (TF_SEC[result!.timeframes.entry.split('/')[0]] || tfSec) : null;

  // The pair's track record (every closed trade of its strategy), summarised in the status strip; the list is under the chart
  const pastStats = result?.historyStats ?? null;

  // Follow the app's light/dark theme
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(readTheme()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  // The layers menu closes on a click outside it or on Escape
  const layersRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!layersOpen) return;
    const down = (e: MouseEvent) => { if (layersRef.current && !layersRef.current.contains(e.target as Node)) setLayersOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setLayersOpen(false); };
    document.addEventListener('mousedown', down);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key); };
  }, [layersOpen]);
  const toggleLayer = (k: Layer) => setLayers(prev => {
    const next = { ...prev, [k]: !prev[k] };
    try { localStorage.setItem(layerKey(kind), JSON.stringify(next)); } catch { /* storage unavailable */ }
    return next;
  });

  // Real full screen (Esc leaves it); the chart follows the new size
  useEffect(() => {
    const on = () => setFull(document.fullscreenElement === frameRef.current);
    document.addEventListener('fullscreenchange', on);
    return () => document.removeEventListener('fullscreenchange', on);
  }, []);
  const toggleFull = () => {
    const el = frameRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    else (el.requestFullscreen?.() ?? Promise.reject()).catch(() => setFull(f => !f));  // iOS: CSS full-screen fallback
  };

  // Chart instance (rebuilt on theme or precision change)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const p = PAL[theme];
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      layout: { background: { type: ColorType.Solid, color: p.bg }, textColor: p.text, fontSize: 11, fontFamily: "'JetBrains Mono', ui-monospace, monospace", attributionLogo: false },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(214,174,87,0.45)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: theme === 'dark' ? '#1A1F29' : '#4D5566' },
        horzLine: { color: 'rgba(214,174,87,0.45)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: theme === 'dark' ? '#1A1F29' : '#4D5566' },
      },
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.08, bottom: 0.16 } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, barSpacing: 8, rightOffset: 14 },
    });
    const minMove = decimals === 2 ? 0.01 : decimals === 4 ? 0.0001 : 0.00001;
    const cs = chart.addSeries(CandlestickSeries, {
      upColor: p.bull, downColor: p.bear, borderUpColor: p.bull, borderDownColor: p.bear, wickUpColor: p.bull, wickDownColor: p.bear,
      priceFormat: { type: 'price', precision: decimals, minMove },
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } });
    const emaLines = [p.ema50, p.ema200].map(color => chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false }));
    const bandLines = [0, 1, 2].map(k => chart.addSeries(LineSeries, {
      color: k === 1 ? 'rgba(160,150,220,0.55)' : 'rgba(160,150,220,0.85)', lineWidth: 1, lineStyle: k === 1 ? LineStyle.Dotted : LineStyle.Solid,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    }));
    const prim = new DrawingsPrimitive();
    cs.attachPrimitive(prim);

    chart.subscribeCrosshairMove(param => {
      const d = param.seriesData.get(cs) as any;
      const t = Number(param.time);
      setHover({
        c: d && typeof d.open === 'number' ? { time: t, open: d.open, high: d.high, low: d.low, close: d.close } : null,
        x: param.point?.x ?? 0,
        y: param.point?.y ?? 0,
        onSignal: false,
      });
    });

    // Click a drawing → the agent explains it from the drawing's own data
    chart.subscribeClick(param => {
      if (!param.point) { setExplain(null); return; }
      const hit = prim.findDrawingAt(param.point.x, param.point.y, el.clientWidth - chart.priceScale('right').width());
      if (!hit) { setExplain(null); return; }
      const at = { x: param.point.x, y: param.point.y };
      setExplain({ ...at, title: hit.text || hit.layer, text: '…' });
      apiFetch('/api/agent/explain-drawing', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: symbolRef.current, drawingId: hit.id, lang: langRef.current, asOf: Number(new URLSearchParams(window.location.search).get('asOf')) || 0 }) })
        .then(r => r.json())
        .then(j => setExplain({ ...at, title: hit.text || hit.layer, text: j.success ? j.text : j.error || '—' }))
        .catch(() => setExplain({ ...at, title: hit.text || hit.layer, text: '⚠' }));
    });

    chartRef.current = chart;
    candleRef.current = cs;
    volRef.current = vol;
    emaRefs.current = emaLines;
    bandRefs.current = bandLines;
    markersRef.current = createSeriesMarkers(cs, []);
    primitiveRef.current = prim;
    fitKeyRef.current = '';

    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      primitiveRef.current = null;
    };
  }, [theme, decimals]);

  const bars = useMemo(() => [...candles]
    .filter(c => c && [c.open, c.high, c.low, c.close].every(v => typeof v === 'number'))
    .sort((a, b) => a.time - b.time)
    .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time), [candles]);

  const barsLenRef = useRef(0);
  const barTimesRef = useRef<number[]>([]);
  barsLenRef.current = bars.length;
  const resetView = () => {
    const n = barsLenRef.current;
    const show = VISIBLE_BARS[timeframe] ?? 120;
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n + Math.max(4, Math.round(show * 0.08)) });
  };

  // Candles, volume, EMAs
  useEffect(() => {
    const cs = candleRef.current, chart = chartRef.current;
    if (!cs || !chart) return;
    const p = PAL[theme];
    // The feed is a sliding window (oldest candle drops when a new one opens): keep the view on the same candles
    // so a trade drawn on the chart stays exactly where it is instead of sliding one bar at every refresh
    const prevTimes = barTimesRef.current;
    const range = prevTimes.length && bars.length ? chart.timeScale().getVisibleLogicalRange() : null;
    let shift = 0;
    if (range && prevTimes[0] !== bars[0].time) {
      const k = bars.findIndex(b => b.time === prevTimes[0]);
      shift = k >= 0 ? k : -Math.max(0, prevTimes.indexOf(bars[0].time));
    }
    const followLive = !!range && range.to >= prevTimes.length - 1;  // the user is looking at the live edge
    const grew = bars.length + shift - prevTimes.length;  // candles added at the right edge
    cs.setData(bars.map(b => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })));
    barTimesRef.current = bars.map(b => b.time);
    if (range && (shift || grew) && fitKeyRef.current === `${symbol}-${timeframe}-${theme}`) {
      const extra = followLive ? Math.max(0, grew) : 0;  // at the live edge: the new candle scrolls in, as on any terminal
      chart.timeScale().setVisibleLogicalRange({ from: range.from + shift + extra, to: range.to + shift + extra });
    }
    volRef.current?.setData(bars.map(b => ({ time: b.time as Time, value: b.volume || 0, color: b.close >= b.open ? 'rgba(22,199,132,0.22)' : 'rgba(234,57,67,0.22)' })));
    const closes = bars.map(b => b.close);
    const toLine = (vals: (number | null)[]) => bars.flatMap((b, i) => (vals[i] === null ? [] : [{ time: b.time as Time, value: vals[i] as number }]));
    // Only the averages this strategy's rules use (gold EMA 50/200, forex EMA 20)
    emaRefs.current.forEach((line, k) => {
      const period = emas[k];
      line.setData(layers.ema && period ? toLine(ema(closes, period)) : []);
      line.applyOptions({ color: k === 0 ? p.ema50 : p.ema200, title: period ? `EMA${period}` : '' });
    });
    // Gold's reversion engine reads the 20-period 2.2σ Bollinger band: drawn only on the gold chart
    const bb = kind === 'gold' && layers.bands ? bollinger(closes, 20, 2.2) : null;
    bandRefs.current.forEach((line, k) => line.setData(bb ? toLine([bb.up, bb.mid, bb.lo][k]) : []));
    const key = `${symbol}-${timeframe}-${theme}`;
    if (fitKeyRef.current !== key && bars.length) {
      fitKeyRef.current = key;
      barTimesRef.current = bars.map(b => b.time);
      resetView();
    }
  }, [bars, symbol, timeframe, theme, layers.ema, layers.bands, emas, kind]);

  // Daily / weekly axis shows dates only; forex has no real volume on the free feed, so its pane is hidden
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const hasVolume = bars.some(b => (b.volume || 0) > 0);
    chart.applyOptions({ timeScale: { timeVisible: tfSec < 86400 } });
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.08, bottom: hasVolume ? 0.16 : 0.06 } });
    volRef.current?.applyOptions({ visible: hasVolume });
  }, [bars, tfSec, theme, decimals]);

  // The trade's levels on the price axis (entry, stop, targets), so they can be read at any zoom
  useEffect(() => {
    const cs = candleRef.current;
    if (!cs) return;
    const lines: IPriceLine[] = [];
    if (setup && layers.trade && ['PENDING', 'OPEN', 'TP1_HIT', 'TP2_HIT'].includes(setup.lifecycle.state)) {
      const p = PAL[theme];
      const add = (price: number, color: string, title: string, style = LineStyle.Solid) =>
        lines.push(cs.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title }));
      add(setup.entry, p.text, t('Entry', 'Entrée', 'دخول'));
      add(setup.sl, p.bear, 'SL');
      const single = setup.params?.breakeven === false;
      if (single) add(setup.tp3, p.bull, 'TP');
      else { add(setup.tp1, p.bull, 'TP1', LineStyle.Dashed); add(setup.tp2, p.bull, 'TP2', LineStyle.Dashed); add(setup.tp3, p.bull, 'TP3'); }
    }
    return () => { lines.forEach(l => { try { cs.removePriceLine(l); } catch { /* chart rebuilt */ } }); };
  }, [setup?.id, setup?.lifecycle.state, layers.trade, theme, decimals, lang]);

  // A new pair / timeframe: forget the old crosshair and explanation
  useEffect(() => { chartRef.current?.clearCrosshairPosition(); setExplain(null); }, [symbol, timeframe]);

  // Drawings + entry arrow
  useEffect(() => {
    const prim = primitiveRef.current;
    if (!prim) return;
    const { ema: _ema, bands: _bands, ...drawLayers } = layers;
    prim.update({ drawings: result?.drawings ?? [], barTimes: bars.map(b => b.time), tfSec, chartTf: timeframe, layers: drawLayers as Record<DrawingLayer, boolean>, theme });
    const markers: any[] = [];
    if (setup && layers.trade && signalBarTime !== null) {
      let snap: number | null = null;
      for (const b of bars) { if (b.time <= signalBarTime) snap = b.time; else break; }
      const buy = setup.direction === 'BUY';
      if (snap !== null) markers.push({ time: snap as Time, position: buy ? 'belowBar' : 'aboveBar', color: buy ? PAL[theme].bull : PAL[theme].bear, shape: buy ? 'arrowUp' : 'arrowDown', text: `${setup.direction} · ${result!.score}`, size: 1.2 });
    }
    markersRef.current?.setMarkers(markers);
  }, [result, bars, layers, tfSec, timeframe, theme, setup, signalBarTime]);

  const last = bars[bars.length - 1];
  const ohlc = hover.c || last;
  const legendIdx = ohlc ? bars.findIndex(b => b.time === ohlc.time) : -1;
  const closesAll = useMemo(() => bars.map(b => b.close), [bars]);
  const emaVals = useMemo(() => emas.map(period => ema(closesAll, period)), [closesAll, emas]);
  const bbVals = useMemo(() => (kind === 'gold' ? bollinger(closesAll, 20, 2.2) : null), [closesAll, kind]);
  const prevClose = legendIdx > 0 ? bars[legendIdx - 1].close : null;
  const chg = ohlc && prevClose ? ((ohlc.close - prevClose) / prevClose) * 100 : null;

  // The numbers this strategy decides on, straight from its own output (no recomputation here)
  const facts = (result?.facts ?? {}) as Record<string, unknown>;
  const pip = result?.spec.pipSize ?? (symbol === 'XAU/USD' ? 0.1 : 0.0001);
  const trendTone = (t: string) => (t === 'bullish' ? 'text-emerald-400' : t === 'bearish' ? 'text-rose-400' : 'text-slate-300');
  const trendWord = (w: string) => (w === 'bullish' ? t('bullish', 'haussière', 'صاعد') : w === 'bearish' ? t('bearish', 'baissière', 'هابط')
    : w === 'flat' || w === 'none' ? t('none', 'aucune', 'بلا اتجاه') : w || '—');
  const keyFacts: { label: string; value: string; tone?: string }[] = [];
  if (result?.dataQuality.ok) {
    if (symbol === 'XAU/USD') {
      const rng = facts.range20h as { high?: number; low?: number } | undefined;
      keyFacts.push({ label: t('H1 trend', 'Tendance H1', 'اتجاه H1'), value: trendWord(str(facts.trend)), tone: trendTone(str(facts.trend)) });
      if (num(facts.ema50) !== null) keyFacts.push({ label: 'EMA50', value: fmt(num(facts.ema50)!) });
      if (num(facts.ema200) !== null) keyFacts.push({ label: 'EMA200', value: fmt(num(facts.ema200)!) });
      if (num(facts.atrH1) !== null) keyFacts.push({ label: 'ATR H1', value: `$${num(facts.atrH1)!.toFixed(2)}` });
      if (rng?.high && rng?.low) keyFacts.push({ label: t('20h range', 'Range 20 h', 'نطاق 20 ساعة'), value: `${fmt(rng.low)} – ${fmt(rng.high)}` });
      // Second engine (reversion): the 2.2σ Bollinger band it waits for a close beyond
      const bands = facts.bands as { upper: number; middle: number; lower: number } | null | undefined;
      if (bands) keyFacts.push({ label: t('Bollinger 2.2σ', 'Bollinger 2,2σ', 'بولينجر 2.2σ'), value: `${fmt(bands.lower)} · ${fmt(bands.middle)} · ${fmt(bands.upper)}` });
    } else if (kind === 'rsi2') {
      // RSI(2) Connors: H4 trend, RSI(2) now vs the pair's extreme, EMA5 exit level
      keyFacts.push({ label: t('H4 trend', 'Tendance H4', 'اتجاه H4'), value: trendWord(str(facts.trendH4)), tone: trendTone(str(facts.trendH4)) });
      const r2 = num(facts.rsi2);
      const lvl = num(facts.rsiLevel);
      if (r2 !== null) keyFacts.push({ label: 'RSI(2)', value: lvl !== null ? `${r2.toFixed(1)} · ${t('buy <', 'achat <', 'شراء <')} ${lvl} / ${t('sell >', 'vente >', 'بيع >')} ${100 - lvl}` : r2.toFixed(1),
        tone: lvl !== null && (r2 < lvl || r2 > 100 - lvl) ? 'text-gold-300' : 'text-slate-300' });
      if (num(facts.ema5) !== null) keyFacts.push({ label: t('EMA5 (exit)', 'EMA5 (sortie)', 'EMA5 (خروج)'), value: fmt(num(facts.ema5)!) });
      if (num(facts.ema200) !== null) keyFacts.push({ label: 'EMA200', value: fmt(num(facts.ema200)!) });
      if (num(facts.atrH4) !== null) keyFacts.push({ label: 'ATR H4', value: `${(num(facts.atrH4)! / pip).toFixed(1)} pips` });
    } else {
      // The 3 sync rule, the GPA grade right now, and the W1 / D1 zones with their touches
      for (const [k, key] of [['W1', 'trendW1'], ['D1', 'trendD1'], ['H4', 'trendH4']] as const) {
        keyFacts.push({ label: k, value: trendWord(str(facts[key])), tone: trendTone(str(facts[key])) });
      }
      const live = facts.liveGrade as { score: number; grade: string } | undefined;
      if (live) keyFacts.push({ label: t('Grade now', 'Note actuelle', 'التقييم دابا'), value: `${live.grade} · ${live.score}%`, tone: live.score >= 60 ? 'text-emerald-300' : live.score >= 50 ? 'text-gold-200' : 'text-slate-300' });
      if (num(facts.atrH4) !== null) keyFacts.push({ label: 'ATR H4', value: `${(num(facts.atrH4)! / pip).toFixed(1)} pips` });
      const aoi = (facts.areasOfInterest as { kind: string; lo: number; hi: number; touches: number; tfs: string }[] | undefined) ?? [];
      aoi.slice(0, 3).forEach((a, k) => keyFacts.push({ label: k === 0 ? t('AOI', 'Zone (AOI)', 'منطقة الاهتمام') : '', value: `${a.tfs} ${fmt(a.lo)}–${fmt(a.hi)} ×${a.touches}`, tone: a.kind === 'support' ? 'text-emerald-300' : 'text-rose-300' }));
    }
  }
  const entrySec = TF_SEC[entryTf] || 3600;
  const nowSec = nowMs / 1000;
  const nextClose = Math.ceil(nowSec / entrySec) * entrySec;
  if (result?.market.isOpen && updatedAt) keyFacts.push({ label: t(`Next ${entryTf} close`, `Prochaine clôture ${entryTf}`, `الإغلاق الجاي ${entryTf}`), value: fmtLeft(nextClose - nowSec), tone: 'text-gold-300' });
  if (result?.news.next) keyFacts.push({ label: t('News', 'News', 'خبر'), value: result.news.next, tone: result.news.blocked ? 'text-rose-300' : undefined });
  const lastTrade = facts.lastTrade as { state: string; outcome: string | null; r: number | null } | null | undefined;
  if (lastTrade) keyFacts.push({ label: t('Last trade', 'Dernier trade', 'آخر صفقة'), value: lastTrade.outcome ? `${lastTrade.outcome} ${lastTrade.r !== null ? `${lastTrade.r > 0 ? '+' : ''}${lastTrade.r.toFixed(2)}R` : ''}` : lastTrade.state,
    tone: lastTrade.outcome === 'WIN' ? 'text-emerald-300' : lastTrade.outcome === 'LOSS' ? 'text-rose-300' : 'text-gold-200' });

  // Only the layers this strategy actually draws (plus its averages and the trade)
  const present = new Set((result?.drawings ?? []).map(d => d.layer));
  const shownLayers = LAYERS.filter(l => ALWAYS_SHOWN.includes(l.key) || present.has(l.key as DrawingLayer) || (l.key === 'bands' && kind === 'gold'))
    .map(l => ({ key: l.key, label: l.key === 'ema' ? `EMA ${emas.join('/')} · ${({ 'trend on H1': t('trend on H1', 'tendance H1', 'اتجاه H1'), 'rejection on H4 / 1H': t('rejection on H4 / 1H', 'rejet H4 / 1H', 'رفض H4 / 1H'), 'exit / trend on H4': t('exit / trend on H4', 'sortie / tendance H4', 'خروج / اتجاه H4') } as Record<string, string>)[emaNote] ?? emaNote}` : l.label[li] }));
  const age = updatedAt ? Math.max(0, Math.round((nowMs - updatedAt) / 1000)) : null;
  const hoverIsSignal = !!(setup && hover.c && signalBarTime !== null && hover.c.time <= signalBarTime && hover.c.time + tfSec > signalBarTime);
  const statusTone = result?.status === 'SIGNAL' ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
    : result?.status === 'WATCH' ? 'bg-gold-500/15 text-gold-200 ring-gold-500/30'
    : 'bg-slate-500/10 text-slate-300 ring-slate-500/30';

  return (
    <div ref={frameRef} className={`flex flex-col border border-line bg-surface overflow-hidden ${full ? 'fixed inset-0 z-[60] rounded-none' : 'rounded-[var(--radius-card)]'}`}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-4 py-2 border-b border-line">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-white font-mono">{symbol}</span>
          <span className="px-1.5 py-0.5 rounded bg-surface-2 text-[11px] font-mono text-gold-300">{timeframe}</span>
          {timeframe === entryTf && <span className="hidden sm:inline text-[11px] text-slate-500">{t('decision timeframe', 'unité de décision', 'فريم القرار')}</span>}
        </div>
        <div className="flex items-center gap-1.5">
          <div role="tablist" aria-label={t('Timeframe', 'Unité de temps', 'الفريم')} className="flex items-center rounded-lg bg-surface-2 border border-line p-0.5">
            {timeframes.map(tf => (
              <button key={tf} role="tab" aria-selected={tf === timeframe} onClick={() => onTimeframeChange(tf)}
                className={`relative min-w-[38px] h-8 px-2 rounded-md font-mono text-xs cursor-pointer transition-colors ${tf === timeframe ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-100'}`}>
                {tf}{tf === entryTf && <span className="absolute top-1 end-1 w-1 h-1 rounded-full bg-gold-400" aria-hidden="true" />}
              </button>
            ))}
          </div>
          <div className="relative" ref={layersRef}>
            <button onClick={() => setLayersOpen(o => !o)} aria-expanded={layersOpen} aria-haspopup="menu"
              className="h-9 px-2.5 inline-flex items-center gap-1.5 rounded-lg border border-line text-slate-300 hover:text-white hover:bg-surface-2 cursor-pointer text-xs">
              <LayersIcon className="w-4 h-4" /><span className="hidden sm:inline">{t('Layers', 'Calques', 'الطبقات')}</span><ChevronDown className="w-3 h-3" />
            </button>
            {layersOpen && (
              <div role="menu" aria-label={t('Chart layers', 'Calques du graphique', 'طبقات الشارت')}
                className="absolute end-0 mt-1.5 w-60 rounded-xl border border-line-2 bg-surface-2 shadow-[var(--shadow-float)] p-1.5 z-40">
                {shownLayers.map(l => (
                  <button key={l.key} role="menuitemcheckbox" aria-checked={layers[l.key]} onClick={() => toggleLayer(l.key)}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-slate-200 hover:bg-white/[0.05] cursor-pointer text-start">
                    <span className={`w-4 h-4 rounded border flex items-center justify-center ${layers[l.key] ? 'bg-gold-500 border-gold-500 text-ink-strong' : 'border-line-2'}`}>
                      {layers[l.key] && <Check className="w-3 h-3" />}
                    </span>{l.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={resetView}
            className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2 cursor-pointer" aria-label={t('Reset view', 'Recentrer', 'رجع العرض')} title={t('Reset view', 'Recentrer', 'رجع العرض')}>
            <Maximize2 className="w-4 h-4" />
          </button>
          <button onClick={toggleFull} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2 cursor-pointer"
            aria-label={full ? t('Exit full screen', 'Quitter le plein écran', 'خرج من الشاشة الكاملة') : t('Full screen', 'Plein écran', 'شاشة كاملة')} title={full ? t('Exit full screen', 'Quitter le plein écran', 'خرج من الشاشة الكاملة') : t('Full screen', 'Plein écran', 'شاشة كاملة')}>
            {full ? <Minimize2 className="w-4 h-4" /> : <Expand className="w-4 h-4" />}
          </button>
          {onRefresh && (
            <button onClick={onRefresh} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2 cursor-pointer" aria-label={t('Refresh', 'Actualiser', 'تحديث')} title={t('Refresh', 'Actualiser', 'تحديث')}>
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-gold-400' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Status strip */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 sm:px-4 py-2 border-b border-line bg-surface-2/50 text-xs">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md ring-1 ring-inset font-medium ${statusTone}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
          {result ? (result.status === 'NO_TRADE' ? t('No trade', 'Pas de trade', 'لا صفقة') : `${setup?.direction ?? ''} ${result.status === 'SIGNAL' ? t('Signal', 'Signal', 'إشارة') : result.status === 'WATCH' ? t('Watch', 'À surveiller', 'مراقبة') : t('Ignored', 'Ignoré', 'متجاهل')}`) : t('Loading', 'Chargement', 'تحميل')}
          {result?.setup && ` · ${result.score}`}
        </span>
        <span className="text-slate-400 min-w-0 truncate">{result?.headline ?? t('Loading the analysis…', 'Chargement de l’analyse…', 'كيتحمل التحليل…')}</span>
        {pastStats && pastStats.trades > 0 && (
          <span className="inline-flex items-center gap-1.5 font-mono text-slate-400" title={t('Closed trades of the strategy on this pair: in profit (TP), at the entry (BE), at a loss (SL)', 'Trades clôturés de la stratégie sur cette paire : en gain (TP), au point mort (BE), en perte (SL)', 'الصفقات لي سدات الاستراتيجية ف هاد الزوج: ربح (TP)، تعادل (BE)، خسارة (SL)')}>
            {pastStats.trades} · <span className="text-emerald-400">TP {pastStats.tp}</span>/<span className="text-slate-300">BE {pastStats.be}</span>/<span className="text-rose-400">SL {pastStats.sl}</span> ·
            <span className={pastStats.totalR >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{pastStats.totalR >= 0 ? '+' : ''}{pastStats.totalR.toFixed(1)}R</span>
          </span>
        )}
        {keyFacts.length > 0 && (
          <button onClick={() => setDetailsOpen(o => !o)} aria-expanded={detailsOpen}
            className="inline-flex items-center gap-1 text-slate-400 hover:text-gold-300 cursor-pointer">
            {t('Details', 'Détails', 'التفاصيل')}<ChevronDown className={`w-3.5 h-3.5 transition-transform ${detailsOpen ? 'rotate-180' : ''}`} />
          </button>
        )}
        <span className="ms-auto font-mono text-slate-500">
          {t('Trend', 'Tendance', 'الاتجاه')} <span className={result?.bias.direction === 'BULLISH' ? 'text-emerald-400' : result?.bias.direction === 'BEARISH' ? 'text-rose-400' : 'text-slate-400'}>{result ? (result.bias.direction === 'BULLISH' ? t('Bullish', 'Haussière', 'صاعد') : result.bias.direction === 'BEARISH' ? t('Bearish', 'Baissière', 'هابط') : t('Neutral', 'Neutre', 'محايد')) : '—'}</span>
          {result?.market.window ? <span className="text-gold-300"> · {result.market.window}</span> : null}
        </span>
      </div>

      {/* Key numbers of the strategy */}
      {keyFacts.length > 0 && detailsOpen && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 sm:px-4 py-2 border-b border-line text-xs font-mono" aria-label={t('Strategy key levels', 'Chiffres clés de la stratégie', 'أرقام الاستراتيجية')}>
          {keyFacts.map((k, i) => (
            <span key={i} className="whitespace-nowrap">
              {k.label && <span className="text-slate-500">{k.label} </span>}
              <span className={k.tone ?? 'text-slate-200'}>{k.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className={`relative ${full ? 'flex-1' : 'h-[58vh] min-h-[380px] max-h-[680px]'}`}>
        <div ref={containerRef} className="absolute inset-0" />
        {ohlc && (
          <div className="absolute z-10 top-2 start-2 pointer-events-none font-mono text-[11px] leading-5 px-2 py-1 rounded-md bg-surface/70 backdrop-blur-sm" aria-hidden="true">
            <div className="flex flex-wrap gap-x-2">
              <span className="text-slate-200 font-semibold">{symbol} · {timeframe}</span>
              <span className="text-slate-500">O <span className="text-slate-200">{fmt(ohlc.open)}</span></span>
              <span className="text-slate-500">H <span className="text-slate-200">{fmt(ohlc.high)}</span></span>
              <span className="text-slate-500">L <span className="text-slate-200">{fmt(ohlc.low)}</span></span>
              <span className="text-slate-500">C <span className={ohlc.close >= ohlc.open ? 'text-emerald-400' : 'text-rose-400'}>{fmt(ohlc.close)}</span></span>
              {chg !== null && <span className={chg >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>}
            </div>
            {layers.ema && legendIdx >= 0 && (
              <div className="flex flex-wrap gap-x-2">
                {emas.map((period, k) => emaVals[k]?.[legendIdx] != null && (
                  <span key={period} style={{ color: k === 0 ? PAL[theme].ema50 : PAL[theme].ema200 }}>EMA{period} {fmt(emaVals[k][legendIdx] as number)}</span>
                ))}
                {kind === 'gold' && layers.bands && bbVals?.up[legendIdx] != null && (
                  <span className="text-violet-300">BB {fmt(bbVals.lo[legendIdx] as number)} · {fmt(bbVals.up[legendIdx] as number)}</span>
                )}
              </div>
            )}
          </div>
        )}
        {result?.dataQuality.ok && (result.dataQuality as any).stale && (
          <div className="absolute z-20 top-2 end-16 px-2.5 py-1 rounded-md bg-amber-500/15 ring-1 ring-amber-500/30 text-[11px] text-amber-200">
            {t('Feed retrying · showing the last good analysis', 'Flux en reconnexion · dernière analyse valide', 'الفلوكس كيتعاود · آخر تحليل صالح')}
          </div>
        )}
        {hoverIsSignal && setup && result && (
          <div role="tooltip" className="absolute z-20 w-72 max-w-[85%] p-3 rounded-lg border border-line bg-canvas/95 shadow-[var(--shadow-float)] text-xs pointer-events-none"
            style={{ left: Math.min(hover.x + 14, (containerRef.current?.clientWidth ?? 400) - 300), top: Math.max(8, hover.y - 160) }}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-white">{setup.direction} {setup.entryType} · {setup.setup}</span>
              <span className="font-mono text-gold-300">{result.score}/100</span>
            </div>
            <ul className="space-y-0.5">
              {result.checklist.map(c => (
                <li key={c.key} className="flex gap-1.5">{c.passed ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-label={t('passed', 'validé', 'محقق')} /> : <X className="w-3.5 h-3.5 shrink-0 text-rose-300" aria-label={t('failed', 'non validé', 'ما محققش')} />}<span className="text-slate-300 truncate">{lang === 'ar' && c.ruleAr ? c.ruleAr : c.rule}</span></li>
              ))}
            </ul>
          </div>
        )}
        {explain && (
          <div role="dialog" aria-label={t('Drawing explanation', 'Explication du dessin', 'شرح الرسم')} className="absolute z-30 w-80 max-w-[90%] p-3 rounded-lg border border-gold-500/30 bg-canvas/95 shadow-[var(--shadow-float)] text-xs"
            style={{ left: Math.max(8, Math.min(explain.x + 12, (containerRef.current?.clientWidth ?? 400) - 330)), top: Math.max(8, Math.min(explain.y + 12, (containerRef.current?.clientHeight ?? 400) - 160)) }}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-gold-200">{explain.title}</span>
              <button onClick={() => setExplain(null)} className="h-6 w-6 -me-1 rounded text-slate-400 hover:text-white" aria-label={t('Close', 'Fermer', 'سد')}>×</button>
            </div>
            <p className="text-slate-300 leading-relaxed">{explain.text}</p>
          </div>
        )}
        {result && !result.dataQuality.ok && (
          <div className="absolute z-20 top-3 left-3 max-w-[80%] px-3 py-2 rounded-lg bg-canvas/90 border border-line text-xs text-slate-300">{result.dataQuality.reason}</div>
        )}
      </div>

      {/* Layers + provenance */}
      <div className="flex flex-col gap-2 px-3 sm:px-4 py-2 border-t border-line text-[11px]">
        <span className="font-mono text-slate-500 truncate">
          {age !== null && (
            <span className={age > 5 ? 'text-rose-300' : 'text-emerald-400'}>{age > 5 ? `● ${t('Stale', 'Ancien', 'قديم')} · ${age}s` : `● Live · ${age}s`} · {t('every 1 s', 'chaque seconde', 'كل ثانية')} · </span>
          )}
          {result ? `${result.strategyName} · ${result.dataQuality.source} · ${t(`decides at each ${entryTf} close · click a drawing to explain it`, `décide à chaque clôture ${entryTf} · cliquez un dessin pour l’expliquer`, `كتقرر عند كل إغلاق ${entryTf} · كليكي على رسم باش يتشرح`)}` : ''}
        </span>
      </div>
    </div>
  );
};
