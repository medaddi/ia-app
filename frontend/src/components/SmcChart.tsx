import { apiFetch } from '../api';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { InstrumentSymbol } from '../instruments';
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
  createSeriesMarkers,
  Time,
} from 'lightweight-charts';
import { Check, Maximize2, RefreshCw, X } from 'lucide-react';
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

const TF_SEC: Record<string, number> = { M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400, W1: 604800 };
type Layer = DrawingLayer | 'ema';
const LAYERS: { key: Layer; label: string }[] = [
  { key: 'sessions', label: 'Sessions' },
  { key: 'levels', label: 'Key levels' },
  { key: 'liquidity', label: 'Liquidity' },
  { key: 'structure', label: 'Structure' },
  { key: 'swings', label: 'Swings' },
  { key: 'fvg', label: 'FVG' },
  { key: 'ob', label: 'OB' },
  { key: 'fib', label: 'Fib' },
  { key: 'ema', label: 'EMA' },
  { key: 'trade', label: 'Trade' },
];
const DEFAULT_LAYERS = Object.fromEntries(LAYERS.map(l => [l.key, true])) as Record<Layer, boolean>;
const LAYER_KEY = 'exunu_chart_layers_v1';
const ALWAYS_SHOWN: Layer[] = ['ema', 'trade'];

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
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNowMs(Date.now()), 1000); return () => clearInterval(id); }, []);
  const [layers, setLayers] = useState<Record<Layer, boolean>>(() => {
    try { return { ...DEFAULT_LAYERS, ...JSON.parse(localStorage.getItem(LAYER_KEY) || '{}') }; } catch { return DEFAULT_LAYERS; }
  });

  const decimals = result?.spec.decimals ?? (symbol === 'XAU/USD' ? 2 : 5);
  const fmt = (v: number) => v.toFixed(decimals);
  const tfSec = TF_SEC[timeframe] || 900;
  const setup = result?.setup ?? null;
  const signalBarTime = setup ? setup.signalTime - (TF_SEC[result!.timeframes.entry.split('/')[0]] || tfSec) : null;

  // Follow the app's light/dark theme
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(readTheme()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    try { localStorage.setItem(LAYER_KEY, JSON.stringify(layers)); } catch { /* storage unavailable */ }
  }, [layers]);

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
        .then(j => setExplain({ ...at, title: hit.text || hit.layer, text: j.success ? j.text : j.error || 'No explanation' }))
        .catch(() => setExplain({ ...at, title: hit.text || hit.layer, text: 'Agent unreachable' }));
    });

    chartRef.current = chart;
    candleRef.current = cs;
    volRef.current = vol;
    emaRefs.current = emaLines;
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

  // Candles, volume, EMAs
  useEffect(() => {
    const cs = candleRef.current, chart = chartRef.current;
    if (!cs || !chart) return;
    const p = PAL[theme];
    cs.setData(bars.map(b => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })));
    volRef.current?.setData(bars.map(b => ({ time: b.time as Time, value: b.volume || 0, color: b.close >= b.open ? 'rgba(22,199,132,0.22)' : 'rgba(234,57,67,0.22)' })));
    const closes = bars.map(b => b.close);
    const toLine = (vals: (number | null)[]) => bars.flatMap((b, i) => (vals[i] === null ? [] : [{ time: b.time as Time, value: vals[i] as number }]));
    // Only the averages this strategy's rules use (gold EMA 50/200, forex EMA 20)
    emaRefs.current.forEach((line, k) => {
      const period = emas[k];
      line.setData(layers.ema && period ? toLine(ema(closes, period)) : []);
      line.applyOptions({ color: k === 0 ? p.ema50 : p.ema200, title: period ? `EMA${period}` : '' });
    });
    const key = `${symbol}-${timeframe}-${theme}`;
    if (fitKeyRef.current !== key && bars.length) {
      fitKeyRef.current = key;
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 140), to: bars.length + 10 });
    }
  }, [bars, symbol, timeframe, theme, layers.ema, emas]);

  // Drawings + entry arrow
  useEffect(() => {
    const prim = primitiveRef.current;
    if (!prim) return;
    const { ema: _ema, ...drawLayers } = layers;
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

  // The numbers this strategy decides on, straight from its own output (no recomputation here)
  const facts = (result?.facts ?? {}) as Record<string, unknown>;
  const pip = result?.spec.pipSize ?? (symbol === 'XAU/USD' ? 0.1 : 0.0001);
  const trendTone = (t: string) => (t === 'bullish' ? 'text-emerald-400' : t === 'bearish' ? 'text-rose-400' : 'text-slate-300');
  const keyFacts: { label: string; value: string; tone?: string }[] = [];
  if (result?.dataQuality.ok) {
    if (symbol === 'XAU/USD') {
      const rng = facts.range20h as { high?: number; low?: number } | undefined;
      keyFacts.push({ label: 'H1 trend', value: str(facts.trend) || '—', tone: trendTone(str(facts.trend)) });
      if (num(facts.ema50) !== null) keyFacts.push({ label: 'EMA50', value: fmt(num(facts.ema50)!) });
      if (num(facts.ema200) !== null) keyFacts.push({ label: 'EMA200', value: fmt(num(facts.ema200)!) });
      if (num(facts.atrH1) !== null) keyFacts.push({ label: 'ATR H1', value: `$${num(facts.atrH1)!.toFixed(2)}` });
      if (rng?.high && rng?.low) keyFacts.push({ label: '20h range', value: `${fmt(rng.low)} – ${fmt(rng.high)}` });
    } else {
      keyFacts.push({ label: 'W1', value: str(facts.weeklyTrend) || '—', tone: trendTone(str(facts.weeklyTrend)) });
      keyFacts.push({ label: 'D1', value: str(facts.dailyTrend) || '—', tone: trendTone(str(facts.dailyTrend)) });
      if (num(facts.atrH4) !== null) keyFacts.push({ label: 'ATR H4', value: `${(num(facts.atrH4)! / pip).toFixed(1)} pips` });
      const aoi = (facts.areasOfInterest as { kind: string; price: number }[] | undefined) ?? [];
      aoi.slice(0, 3).forEach((a, k) => keyFacts.push({ label: k === 0 ? 'AOI' : '', value: `${a.kind} ${fmt(a.price)}`, tone: a.kind === 'support' ? 'text-emerald-300' : 'text-rose-300' }));
    }
  }
  const entrySec = TF_SEC[entryTf] || 3600;
  const nowSec = nowMs / 1000;
  const nextClose = Math.ceil(nowSec / entrySec) * entrySec;
  if (result?.market.isOpen && updatedAt) keyFacts.push({ label: `Next ${entryTf} close`, value: fmtLeft(nextClose - nowSec), tone: 'text-gold-300' });
  if (result?.news.next) keyFacts.push({ label: 'News', value: result.news.next, tone: result.news.blocked ? 'text-rose-300' : undefined });
  const lastTrade = facts.lastTrade as { state: string; outcome: string | null; r: number | null } | null | undefined;
  if (lastTrade) keyFacts.push({ label: 'Last trade', value: lastTrade.outcome ? `${lastTrade.outcome} ${lastTrade.r !== null ? `${lastTrade.r > 0 ? '+' : ''}${lastTrade.r.toFixed(2)}R` : ''}` : lastTrade.state,
    tone: lastTrade.outcome === 'WIN' ? 'text-emerald-300' : lastTrade.outcome === 'LOSS' ? 'text-rose-300' : 'text-gold-200' });

  // Only the layers this strategy actually draws (plus its averages and the trade)
  const present = new Set((result?.drawings ?? []).map(d => d.layer));
  const shownLayers = LAYERS.filter(l => ALWAYS_SHOWN.includes(l.key) || present.has(l.key as DrawingLayer))
    .map(l => (l.key === 'ema' ? { ...l, label: `EMA ${emas.join('/')} · ${emaNote}` } : l));
  const age = updatedAt ? Math.max(0, Math.round((nowMs - updatedAt) / 1000)) : null;
  const hoverIsSignal = !!(setup && hover.c && signalBarTime !== null && hover.c.time <= signalBarTime && hover.c.time + tfSec > signalBarTime);
  const statusTone = result?.status === 'SIGNAL' ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
    : result?.status === 'WATCH' ? 'bg-gold-500/15 text-gold-200 ring-gold-500/30'
    : 'bg-slate-500/10 text-slate-300 ring-slate-500/30';

  return (
    <div className="flex flex-col rounded-[var(--radius-card)] border border-line bg-surface overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-4 py-2.5 border-b border-line">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold text-white">{symbol}</span>
          <span className="text-xs text-slate-500">{timeframe}</span>
          {ohlc && (
            <div className="hidden md:flex items-center gap-2 font-mono text-xs text-slate-400">
              <span>O <span className="text-slate-200">{fmt(ohlc.open)}</span></span>
              <span>H <span className="text-slate-200">{fmt(ohlc.high)}</span></span>
              <span>L <span className="text-slate-200">{fmt(ohlc.low)}</span></span>
              <span>C <span className={ohlc.close >= ohlc.open ? 'text-emerald-400' : 'text-rose-400'}>{fmt(ohlc.close)}</span></span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div role="tablist" aria-label="Timeframe" className="flex items-center rounded-lg bg-surface-2 border border-line p-0.5">
            {timeframes.map(tf => (
              <button key={tf} role="tab" aria-selected={tf === timeframe} onClick={() => onTimeframeChange(tf)}
                className={`min-w-[40px] h-8 px-2 rounded-md font-mono text-xs transition-colors ${tf === timeframe ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-100'}`}>
                {tf}
              </button>
            ))}
          </div>
          <button onClick={() => chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 140), to: bars.length + 10 })}
            className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2" aria-label="Reset view" title="Reset view">
            <Maximize2 className="w-4 h-4" />
          </button>
          {onRefresh && (
            <button onClick={onRefresh} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2" aria-label="Refresh" title="Refresh">
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-gold-400' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Status strip */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 sm:px-4 py-2 border-b border-line bg-surface-2/50 text-xs">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md ring-1 ring-inset font-medium ${statusTone}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
          {result ? (result.status === 'NO_TRADE' ? 'No trade' : `${setup?.direction ?? ''} ${result.status === 'SIGNAL' ? 'Signal' : result.status === 'WATCH' ? 'Watch' : 'Ignored'}`) : 'Loading'}
          {result?.setup && ` · ${result.score}`}
        </span>
        <span className="text-slate-400 min-w-0 truncate">{result?.headline ?? 'Loading analysis…'}</span>
        <span className="ms-auto font-mono text-slate-500">
          Bias <span className={result?.bias.direction === 'BULLISH' ? 'text-emerald-400' : result?.bias.direction === 'BEARISH' ? 'text-rose-400' : 'text-slate-400'}>{result?.bias.direction ?? '—'}</span>
          {result?.market.window ? <span className="text-gold-300"> · {result.market.window}</span> : null}
        </span>
      </div>

      {/* Key numbers of the strategy */}
      {keyFacts.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 sm:px-4 py-2 border-b border-line text-xs font-mono" aria-label="Strategy key levels">
          {keyFacts.map((k, i) => (
            <span key={i} className="whitespace-nowrap">
              {k.label && <span className="text-slate-500">{k.label} </span>}
              <span className={k.tone ?? 'text-slate-200'}>{k.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className="relative h-[440px] sm:h-[540px]">
        <div ref={containerRef} className="absolute inset-0" />
        {hoverIsSignal && setup && result && (
          <div role="tooltip" className="absolute z-20 w-72 max-w-[85%] p-3 rounded-lg border border-line bg-canvas/95 shadow-[var(--shadow-float)] text-xs pointer-events-none"
            style={{ left: Math.min(hover.x + 14, (containerRef.current?.clientWidth ?? 400) - 300), top: Math.max(8, hover.y - 160) }}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-white">{setup.direction} {setup.entryType} · Setup {setup.setup}</span>
              <span className="font-mono text-gold-300">{result.score}/100</span>
            </div>
            <ul className="space-y-0.5">
              {result.checklist.map(c => (
                <li key={c.key} className="flex gap-1.5">{c.passed ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-label="passed" /> : <X className="w-3.5 h-3.5 shrink-0 text-rose-300" aria-label="failed" />}<span className="text-slate-300 truncate">{c.rule}</span></li>
              ))}
            </ul>
          </div>
        )}
        {explain && (
          <div role="dialog" aria-label="Drawing explanation" className="absolute z-30 w-80 max-w-[90%] p-3 rounded-lg border border-gold-500/30 bg-canvas/95 shadow-[var(--shadow-float)] text-xs"
            style={{ left: Math.max(8, Math.min(explain.x + 12, (containerRef.current?.clientWidth ?? 400) - 330)), top: Math.max(8, Math.min(explain.y + 12, (containerRef.current?.clientHeight ?? 400) - 160)) }}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-gold-200">{explain.title}</span>
              <button onClick={() => setExplain(null)} className="h-6 w-6 -me-1 rounded text-slate-400 hover:text-white" aria-label="Close">×</button>
            </div>
            <p className="text-slate-300 leading-relaxed">{explain.text}</p>
          </div>
        )}
        {result && !result.dataQuality.ok && (
          <div className="absolute z-20 top-3 left-3 max-w-[80%] px-3 py-2 rounded-lg bg-canvas/90 border border-line text-xs text-slate-300">{result.dataQuality.reason}</div>
        )}
      </div>

      {/* Layers + provenance */}
      <div className="flex flex-col gap-2 px-3 sm:px-4 py-2 border-t border-line text-xs">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Chart layers">
          {shownLayers.map(l => (
            <button key={l.key} aria-pressed={layers[l.key]} onClick={() => setLayers(s => ({ ...s, [l.key]: !s[l.key] }))}
              className={`h-7 px-2.5 rounded-md border transition-colors ${layers[l.key] ? 'border-gold-500/40 bg-gold-500/10 text-gold-200' : 'border-line text-slate-500 hover:text-slate-300'}`}>
              {l.label}
            </button>
          ))}
        </div>
        <span className="font-mono text-slate-500 truncate">
          {age !== null && (
            <span className={age > 15 ? 'text-rose-300' : 'text-emerald-400'}>{age > 15 ? `● Stale · ${age}s` : `● Live · ${age}s ago`} · every 5 s · </span>
          )}
          {result ? `${result.strategyName} · ${result.dataQuality.source} · decides at each ${entryTf} close · click a drawing to explain it` : ''}
        </span>
      </div>
    </div>
  );
};
