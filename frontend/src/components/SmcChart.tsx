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
  IPriceLine,
  createSeriesMarkers,
  Time,
} from 'lightweight-charts';
import { Check, ChevronDown, Expand, Layers as LayersIcon, Maximize2, Minimize2, X } from 'lucide-react';
import type { StrategyResult } from '../strategyTypes';
import { AgentOverlayPrimitive, type OverlayLayer, type OverlayTheme } from '../chart-overlays/agentOverlayPrimitive';
import { FSM_TONE, type AgentChartOverlayState } from '../agentOverlay';

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
  quote?: { time: number; source: string } | null; // when the provider itself last priced the pair (unix s)
  livePrice?: number | null;  // the price every second: the forming candle follows it
  onTimeframeChange: (tf: string) => void;
  isLoading?: boolean;
  onRefresh?: () => void;
  lang?: string;
  overlay?: AgentChartOverlayState | null;  // what this pair's own agent draws on its chart
  compact?: boolean;  // a pane of the 4-chart split screen
}

const TF_SEC: Record<string, number> = { M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800 };
type Layer = OverlayLayer | 'ema';
const LAYERS: { key: Layer; label: [string, string, string] }[] = [
  { key: 'sessions', label: ['Sessions & liquidity (Asia, London, PDH/PDL)', 'Sessions & liquidité', 'الجلسات والسيولة'] },
  { key: 'zones', label: ['Zones (FVG, OB, OTE, supply / demand)', 'Zones (FVG, OB, OTE, offre / demande)', 'المناطق (FVG، OB، OTE)'] },
  { key: 'structure', label: ['Structure (MSS, 50 %, divergence)', 'Structure (MSS, 50 %, divergence)', 'الهيكل (MSS، 50%، دايفرجنس)'] },
  { key: 'markers', label: ['Agent markers', 'Marqueurs de l’agent', 'علامات الوكيل'] },
  { key: 'smc', label: ['SMC view: structure, liquidity, OB, FVG (context, not a signal)', 'Vue SMC : structure, liquidité, OB, FVG (contexte, pas un signal)', 'قراءة SMC: الهيكل، السيولة، OB، FVG (سياق، ماشي إشارة)'] },
  { key: 'ema', label: ['EMA', 'EMA', 'EMA'] },
  { key: 'trade', label: ['Trade projection', 'Projection du trade', 'إسقاط الصفقة'] },
];
// every layer on by default, the SMC read included (structure, BOS / CHoCH, OB, FVG, BSL / SSL): one click away in Layers to hide
const DEFAULT_LAYERS = Object.fromEntries(LAYERS.map(l => [l.key, true])) as Record<Layer, boolean>;  // the SMC read is part of the agent: shown
// Candles shown when a pair / timeframe opens (the rest of the history stays one scroll away): close enough to read
// each candle, wide enough for the structure. Daily ≈ 3 months, weekly ≈ 1 year.
const VISIBLE_BARS: Record<string, number> = { M5: 160, M15: 150, M30: 130, H1: 120, H4: 100, D1: 66, W1: 52 };
const layerKey = (kind: string) => `ld_chart_layers_${kind}_v5`;  // v4: the SMC view off by default

const fmtLeft = (sec: number) => {
  const s = Math.max(0, Math.floor(sec));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s % 60).padStart(2, '0')}s`;
};
const str = (v: unknown) => (typeof v === 'string' ? v : '');
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

const PAL = {
  dark: { bg: 'rgba(9, 11, 16, 0.55)', grid: 'rgba(255,255,255,0.035)', text: '#8D96A6', border: '#1F2430', bull: '#16C784', bear: '#EA3943', ema50: '#4B85B8', ema200: '#C9A04A' },
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

export const SmcChart: React.FC<SmcChartProps> = ({ symbol, candles, result, timeframe, timeframes, entryTf, emas, emaNote, updatedAt, onTimeframeChange, isLoading, onRefresh, lang = 'en', overlay: overlayProp, compact = false, quote = null, livePrice = null }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const frameRef = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);  // folded: the chart first, the numbers one click away
  const kind = symbol;  // the chart's layer choices are kept per pair
  // Only what this pair's own agent emits for this chart
  // Strict pair isolation: an overlay drawn only if it is THIS pair's, and only its items within ±20 % of the price
  const overlayRaw = overlayProp ?? result?.overlay ?? null;
  const refPrice = candles.length ? candles[candles.length - 1].close : 0;
  const overlay = useMemo(() => {
    if (!overlayRaw) return null;
    if (overlayRaw.symbol && overlayRaw.symbol !== symbol.replace('/', '')) return null;
    if (!(refPrice > 0)) return overlayRaw;
    const near = (p: number) => Math.abs(p - refPrice) / refPrice <= 0.2;
    const box = overlayRaw.tradeExecutionBox;
    return {
      ...overlayRaw,
      zones: overlayRaw.zones.filter(z => near(z.topPrice) && near(z.bottomPrice)),
      priceLines: overlayRaw.priceLines.filter(l => near(l.startPrice) && near(l.endPrice)),
      markers: overlayRaw.markers.filter(m => near(m.price)),
      tradeExecutionBox: box && near(box.entryPrice) && near(box.stopLoss) ? box : null,
    };
  }, [overlayRaw, symbol, refPrice]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const primitiveRef = useRef<AgentOverlayPrimitive | null>(null);
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
  const box = overlay?.tradeExecutionBox ?? null;

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
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.14, bottom: 0.16 } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, barSpacing: 8, rightOffset: 22 },  // the labels sit right of the last candle
    });
    const minMove = decimals === 2 ? 0.01 : decimals === 4 ? 0.0001 : 0.00001;
    const cs = chart.addSeries(CandlestickSeries, {
      upColor: p.bull, downColor: p.bear, borderUpColor: p.bull, borderDownColor: p.bear, wickUpColor: p.bull, wickDownColor: p.bear,
      priceFormat: { type: 'price', precision: decimals, minMove },
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } });
    // no EMA tags on the price axis (they crowded the price and the trade levels): their values are in the legend
    const emaLines = [p.ema50, p.ema200].map(color => chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }));
    const prim = new AgentOverlayPrimitive();
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
      const hit = prim.findAt(param.point.x, param.point.y, el.clientWidth - chart.priceScale('right').width());
      if (!hit) { setExplain(null); return; }
      const at = { x: param.point.x, y: param.point.y };
      setExplain({ ...at, title: hit.label, text: '…' });
      apiFetch('/api/agent/explain-drawing', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: symbolRef.current, drawingId: hit.id, lang: langRef.current, asOf: Number(new URLSearchParams(window.location.search).get('asOf')) || 0 }) })
        .then(r => r.json())
        .then(j => setExplain({ ...at, title: hit.label, text: j.success ? j.text : j.detail || j.error || '—' }))
        .catch(() => setExplain({ ...at, title: hit.label, text: '⚠' }));
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
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      emaRefs.current = [];
      markersRef.current = null;
      primitiveRef.current = null;
      // Removed on the next frame: a repaint already scheduled for this one would otherwise draw a disposed chart
      requestAnimationFrame(() => { try { chart.remove(); } catch { /* already gone */ } });
    };
  }, [theme, decimals]);

  // Zero time décalage: UTC seconds, each intraday candle snapped to the open of its timeframe slot, sorted, one per slot
  const bars = useMemo(() => {
    const step = TF_SEC[timeframe] || 0;
    const bySlot = new Map<number, SmcChartCandle>();
    for (const c of candles) {
      if (!c || ![c.open, c.high, c.low, c.close].every(v => typeof v === 'number' && Number.isFinite(v))) continue;
      let t = Number(c.time);
      if (t > 1e11) t = Math.floor(t / 1000);  // milliseconds → seconds
      if (step > 0 && step < 86400) t -= t % step;  // daily / weekly bars keep the provider's own session open
      bySlot.set(t, { ...c, time: t });
    }
    return [...bySlot.values()].sort((a, b) => a.time - b.time);
  }, [candles, timeframe]);

  const barsLenRef = useRef(0);
  const barTimesRef = useRef<number[]>([]);
  barsLenRef.current = bars.length;
  const resetView = () => {
    const n = barsLenRef.current;
    const show = VISIBLE_BARS[timeframe] ?? 120;
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n + Math.max(4, Math.round(show * 0.08)) });
  };

  // The forming candle follows the live price every second (between two candle reloads)
  const liveBar = useRef<{ time: number; open: number; high: number; low: number } | null>(null);
  useEffect(() => { liveBar.current = null; }, [symbol, timeframe]);
  useEffect(() => {
    const cs = candleRef.current;
    const last = bars[bars.length - 1];
    if (!cs || !last || !livePrice || !(livePrice > 0)) return;
    if (Math.abs(livePrice - last.close) / last.close > 0.2) return;  // a price of another pair (mid-switch): never drawn on these candles
    if (Date.now() / 1000 >= last.time + tfSec) return;  // the last candle is closed (market shut): leave it as it is
    const lb = liveBar.current && liveBar.current.time === last.time ? liveBar.current : { time: last.time, open: last.open, high: last.high, low: last.low };
    lb.high = Math.max(lb.high, livePrice);
    lb.low = Math.min(lb.low, livePrice);
    liveBar.current = lb;
    cs.update({ time: last.time as Time, open: lb.open, high: lb.high, low: lb.low, close: livePrice });
  }, [livePrice, bars, tfSec]);

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
      line.applyOptions({ color: k === 0 ? p.ema50 : p.ema200, title: '' });  // the EMA values are in the legend, not in the margin
    });
    const key = `${symbol}-${timeframe}-${theme}`;
    if (fitKeyRef.current !== key && bars.length) {
      fitKeyRef.current = key;
      barTimesRef.current = bars.map(b => b.time);
      resetView();
    }
  }, [bars, symbol, timeframe, theme, layers.ema, emas, kind]);

  // Daily / weekly axis shows dates only; forex has no real volume on the free feed, so its pane is hidden
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const hasVolume = bars.some(b => (b.volume || 0) > 0);
    chart.applyOptions({ timeScale: { timeVisible: tfSec < 86400 } });
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.14, bottom: hasVolume ? 0.16 : 0.06 } });
    volRef.current?.applyOptions({ visible: hasVolume });
  }, [bars, tfSec, theme, decimals]);

  // The trade projection's levels on the price axis (entry, stop, TP1, TP2), readable at any zoom
  useEffect(() => {
    const cs = candleRef.current;
    if (!cs) return;
    const lines: IPriceLine[] = [];
    if (box && layers.trade) {
      const p = PAL[theme];
      const add = (price: number, color: string, title: string, style = LineStyle.Solid) =>
        lines.push(cs.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title, lineVisible: false }));
      add(box.entryPrice, '#D4AF37', t('Entry', 'Entrée', 'دخول'));
      add(box.stopLoss, p.bear, box.status === 'TP1_HIT_BE' ? 'SL · BE' : 'SL');
      const oneTarget = Math.abs(box.tp1Price - box.tp2Price) < 1e-9;
      if (oneTarget) add(box.tp2Price, p.bull, 'TP');
      else { add(box.tp1Price, p.bull, 'TP1', LineStyle.Dashed); add(box.tp2Price, p.bull, 'TP2'); }
    }
    return () => { lines.forEach(l => { try { cs.removePriceLine(l); } catch { /* chart rebuilt */ } }); };
  }, [box?.entryPrice, box?.stopLoss, box?.tp1Price, box?.tp2Price, box?.status, layers.trade, theme, decimals, lang]);

  // A new pair / timeframe: forget the old crosshair and explanation
  useEffect(() => { chartRef.current?.clearCrosshairPosition(); setExplain(null); }, [symbol, timeframe]);

  // The agent's overlay: zones, lines and trade projection on the canvas; its markers as the series' own markers
  useEffect(() => {
    const prim = primitiveRef.current;
    if (!prim) return;
    const { ema: _ema, ...drawLayers } = layers;
    prim.update({ state: overlay, barTimes: bars.map(b => b.time), tfSec, layers: drawLayers as Record<OverlayLayer, boolean>, theme, decimals });
    const markers: any[] = [];
    if (overlay && layers.markers && bars.length) {
      for (const m of overlay.markers) {
        if (m.id.startsWith('SMC-') && !layers.smc) continue;  // the SMC swing labels follow their own layer
        let snap: number | null = null;  // on the bar that contains the marker's time on this timeframe
        for (const b of bars) { if (b.time <= m.time) snap = b.time; else break; }
        if (snap !== null) markers.push({ time: snap as Time, position: m.position, color: m.color, shape: m.shape, text: m.text, size: 1.1 });
      }
      markers.sort((a, b) => a.time - b.time);
    }
    markersRef.current?.setMarkers(markers);
  }, [overlay, bars, layers, tfSec, timeframe, theme, decimals]);

  const last = bars[bars.length - 1];
  const ohlc = hover.c || last;
  const legendIdx = ohlc ? bars.findIndex(b => b.time === ohlc.time) : -1;
  const closesAll = useMemo(() => bars.map(b => b.close), [bars]);
  const emaVals = useMemo(() => emas.map(period => ema(closesAll, period)), [closesAll, emas]);
  const prevClose = legendIdx > 0 ? bars[legendIdx - 1].close : null;
  const chg = ohlc && prevClose ? ((ohlc.close - prevClose) / prevClose) * 100 : null;

  // The numbers this strategy decides on, straight from its own output (no recomputation here)
  const facts = (result?.facts ?? {}) as Record<string, unknown>;
  const pip = result?.spec.pipSize ?? (symbol === 'XAU/USD' ? 0.1 : 0.0001);
  const trendTone = (t: string) => (t === 'bullish' ? 'text-emerald-400' : t === 'bearish' ? 'text-rose-400' : 'text-slate-300');
  const trendWord = (w: string) => (w === 'bullish' ? t('bullish', 'haussière', 'صاعد') : w === 'bearish' ? t('bearish', 'baissière', 'هابط')
    : w === 'flat' || w === 'none' ? t('none', 'aucune', 'بلا اتجاه') : w || '—');
  const keyFacts: { label: string; value: string; tone?: string }[] = [];
  if (overlay) {
    keyFacts.push({ label: t('Agent', 'Agent', 'الوكيل'), value: overlay.agentId.split('_')[1] || overlay.agentId, tone: 'text-gold-200' });
    keyFacts.push({ label: t('Session', 'Session', 'الجلسة'), value: overlay.metrics.sessionName.replace('Outside the plan window', t('off hours', 'hors horaires', 'برا الوقت')).replace(' window', '') });
    keyFacts.push({ label: 'Spread', value: `${overlay.metrics.spreadPips.toFixed(1)}p` });
    keyFacts.push({ label: `ATR`, value: `${overlay.metrics.atrPips.toFixed(0)}p` });
    keyFacts.push({ label: t('State', 'État', 'الحالة'), value: overlay.metrics.confluenceTag.toLowerCase(), tone: 'text-sky-300' });
  }
  if (result?.dataQuality.ok && num(facts.ema50) !== null && num(facts.ema200) !== null) keyFacts.push({ label: 'EMA 50/200', value: `${fmt(num(facts.ema50)!)} / ${fmt(num(facts.ema200)!)}` });
  const entrySec = TF_SEC[entryTf] || 3600;
  const nowSec = nowMs / 1000;
  const nextClose = Math.ceil(nowSec / entrySec) * entrySec;
  if (result?.market.isOpen && updatedAt) keyFacts.push({ label: t(`${entryTf} close`, `Clôture ${entryTf}`, `إغلاق ${entryTf}`), value: fmtLeft(nextClose - nowSec), tone: 'text-gold-300' });
  if (result?.news.next) keyFacts.push({ label: t('News', 'News', 'خبر'), value: result.news.next.replace(/ m\/m| q\/q| y\/y/g, '').replace(/ (\d{4})-(\d{2})-(\d{2}) /, ' $3/$2 '), tone: result.news.blocked ? 'text-rose-300' : undefined });
  const lastTrade = facts.lastTrade as { state: string; outcome: string | null; r: number | null } | null | undefined;
  if (lastTrade) keyFacts.push({ label: t('Last', 'Dernier', 'آخر'), value: lastTrade.outcome ? `${lastTrade.outcome} ${lastTrade.r !== null ? `${lastTrade.r > 0 ? '+' : ''}${lastTrade.r.toFixed(2)}R` : ''}` : lastTrade.state,
    tone: lastTrade.outcome === 'WIN' ? 'text-emerald-300' : lastTrade.outcome === 'LOSS' ? 'text-rose-300' : 'text-gold-200' });

  const shownLayers = LAYERS.map(l => ({ key: l.key, label: l.key === 'ema' ? `EMA ${emas.join('/')} · ${emaNote}` : l.label[li] }));
  const age = updatedAt ? Math.max(0, Math.round((nowMs - updatedAt) / 1000)) : null;
  // the price's own age at its provider (free feeds: forex every ~10–60 s, gold spot every ~30 s)
  const quoteAge = quote?.time ? Math.max(0, Math.round(nowMs / 1000 - quote.time)) : null;
  const signalBarTime = setup ? setup.signalTime - (TF_SEC[entryTf] || tfSec) : null;
  const hoverIsSignal = !!(setup && hover.c && signalBarTime !== null && hover.c.time <= signalBarTime && hover.c.time + tfSec > signalBarTime);
  const headline = result?.headline ?? '';
  const shortHead = headline.split(/: | · /)[0].replace(/ \((\d\d:\d\d)–(\d\d:\d\d) GMT and (\d\d:\d\d)–(\d\d:\d\d) GMT\)/, ' ($1–$2 · $3–$4 GMT)');
  const statusTone = result?.status === 'SIGNAL' ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
    : result?.status === 'WATCH' ? 'bg-gold-500/15 text-gold-200 ring-gold-500/30'
    : 'bg-slate-500/10 text-slate-300 ring-slate-500/30';

  return (
    <div ref={frameRef} className={`flex flex-col border glass overflow-hidden ${full ? 'fixed inset-0 z-[60] rounded-none' : 'rounded-[var(--radius-card)]'}`}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-4 py-2 border-b border-line">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-white font-mono">{symbol}</span>
          <span className="px-1.5 py-0.5 rounded bg-surface-2 text-[11px] font-mono text-gold-300">{timeframe}</span>
          
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
                className="absolute end-0 mt-1.5 w-60 rounded-xl border glass-strong p-1.5 z-40">
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
        </div>
      </div>

      {/* Status strip */}
      <div hidden={compact} className="flex items-center gap-x-3 px-3 sm:px-4 py-1.5 border-b border-line bg-surface-2/50 text-xs">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md ring-1 ring-inset font-medium ${statusTone}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
          {result ? (result.status === 'NO_TRADE' ? t('No trade', 'Pas de trade', 'لا صفقة') : `${setup?.direction ?? ''} ${result.status === 'SIGNAL' ? t('Signal', 'Signal', 'إشارة') : result.status === 'WATCH' ? t('Watch', 'À surveiller', 'مراقبة') : t('Ignored', 'Ignoré', 'متجاهل')}`) : t('Loading', 'Chargement', 'تحميل')}
          {result?.setup && ` · ${result.score}`}
        </span>
        <span className="text-slate-400 min-w-0 flex-1 truncate" title={headline}>{result ? shortHead : t('Loading the analysis…', 'Chargement de l’analyse…', 'كيتحمل التحليل…')}</span>
        {(keyFacts.length > 0 || (pastStats && pastStats.trades > 0)) && (
          <button onClick={() => setDetailsOpen(o => !o)} aria-expanded={detailsOpen}
            className="shrink-0 inline-flex items-center gap-1 text-slate-500 hover:text-gold-300 cursor-pointer">
            {t('Details', 'Détails', 'التفاصيل')}<ChevronDown className={`w-3.5 h-3.5 transition-transform ${detailsOpen ? 'rotate-180' : ''}`} />
          </button>
        )}
        <span className="shrink-0 font-mono text-slate-500">
          <span className={result?.bias.direction === 'BULLISH' ? 'text-emerald-400' : result?.bias.direction === 'BEARISH' ? 'text-rose-400' : 'text-slate-400'}>{result ? (result.bias.direction === 'BULLISH' ? t('Bullish', 'Haussière', 'صاعد') : result.bias.direction === 'BEARISH' ? t('Bearish', 'Baissière', 'هابط') : t('Neutral', 'Neutre', 'محايد')) : '—'}</span>
        </span>
      </div>

      {/* Key numbers of the strategy */}
      {detailsOpen && !compact && (
        <div className="px-3 sm:px-4 py-2 border-b border-line text-[11px] space-y-2" aria-label={t('Strategy key levels', 'Chiffres clés de la stratégie', 'أرقام الاستراتيجية')}>
          {headline && <p className="text-slate-400 leading-snug">{headline}</p>}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-1.5 font-mono">
            {pastStats && pastStats.trades > 0 && (
              <div className="rounded-md bg-surface-2 px-2 py-1" title={t('Closed trades of the strategy on this pair', 'Trades clôturés de la stratégie sur cette paire', 'الصفقات لي سدات ف هاد الزوج')}>
                <div className="text-[10px] text-slate-500">{t('Trades', 'Trades', 'صفقات')} {pastStats.trades}</div>
                <div><span className="text-emerald-400">{pastStats.tp}</span><span className="text-slate-500">/</span><span className="text-slate-300">{pastStats.be}</span><span className="text-slate-500">/</span><span className="text-rose-400">{pastStats.sl}</span>{' '}
                  <span className={pastStats.totalR >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{pastStats.totalR >= 0 ? '+' : ''}{pastStats.totalR.toFixed(1)}R</span></div>
              </div>
            )}
            {keyFacts.map((k, i) => (
              <div key={i} className="rounded-md bg-surface-2 px-2 py-1 min-w-0">
                <div className="text-[10px] text-slate-500 truncate">{k.label}</div>
                <div className={`truncate ${k.tone ?? 'text-slate-200'}`} title={k.value}>{k.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chart */}
      <div className={`relative ${full ? 'flex-1' : compact ? 'h-[36vh] min-h-[260px]' : 'h-[58vh] min-h-[380px] max-h-[680px]'}`}>
        <div ref={containerRef} className="absolute inset-0" />
        {overlay && (
          <div className="absolute z-10 top-2 start-2 max-w-[calc(100%-90px)] pointer-events-none flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface/80 backdrop-blur-sm text-[11px]" role="status">
            <span className={`shrink-0 px-1.5 py-0.5 rounded font-mono font-bold ring-1 ring-inset ${FSM_TONE[overlay.fsmState]}`}>{overlay.fsmState.replace('_', ' ')}</span>
            {compact && <span className="text-slate-200 truncate">{overlay.statusBannerText.split(' · ').slice(2).join(' · ').split(/: /)[0]}</span>}
          </div>
        )}
        {ohlc && !compact && (
          <div className="absolute z-10 top-10 start-2 pointer-events-none font-mono text-[11px] leading-5 px-2 py-1 rounded-md bg-surface/70 backdrop-blur-sm" aria-hidden="true">
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
          {age !== null && <span className={age > 5 ? 'text-rose-300' : 'text-emerald-400'}>{age > 5 ? `● ${t('Stale', 'Ancien', 'قديم')} · ${age}s` : '● Live'}</span>}
          {age !== null && quoteAge !== null && (
            <span className={quoteAge > 120 ? 'text-amber-300' : 'text-slate-400'} title={quote?.source}>
              {' · '}{t('price', 'prix', 'الثمن')} {quoteAge < 90 ? `${quoteAge} s` : `${Math.round(quoteAge / 60)} min`}{quote?.source ? ` · ${quote.source.replace('Interbank ', '')}` : ''}
            </span>
          )}
        </span>
      </div>
    </div>
  );
};
