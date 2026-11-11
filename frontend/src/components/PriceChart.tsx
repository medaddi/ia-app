import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import { Expand, Layers, Maximize2, Minimize2, Shapes } from 'lucide-react';
import type { InstrumentSymbol } from '../instruments';
import { SmcDrawingPrimitive, type SmcDrawing } from '../chart/smcDrawing';
import { computeSmc, emaLine } from '../chart/smcOverlay';

/**
 * A pair's clean chart: candles, volume, the forming candle following the live price, a legend and the timeframe buttons.
 * What it draws is the pair team's analysis (backend smc/chart.py, drawn by chart/smcDrawing.ts): order blocks and FVGs as
 * labelled boxes, BOS / CHoCH / IDM / liquidity as labelled segments on their candles, "Liquidity Sweep" at the wick, and the
 * setup's trade as TP / SL areas, its entry / SL / TP prices on the axis.
 */
export interface ChartLevel { price: number; label: string; kind: 'entry' | 'sl' | 'tp' }
export interface PriceCandle { time: number; open: number; high: number; low: number; close: number; volume?: number }

interface PriceChartProps {
  symbol: InstrumentSymbol;
  candles: PriceCandle[];
  decimals: number;
  timeframe: string;
  timeframes: string[];
  onTimeframeChange: (tf: string) => void;
  livePrice?: number | null;  // the price every second: the forming candle follows it
  quote?: { time: number; source: string } | null;  // when the provider itself last priced the pair (unix s)
  updatedAt: number;  // ms of the last candle reload
  lang?: string;
  levels?: ChartLevel[];  // the setup's entry / SL / TP, as axis labels
  drawing?: SmcDrawing | null;  // the team's analysis
  extra?: React.ReactNode;  // one more control for the toolbar (the terminal's Top 5 switch)
  tabValue?: string;  // the selected tab when it is not this chart's own timeframe (the H1 + M5 split view)
  compact?: boolean;  // a shorter chart (one of two in the split view)
}

/** The timeframe tabs' names ("SPLIT" is the H1 + M5 split view). */
export const TAB_LABEL = (tf: string) => (tf === 'SPLIT' ? 'H4 + H1' : tf);

const TF_SEC: Record<string, number> = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H2: 7200, H4: 14400, D1: 86400, W1: 604800 };
// Candles shown when a pair / timeframe opens (the rest of the history stays one scroll away)
const VISIBLE_BARS: Record<string, number> = { M1: 180, M5: 160, M15: 150, M30: 130, H1: 120, H2: 110, H4: 100, D1: 66, W1: 52 };
const PAL = {
  dark: { bg: 'rgba(9, 11, 16, 0.55)', grid: 'rgba(255,255,255,0.035)', text: '#8D96A6', border: '#1F2430', bull: '#16C784', bear: '#EA3943' },
  light: { bg: '#FFFFFF', grid: 'rgba(0,0,0,0.05)', text: '#4D5566', border: '#DDD6C8', bull: '#0E9F6E', bear: '#D92D3A' },
};
type Theme = keyof typeof PAL;
const readTheme = (): Theme => (typeof document !== 'undefined' && !document.documentElement.classList.contains('dark') ? 'light' : 'dark');

export const PriceChart: React.FC<PriceChartProps> = ({ symbol, candles, decimals, timeframe, timeframes, onTimeframeChange, livePrice = null, quote = null, updatedAt, lang = 'en', levels = [], drawing = null, tabValue, compact = false, extra = null }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const fitKeyRef = useRef('');
  const drawRef = useRef<SmcDrawingPrimitive | null>(null);
  // A calm chart by default: candles, the zone in play, the 1D structure levels, the proposed trade and the 50 EMA.
  // "Details" (off by default, kept per browser) adds the secondary objects: the other zones, round numbers, 4H levels,
  // HH / HL markers, the SoS line, premium / discount, BOS / CHoCH, sessions, liquidity and FVGs.
  const [showDetails, setShowDetails] = useState<boolean>(() => { try { return localStorage.getItem('ld_chart_details') === '1'; } catch { return false; } });
  const toggleDetails = () => setShowDetails(v => { try { localStorage.setItem('ld_chart_details', v ? '0' : '1'); } catch { /* storage blocked */ } return !v; });
  const [showEma, setShowEma] = useState<boolean>(() => { try { return localStorage.getItem('ld_chart_ema') !== '0'; } catch { return true; } });
  const toggleEma = () => setShowEma(v => { try { localStorage.setItem('ld_chart_ema', v ? '0' : '1'); } catch { /* storage blocked */ } return !v; });
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [full, setFull] = useState(false);
  const [hover, setHover] = useState<PriceCandle | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const li = lang === 'fr' ? 1 : lang === 'ar' ? 2 : 0;
  const t = (en: string, fr: string, ar: string) => [en, fr, ar][li];
  const fmt = (v: number) => v.toFixed(decimals);
  const tfSec = TF_SEC[timeframe] || 900;

  useEffect(() => { const id = setInterval(() => setNowMs(Date.now()), 1000); return () => clearInterval(id); }, []);
  // Follow the app's light/dark theme
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(readTheme()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);
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
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.1, bottom: 0.16 } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, barSpacing: 8, rightOffset: 8 },
    });
    const minMove = 10 ** -decimals;
    const cs = chart.addSeries(CandlestickSeries, {
      upColor: p.bull, downColor: p.bear, borderUpColor: p.bull, borderDownColor: p.bear, wickUpColor: p.bull, wickDownColor: p.bear,
      priceFormat: { type: 'price', precision: decimals, minMove },
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } });
    chart.subscribeCrosshairMove(param => {
      const d = param.seriesData.get(cs) as any;
      setHover(d && typeof d.open === 'number' ? { time: Number(param.time), open: d.open, high: d.high, low: d.low, close: d.close } : null);
    });
    chartRef.current = chart;
    candleRef.current = cs;
    volRef.current = vol;
    const prim = new SmcDrawingPrimitive();
    cs.attachPrimitive(prim);
    drawRef.current = prim;
    fitKeyRef.current = '';
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      drawRef.current = null;
      // Removed on the next frame: a repaint already scheduled for this one would otherwise draw a disposed chart
      requestAnimationFrame(() => { try { chart.remove(); } catch { /* already gone */ } });
    };
  }, [theme, decimals]);

  // UTC seconds, each intraday candle snapped to the open of its timeframe slot, sorted, one per slot
  const bars = useMemo(() => {
    const step = TF_SEC[timeframe] || 0;
    const bySlot = new Map<number, PriceCandle>();
    for (const c of candles) {
      if (!c || ![c.open, c.high, c.low, c.close].every(v => typeof v === 'number' && Number.isFinite(v))) continue;
      let ts = Number(c.time);
      if (ts > 1e11) ts = Math.floor(ts / 1000);  // milliseconds → seconds
      if (step > 0 && step < 86400) ts -= ts % step;  // daily / weekly bars keep the provider's own session open
      bySlot.set(ts, { ...c, time: ts });
    }
    return [...bySlot.values()].sort((a, b) => a.time - b.time);
  }, [candles, timeframe]);

  const barsLenRef = useRef(0);
  const barTimesRef = useRef<number[]>([]);
  barsLenRef.current = bars.length;
  const resetView = () => {
    const n = barsLenRef.current;
    const show = VISIBLE_BARS[timeframe] ?? 120;
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n + Math.max(4, Math.round(show * 0.06)) });
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

  // Candles and volume; the view stays on the same candles when the feed slides by one
  useEffect(() => {
    const cs = candleRef.current, chart = chartRef.current;
    if (!cs || !chart) return;
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
    const key = `${symbol}-${timeframe}-${theme}`;
    if (range && (shift || grew) && fitKeyRef.current === key) {
      const extra = followLive ? Math.max(0, grew) : 0;  // at the live edge: the new candle scrolls in
      chart.timeScale().setVisibleLogicalRange({ from: range.from + shift + extra, to: range.to + shift + extra });
    }
    volRef.current?.setData(bars.map(b => ({ time: b.time as Time, value: b.volume || 0, color: b.close >= b.open ? 'rgba(22,199,132,0.22)' : 'rgba(234,57,67,0.22)' })));
    if (fitKeyRef.current !== key && bars.length) {
      fitKeyRef.current = key;
      resetView();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, symbol, timeframe, theme]);

  // Daily / weekly axis shows dates only; forex has no real volume on the free feed, so its pane is hidden
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const hasVolume = bars.some(b => (b.volume || 0) > 0);
    chart.applyOptions({ timeScale: { timeVisible: tfSec < 86400 } });
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.1, bottom: hasVolume ? 0.16 : 0.06 } });
    volRef.current?.applyOptions({ visible: hasVolume });
  }, [bars, tfSec, theme, decimals]);

  // The setup's entry / SL / TP prices on the axis (the drawing shows the lines and the areas)
  const levelKey = levels.map(l => `${l.kind}:${l.price}:${l.label}`).join('|');
  useEffect(() => {
    const cs = candleRef.current;
    if (!cs || !levels.length) return;
    const p = PAL[theme];
    const color: Record<ChartLevel['kind'], string> = { entry: '#D4AF37', sl: p.bear, tp: p.bull };
    const lines: IPriceLine[] = levels.map(l => cs.createPriceLine({ price: l.price, color: color[l.kind], lineWidth: 1, lineVisible: false, axisLabelVisible: true, title: l.label }));
    return () => { lines.forEach(x => { try { cs.removePriceLine(x); } catch { /* chart rebuilt */ } }); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [levelKey, theme, decimals, symbol]);

  // The SMC overlays of THIS timeframe's candles, and the team's analysis: placed by time on the candles shown
  const smc = useMemo(() => (showDetails ? computeSmc(bars, tfSec) : null), [bars, tfSec, showDetails]);
  const ema = useMemo(() => (showEma ? emaLine(bars, tfSec) : null), [bars, tfSec, showEma]);
  useEffect(() => {
    const keep = <T extends { detail?: boolean }>(xs: T[]) => (showDetails ? xs : xs.filter(x => !x.detail));
    const team: SmcDrawing = drawing ? { ...drawing, boxes: keep(drawing.boxes), segments: keep(drawing.segments), labels: keep(drawing.labels) }
      : { boxes: [], segments: [], labels: [], lines: [], windows: [], trade: null };
    const lines = [...(ema ? [ema] : []), ...(team.lines ?? [])];
    const merged: SmcDrawing = smc ? { ...team, pd: smc.pd, sessions: smc.sessions, boxes: [...smc.boxes, ...team.boxes], segments: [...smc.segments, ...team.segments],
      lines: [...smc.lines, ...lines] } : { ...team, lines };
    drawRef.current?.update(merged, bars.map(b => b.time), tfSec, theme);
  }, [drawing, showDetails, smc, ema, bars, tfSec, theme]);
  const hasTrade = !!drawing?.trade;
  const hasZone = !!drawing?.boxes.some(b => !b.detail);

  // A new pair / timeframe: forget the old crosshair
  useEffect(() => { chartRef.current?.clearCrosshairPosition(); setHover(null); }, [symbol, timeframe]);

  const last = bars[bars.length - 1];
  const ohlc = hover || last;
  const idx = ohlc ? bars.findIndex(b => b.time === ohlc.time) : -1;
  const prevClose = idx > 0 ? bars[idx - 1].close : null;
  const chg = ohlc && prevClose ? ((ohlc.close - prevClose) / prevClose) * 100 : null;
  const age = updatedAt ? Math.max(0, Math.round((nowMs - updatedAt) / 1000)) : null;
  const quoteAge = quote?.time ? Math.max(0, Math.round(nowMs / 1000 - quote.time)) : null;

  return (
    <div ref={frameRef} className={`flex flex-col border glass overflow-hidden ${full ? 'fixed inset-0 z-[60] rounded-none' : 'rounded-[var(--radius-card)]'}`}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-4 py-2 border-b border-line">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-white font-mono">{symbol}</span>
          <span className="px-1.5 py-0.5 rounded bg-surface-2 text-[11px] font-mono text-gold-300">{timeframe}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {extra}
          <div role="tablist" aria-label={t('Timeframe', 'Unité de temps', 'الفريم')} className="flex items-center rounded-lg bg-surface-2 border border-line p-0.5">
            {timeframes.map(tf => (
              <button key={tf} role="tab" aria-selected={tf === (tabValue ?? timeframe)} onClick={() => onTimeframeChange(tf)}
                className={`min-w-[38px] h-8 px-2 rounded-md font-mono text-xs cursor-pointer transition-colors whitespace-nowrap ${tf === (tabValue ?? timeframe) ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-100'}`}>
                {TAB_LABEL(tf)}
              </button>
            ))}
          </div>
          <button onClick={toggleEma} aria-pressed={showEma} title={t('50 EMA (a secondary confluence, never a signal by itself)', 'EMA 50 (confluence secondaire, jamais un signal seule)', 'EMA 50 (تأكيد ثانوي، عمرها ما إشارة بوحدها)')}
            className={`h-9 px-2.5 inline-flex items-center gap-1.5 rounded-lg border text-xs cursor-pointer ${showEma ? 'border-gold-500/40 bg-gold-500/10 text-gold-200' : 'border-line text-slate-400 hover:text-white hover:bg-surface-2'}`}>
            <Shapes className="w-4 h-4" /><span>EMA 50</span>
          </button>
          <button onClick={toggleDetails} aria-pressed={showDetails}
            title={t('Details: the other zones, round numbers, 4H levels, sessions, liquidity, FVGs', 'Détails : autres zones, chiffres ronds, niveaux 4H, sessions, liquidité, FVG', 'التفاصيل: المناطق الأخرى، الأرقام المدورة، مستويات 4H، السيشنات، السيولة، FVG')}
            className={`h-9 px-2.5 inline-flex items-center gap-1.5 rounded-lg border text-xs cursor-pointer ${showDetails ? 'border-gold-500/40 bg-gold-500/10 text-gold-200' : 'border-line text-slate-400 hover:text-white hover:bg-surface-2'}`}>
            <Layers className="w-4 h-4" /><span>{t('Details', 'Détails', 'التفاصيل')}</span>
          </button>
          <button onClick={resetView} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2 cursor-pointer"
            aria-label={t('Reset view', 'Recentrer', 'رجع العرض')} title={t('Reset view', 'Recentrer', 'رجع العرض')}>
            <Maximize2 className="w-4 h-4" />
          </button>
          <button onClick={toggleFull} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white hover:bg-surface-2 cursor-pointer"
            aria-label={full ? t('Exit full screen', 'Quitter le plein écran', 'خرج من الشاشة الكاملة') : t('Full screen', 'Plein écran', 'شاشة كاملة')}
            title={full ? t('Exit full screen', 'Quitter le plein écran', 'خرج من الشاشة الكاملة') : t('Full screen', 'Plein écran', 'شاشة كاملة')}>
            {full ? <Minimize2 className="w-4 h-4" /> : <Expand className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Chart */}
      <div className={`relative ${full ? 'flex-1' : compact ? 'h-[46vh] min-h-[320px] max-h-[560px]' : 'h-[62vh] min-h-[380px] max-h-[720px]'}`}>
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
          </div>
        )}
        {!bars.length && (
          <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-slate-400">{t('Loading the chart…', 'Chargement du graphique…', 'كيتحمل الشارت…')}</div>
        )}
      </div>

      {/* Legend: one small, constant key for what is on the chart */}
      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 sm:px-4 pt-2 text-[11px] text-slate-400" aria-label={t('Legend', 'Légende', 'المفتاح')}>
        {hasTrade && <>
          <li className="inline-flex items-center gap-1"><span className="w-4 h-0.5 bg-[#D4AF37]" aria-hidden="true" />{t('Entry', 'Entrée', 'الدخول')}</li>
          <li className="inline-flex items-center gap-1"><span className="w-4 h-0.5 bg-[#F87171]" aria-hidden="true" />{t('Stop', 'Stop', 'الستوب')}</li>
          <li className="inline-flex items-center gap-1"><span className="w-4 h-0.5 bg-[#4ADE80]" aria-hidden="true" />{t('Target', 'Objectif', 'الهدف')}</li>
        </>}
        {hasZone && <li className="inline-flex items-center gap-1"><span className="w-3 h-2.5 rounded-sm border border-emerald-500/70 bg-emerald-500/20" aria-hidden="true" />{t('Zone (3+ touches)', 'Zone (3+ touches)', 'المنطقة (3+ لمسات)')}</li>}
        {!!drawing && <li className="inline-flex items-center gap-1"><span className="w-4 border-t border-dotted border-[#F472B6]" aria-hidden="true" />{t('1D structure', 'Structure 1D', 'الهيكل 1D')}</li>}
        {showEma && <li className="inline-flex items-center gap-1"><span className="w-4 h-0.5 bg-[#3b82f6]" aria-hidden="true" />50 EMA</li>}
        {hasTrade && <li className="ms-auto text-slate-500">{t('Research signal · not an order', 'Signal de recherche · pas un ordre', 'إشارة بحث · ماشي أمر')}</li>}
      </ul>
      {/* Provenance */}
      <div className="px-3 sm:px-4 py-2 border-t border-line text-[11px] mt-2">
        <span className="font-mono text-slate-500 truncate">
          {age !== null && <span className={age > 15 ? 'text-rose-300' : 'text-emerald-400'}>{age > 15 ? `● ${t('Stale', 'Ancien', 'قديم')} · ${age}s` : '● Live'}</span>}
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
