import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { Candle, TechnicalIndicators, MarketAsset, AISignal, Language } from '../types';
import { 
  BarChart2, 
  TrendingUp, 
  Layers, 
  Activity, 
  ZoomIn, 
  ZoomOut, 
  Sparkles, 
  Target, 
  Crosshair, 
  Play, 
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  Maximize2,
  Minimize2,
  Columns,
  Square,
  Minus,
  Move,
  Ruler,
  Trash2,
  Clock,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  Shield,
  Sliders,
  DollarSign
} from 'lucide-react';
import { evaluateGoldSmcStrategy, M15SessionLiquidityLevels, mapM15SessionLiquidity, calculateAtr14 } from '../../server/goldSmcStrategy';

export interface GoldChartProps {
  asset: MarketAsset;
  candles: Candle[];
  indicators?: TechnicalIndicators | null;
  activeSignal?: AISignal | null;
  signals?: AISignal[];
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
  lang: Language;
  theme?: 'light' | 'dark';
  onSimulateTrade?: (direction: 'BUY' | 'SELL') => void;
}

// Interactive Drawing items placed by the trader
export interface UserDrawing {
  id: string;
  type: 'ray' | 'rect' | 'ruler' | 'position';
  p1: { x: number; y: number; price: number; time: number };
  p2?: { x: number; y: number; price: number; time: number };
  color?: string;
  label?: string;
  direction?: 'BUY' | 'SELL';
  entryPrice?: number;
  stopLossPrice?: number;
  tp1Price?: number;
  tp2Price?: number;
}

export const GoldChart: React.FC<GoldChartProps> = ({
  asset,
  candles: rawCandles,
  indicators,
  activeSignal,
  signals = [],
  timeframe,
  onTimeframeChange,
  lang,
  theme = 'dark',
  onSimulateTrade,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  // Master Canvas References
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const splitLeftCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const splitRightCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Dimensions & DPI
  const [dimensions, setDimensions] = useState({ width: 900, height: 560 });

  // Navigation: Pan & Zoom
  const [scrollOffsetBars, setScrollOffsetBars] = useState<number>(0); // 0 = right at live bar, > 0 = scrolled into history
  const [barSpacing, setBarSpacing] = useState<number>(12); // width + gap per candle (in px)
  const [verticalPriceOffset, setVerticalPriceOffset] = useState<number>(0); // vertical shift in USD
  const [priceScaleMultiplier, setPriceScaleMultiplier] = useState<number>(1.0); // vertical price zoom
  const [autoFitPriceScale, setAutoFitPriceScale] = useState<boolean>(true);

  // Mouse interaction modes
  const [activeDrawingTool, setActiveDrawingTool] = useState<'pointer' | 'ruler' | 'ray' | 'rect' | 'position'>('pointer');
  const [userDrawings, setUserDrawings] = useState<UserDrawing[]>([]);
  const [currentDrawing, setCurrentDrawing] = useState<Partial<UserDrawing> | null>(null);
  const [draggingTarget, setDraggingTarget] = useState<'chart_pan' | 'price_scale' | 'time_scale' | 'position_handle' | null>(null);
  const [dragStartPoint, setDragStartPoint] = useState<{ x: number; y: number; initialScroll: number; initialVertOffset: number; initialPriceScale: number; initialSpacing: number } | null>(null);

  // Draggable position tool state
  const [activePositionTool, setActivePositionTool] = useState<{
    direction: 'BUY' | 'SELL';
    entry: number;
    sl: number;
    tp1: number;
    tp2: number;
    activeHandle: 'entry' | 'sl' | 'tp1' | 'tp2' | null;
  } | null>(null);

  // Crosshair & Hover Telemetry
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const [hoveredCandle, setHoveredCandle] = useState<Candle | null>(null);
  const [hoveredPrice, setHoveredPrice] = useState<number>(asset.price);

  // Overlays & Toggles
  const [showAsianRange, setShowAsianRange] = useState<boolean>(true);
  const [showLondonRange, setShowLondonRange] = useState<boolean>(true);
  const [showKillzone, setShowKillzone] = useState<boolean>(true);
  const [showLiquidityRays, setShowLiquidityRays] = useState<boolean>(true);
  const [showMSS, setShowMSS] = useState<boolean>(true);
  const [showFVG, setShowFVG] = useState<boolean>(true);
  const [showDisplacementHighlights, setShowDisplacementHighlights] = useState<boolean>(true);
  const [showPositionProjection, setShowPositionProjection] = useState<boolean>(true);
  const [chartStyle, setChartStyle] = useState<'candles' | 'line' | 'hollow'>('candles');

  // Split View (M15 + M5) Mode
  const [isSplitView, setIsSplitView] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Bar-by-Bar Replay Engine (Backtesting)
  const [isReplayActive, setIsReplayActive] = useState<boolean>(false);
  const [replayBarIndex, setReplayBarIndex] = useState<number>(0);
  const [isReplayPlaying, setIsReplayPlaying] = useState<boolean>(false);
  const [replaySpeed, setReplaySpeed] = useState<1 | 2 | 5>(1);

  // Live Candle Countdown
  const [candleSecondsRemaining, setCandleSecondsRemaining] = useState<number>(180);

  // Guaranteed Extended Historical Candle Buffer (600+ bars)
  const candles = useMemo(() => {
    if (rawCandles && rawCandles.length >= 60) return rawCandles;
    // Generate high-density realistic M5/M15 buffer
    const stepSec = timeframe === '1M' ? 60 : timeframe === '5M' ? 300 : timeframe === '15M' ? 900 : timeframe === '1H' ? 3600 : 300;
    const count = 650;
    const now = Math.floor(Date.now() / 1000);
    const roundedNow = now - (now % stepSec);
    const startTimestamp = roundedNow - (count - 1) * stepSec;

    const list: Candle[] = [];
    let p = asset.price - 12.0;

    for (let i = 0; i < count; i++) {
      const t = startTimestamp + i * stepSec;
      const d = new Date(t * 1000);
      const hour = d.getUTCHours();
      const isAsian = hour >= 0 && hour < 8;
      const isLondon = hour >= 8 && hour < 14;
      const isSilverBullet = hour === 14;

      const vol = isSilverBullet ? 3.6 : isLondon ? 2.2 : isAsian ? 0.7 : 1.4;
      const wave = Math.sin(i * 0.28) * vol + Math.cos(i * 0.12) * (vol * 0.7);
      const open = p;
      let close = open + wave;
      if (i === count - 1) close = asset.price;

      const high = Math.max(open, close) + Math.abs(Math.sin(i * 0.6)) * vol * 0.8;
      const low = Math.min(open, close) - Math.abs(Math.cos(i * 0.6)) * vol * 0.8;

      list.push({
        time: t,
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(close.toFixed(2)),
        volume: Math.floor(1200 + vol * 800)
      });
      p = close;
    }
    return list;
  }, [rawCandles, asset.price, timeframe]);

  // Sliced candles during replay mode
  const displayCandles = useMemo(() => {
    if (!isReplayActive) return candles;
    const cutoff = Math.max(20, Math.min(candles.length, replayBarIndex));
    return candles.slice(0, cutoff);
  }, [candles, isReplayActive, replayBarIndex]);

  // Real-Time SMC & Silver Bullet Strategy Evaluation on current candles
  const smcEvaluation = useMemo(() => {
    return evaluateGoldSmcStrategy(displayCandles, undefined, {
      currentPrice: asset.price,
      bypassTimeWindow: true
    });
  }, [displayCandles, asset.price]);

  // Sync position projection tool from active signal or smcEvaluation
  useEffect(() => {
    const targetSig = activeSignal || signals.find(s => s.symbol === asset.symbol);
    if (targetSig && targetSig.entryPrice && targetSig.stopLoss && targetSig.target1) {
      setActivePositionTool({
        direction: (targetSig.signalType === 'SELL' || targetSig.action === 'SELL') ? 'SELL' : 'BUY',
        entry: targetSig.entryPrice,
        sl: targetSig.stopLoss,
        tp1: targetSig.target1,
        tp2: targetSig.target2 || targetSig.target1 * 1.01,
        activeHandle: null,
      });
    } else if (smcEvaluation && smcEvaluation.status === 'VALID_SETUP') {
      setActivePositionTool({
        direction: smcEvaluation.action as 'BUY' | 'SELL',
        entry: smcEvaluation.entryPrice,
        sl: smcEvaluation.stopLossPrice,
        tp1: smcEvaluation.takeProfit1Price,
        tp2: smcEvaluation.takeProfit2Price,
        activeHandle: null,
      });
    }
  }, [activeSignal, signals, asset.symbol, smcEvaluation]);

  // Real-time live countdown timer (ticks every second)
  useEffect(() => {
    const interval = setInterval(() => {
      const nowSec = Math.floor(Date.now() / 1000);
      const stepSec = timeframe === '1M' ? 60 : timeframe === '5M' ? 300 : timeframe === '15M' ? 900 : timeframe === '1H' ? 3600 : 300;
      const elapsed = nowSec % stepSec;
      setCandleSecondsRemaining(Math.max(0, stepSec - elapsed));
    }, 1000);
    return () => clearInterval(interval);
  }, [timeframe]);

  // Replay playback ticker
  useEffect(() => {
    if (!isReplayPlaying || !isReplayActive) return;
    const delay = replaySpeed === 5 ? 200 : replaySpeed === 2 ? 500 : 1000;
    const timer = setInterval(() => {
      setReplayBarIndex(prev => {
        if (prev >= candles.length) {
          setIsReplayPlaying(false);
          return candles.length;
        }
        return prev + 1;
      });
    }, delay);
    return () => clearInterval(timer);
  }, [isReplayPlaying, isReplayActive, replaySpeed, candles.length]);

  // Resize observer for responsive canvas
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 200 && height > 200) {
          setDimensions({ width: Math.floor(width), height: Math.floor(height) });
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Keyboard Shortcuts: Space (Replay), R (Reset View), Esc (Cancel Drawing)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        if (isReplayActive) {
          setIsReplayPlaying(prev => !prev);
        } else {
          // Step back 1 bar into replay
          setIsReplayActive(true);
          setReplayBarIndex(candles.length - 15);
        }
      } else if (e.code === 'KeyR') {
        e.preventDefault();
        setScrollOffsetBars(0);
        setVerticalPriceOffset(0);
        setPriceScaleMultiplier(1.0);
        setAutoFitPriceScale(true);
      } else if (e.code === 'Escape') {
        setActiveDrawingTool('pointer');
        setCurrentDrawing(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isReplayActive, candles.length]);

  // Pad margins (TradingView Pro layout)
  const padRight = 85; // Right price scale width
  const padBottom = 30; // Bottom time axis height
  const padTop = 32; // Top OHLC telemetry padding
  const padLeft = 8;

  const plotWidth = Math.max(100, dimensions.width - padRight - padLeft);
  const plotHeight = Math.max(100, dimensions.height - padTop - padBottom);

  // Price Scale Calculation (with Auto-fit + manual vertical zoom)
  const priceRange = useMemo(() => {
    if (displayCandles.length === 0) return { min: 2600, max: 2700, range: 100 };

    // Visible window of candles based on scrollOffsetBars and plotWidth / barSpacing
    const visibleCount = Math.ceil(plotWidth / barSpacing) + 2;
    const endIndex = Math.max(1, displayCandles.length - Math.floor(scrollOffsetBars));
    const startIndex = Math.max(0, endIndex - visibleCount);
    const visibleSlice = displayCandles.slice(startIndex, endIndex);

    if (visibleSlice.length === 0) return { min: asset.price - 15, max: asset.price + 15, range: 30 };

    let min = Infinity;
    let max = -Infinity;
    for (const c of visibleSlice) {
      if (c.low < min) min = c.low;
      if (c.high > max) max = c.high;
    }

    // Include position tool levels if active and visible
    if (activePositionTool && showPositionProjection) {
      min = Math.min(min, activePositionTool.sl, activePositionTool.entry, activePositionTool.tp1, activePositionTool.tp2);
      max = Math.max(max, activePositionTool.sl, activePositionTool.entry, activePositionTool.tp1, activePositionTool.tp2);
    }

    const padding = (max - min) * 0.12 || 4.0;
    let adjustedMin = min - padding + verticalPriceOffset;
    let adjustedMax = max + padding + verticalPriceOffset;

    // Apply manual price scale zoom
    if (!autoFitPriceScale && priceScaleMultiplier !== 1.0) {
      const mid = (adjustedMin + adjustedMax) / 2;
      const span = (adjustedMax - adjustedMin) / priceScaleMultiplier;
      adjustedMin = mid - span / 2;
      adjustedMax = mid + span / 2;
    }

    return {
      min: adjustedMin,
      max: adjustedMax,
      range: Math.max(1.0, adjustedMax - adjustedMin),
      startIndex,
      endIndex,
      visibleSlice
    };
  }, [displayCandles, plotWidth, barSpacing, scrollOffsetBars, verticalPriceOffset, priceScaleMultiplier, autoFitPriceScale, activePositionTool, showPositionProjection, asset.price]);

  // Coordinate Conversion Functions
  const getX = useCallback((index: number) => {
    // index in displayCandles
    const offsetFromEnd = displayCandles.length - 1 - index;
    const pxFromRight = (offsetFromEnd - scrollOffsetBars) * barSpacing;
    return padLeft + plotWidth - pxFromRight - barSpacing / 2;
  }, [displayCandles.length, scrollOffsetBars, barSpacing, padLeft, plotWidth]);

  const getY = useCallback((price: number) => {
    const pct = (price - priceRange.min) / priceRange.range;
    return padTop + plotHeight - pct * plotHeight;
  }, [priceRange.min, priceRange.range, padTop, plotHeight]);

  const getPriceAtY = useCallback((y: number) => {
    const clampedY = Math.max(padTop, Math.min(padTop + plotHeight, y));
    const pct = (padTop + plotHeight - clampedY) / plotHeight;
    return priceRange.min + pct * priceRange.range;
  }, [priceRange.min, priceRange.range, padTop, plotHeight]);

  const getIndexAtX = useCallback((x: number) => {
    const pxFromRight = padLeft + plotWidth - x - barSpacing / 2;
    const offsetFromEnd = pxFromRight / barSpacing + scrollOffsetBars;
    return Math.round(displayCandles.length - 1 - offsetFromEnd);
  }, [padLeft, plotWidth, barSpacing, scrollOffsetBars, displayCandles.length]);

  // -------------------------------------------------------------
  // PRIMARY 60FPS CANVAS RENDERING ENGINE (Retina High-DPI Scaled)
  // -------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = dimensions.width * dpr;
    canvas.height = dimensions.height * dpr;
    canvas.style.width = `${dimensions.width}px`;
    canvas.style.height = `${dimensions.height}px`;

    ctx.save();
    ctx.scale(dpr, dpr);

    // 1. Chart Background & Grid (Deep Obsidian & Subtle Zinc)
    ctx.fillStyle = isLight ? '#FFFFFF' : '#09090B';
    ctx.fillRect(0, 0, dimensions.width, dimensions.height);

    // Subtle horizontal price grid lines
    ctx.lineWidth = 1;
    ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.04)' : 'rgba(255, 255, 255, 0.04)';
    const priceStep = priceRange.range > 50 ? 10 : priceRange.range > 20 ? 5 : priceRange.range > 10 ? 2 : 1;
    const startGridPrice = Math.floor(priceRange.min / priceStep) * priceStep;

    for (let p = startGridPrice; p <= priceRange.max; p += priceStep) {
      const y = getY(p);
      if (y >= padTop && y <= padTop + plotHeight) {
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotWidth, y);
        ctx.stroke();

        // Right Y-axis static label
        ctx.fillStyle = isLight ? '#64748B' : '#71717A';
        ctx.font = '10px "JetBrains Mono", monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`$${p.toFixed(2)}`, padLeft + plotWidth + 7, y + 3.5);
      }
    }

    // 2. LAYER 1: Session Killzones (Asian, London, NY Silver Bullet)
    const { startIndex, endIndex } = priceRange;
    for (let i = Math.max(0, startIndex - 5); i < Math.min(displayCandles.length, endIndex + 5); i++) {
      const c = displayCandles[i];
      const d = new Date(c.time * 1000);
      const hour = d.getUTCHours();
      const min = d.getUTCMinutes();
      const totalMin = hour * 60 + min;

      const x = getX(i);
      const w = barSpacing;

      // Asian Session (00:00 - 08:00 GMT)
      if (showAsianRange && hour >= 0 && hour < 8) {
        ctx.fillStyle = isLight ? 'rgba(99, 102, 241, 0.04)' : 'rgba(99, 102, 241, 0.05)';
        ctx.fillRect(x - w / 2, padTop, w, plotHeight);
      }
      // London Session (08:00 - 13:55 GMT)
      if (showLondonRange && hour >= 8 && hour < 14) {
        ctx.fillStyle = isLight ? 'rgba(14, 165, 233, 0.04)' : 'rgba(14, 165, 233, 0.05)';
        ctx.fillRect(x - w / 2, padTop, w, plotHeight);
      }
      // NY Silver Bullet Window (14:00 - 15:00 GMT) - Prominent Metallic Gold
      if (showKillzone && totalMin >= 14 * 60 && totalMin <= 15 * 60) {
        ctx.fillStyle = 'rgba(245, 158, 11, 0.12)';
        ctx.fillRect(x - w / 2, padTop, w, plotHeight);

        // Border accents
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.35)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        if (totalMin === 14 * 60) {
          ctx.moveTo(x - w / 2, padTop);
          ctx.lineTo(x - w / 2, padTop + plotHeight);
        }
        if (totalMin === 15 * 60) {
          ctx.moveTo(x + w / 2, padTop);
          ctx.lineTo(x + w / 2, padTop + plotHeight);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // 3. LAYER 2: Unswept & Swept Liquidity Pools (Asian H/L, London H/L)
    if (showLiquidityRays && smcEvaluation.m15Liquidity) {
      const liq = smcEvaluation.m15Liquidity;
      const pools = [
        { name: 'LONDON HIGH (BSL)', price: liq.londonHigh, swept: liq.londonSwept === 'BSL_SWEPT', color: '#0EA5E9' },
        { name: 'LONDON LOW (SSL)', price: liq.londonLow, swept: liq.londonSwept === 'SSL_SWEPT', color: '#0EA5E9' },
        { name: 'ASIAN HIGH (BSL)', price: liq.asianHigh, swept: liq.asianSwept === 'BSL_SWEPT', color: '#818CF8' },
        { name: 'ASIAN LOW (SSL)', price: liq.asianLow, swept: liq.asianSwept === 'SSL_SWEPT', color: '#818CF8' },
      ];

      for (const pool of pools) {
        if (!pool.price || pool.price < 2000) continue;
        const y = getY(pool.price);
        if (y < padTop - 10 || y > padTop + plotHeight + 10) continue;

        ctx.lineWidth = pool.swept ? 1.0 : 1.5;
        ctx.strokeStyle = pool.swept ? (isLight ? '#94A3B8' : '#52525B') : pool.color;
        ctx.setLineDash(pool.swept ? [2, 4] : [6, 4]);

        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotWidth, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Label pill on left
        ctx.fillStyle = pool.swept ? (isLight ? '#94A3B8' : '#71717A') : pool.color;
        ctx.font = 'bold 9px "JetBrains Mono", monospace';
        ctx.textAlign = 'left';
        const dist = Math.abs(asset.price - pool.price).toFixed(2);
        const pips = Math.round(Math.abs(asset.price - pool.price) * 10);
        const text = pool.swept 
          ? `✓ SWEPT @ $${pool.price.toFixed(2)} (${pool.name})`
          : `$$$ ${pool.name} · $${pool.price.toFixed(2)} (${pips} pips · $${dist})`;
        ctx.fillText(text, padLeft + 10, y - 4);
      }
    }

    // 4. LAYER 3: M5 Fair Value Gaps (FVG) with 50% Consequent Encroachment (CE)
    if (showFVG && smcEvaluation.fvgZone) {
      const fvg = smcEvaluation.fvgZone;
      const yHigh = getY(fvg.gapHigh);
      const yLow = getY(fvg.gapLow);
      const yCe = getY(fvg.midpointCE);
      const isBull = smcEvaluation.action === 'BUY';

      // Shaded FVG Box extending forward
      const fvgStartX = getX(Math.max(0, displayCandles.length - 8));
      const fvgWidth = (padLeft + plotWidth) - fvgStartX;

      ctx.fillStyle = isBull ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
      ctx.fillRect(fvgStartX, yHigh, fvgWidth, yLow - yHigh);

      // Top and bottom borders
      ctx.strokeStyle = isBull ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(fvgStartX, yHigh, fvgWidth, yLow - yHigh);

      // 50% Consequent Encroachment (CE) midpoint dashed line
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(fvgStartX, yCe);
      ctx.lineTo(fvgStartX + fvgWidth, yCe);
      ctx.stroke();
      ctx.setLineDash([]);

      // FVG & CE Label
      ctx.fillStyle = '#F59E0B';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`50% CE: $${fvg.midpointCE.toFixed(2)} (M5 FVG Limit)`, padLeft + plotWidth - 10, yCe - 4);
    }

    // 5. LAYER 4: Candlesticks & Displacement Highlights
    const atr14 = calculateAtr14(displayCandles, 14);

    for (let i = startIndex; i < Math.min(displayCandles.length, endIndex); i++) {
      const c = displayCandles[i];
      const x = getX(i);
      const yOpen = getY(c.open);
      const yClose = getY(c.close);
      const yHigh = getY(c.high);
      const yLow = getY(c.low);

      const isBullish = c.close >= c.open;
      const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
      const topY = Math.min(yOpen, yClose);
      const candleW = Math.max(2, barSpacing * 0.75);

      // Check Displacement Condition: Body >= 65% & Range >= 1.2x ATR
      const totalRange = c.high - c.low;
      const bodyRange = Math.abs(c.close - c.open);
      const isDisplacement = showDisplacementHighlights && totalRange > 0 && (bodyRange / totalRange >= 0.65) && (totalRange >= 1.2 * atr14);

      // Wicks
      ctx.strokeStyle = isDisplacement 
        ? '#F59E0B'
        : isBullish ? '#10B981' : '#EF4444';
      ctx.lineWidth = isDisplacement ? 1.5 : 1.0;
      ctx.beginPath();
      ctx.moveTo(x, yHigh);
      ctx.lineTo(x, yLow);
      ctx.stroke();

      // Body
      if (chartStyle === 'hollow' && isBullish) {
        ctx.strokeStyle = '#10B981';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x - candleW / 2, topY, candleW, bodyHeight);
      } else {
        ctx.fillStyle = isDisplacement 
          ? (isBullish ? '#10B981' : '#EF4444')
          : (isBullish ? '#10B981' : '#EF4444');
        ctx.fillRect(x - candleW / 2, topY, candleW, bodyHeight);

        // Highlight displacement border in Metallic Gold
        if (isDisplacement) {
          ctx.strokeStyle = '#F59E0B';
          ctx.lineWidth = 2;
          ctx.strokeRect(x - candleW / 2, topY, candleW, bodyHeight);
        }
      }
    }

    // 6. LAYER 5: Market Structure Shift (MSS) Level
    if (showMSS && smcEvaluation.mssPrice > 0) {
      const mssY = getY(smcEvaluation.mssPrice);
      ctx.strokeStyle = smcEvaluation.action === 'BUY' ? '#10B981' : '#EF4444';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, mssY);
      ctx.lineTo(padLeft + plotWidth, mssY);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = smcEvaluation.action === 'BUY' ? '#10B981' : '#EF4444';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`MSS CONFIRMED (BODY CLOSE @ $${smcEvaluation.mssPrice.toFixed(2)})`, padLeft + 15, mssY - 4);
    }

    // 7. LAYER 6: TradingView Long/Short Position Tool Projection Box
    if (showPositionProjection && activePositionTool) {
      const tool = activePositionTool;
      const isLong = tool.direction === 'BUY';
      const entryY = getY(tool.entry);
      const slY = getY(tool.sl);
      const tp1Y = getY(tool.tp1);
      const tp2Y = getY(tool.tp2);

      const boxStartX = getX(Math.max(0, displayCandles.length - 12));
      const boxWidth = padLeft + plotWidth - boxStartX;

      // Risk (Stop Loss) Box - Crimson
      ctx.fillStyle = 'rgba(239, 68, 68, 0.2)';
      const slBoxY = Math.min(entryY, slY);
      const slBoxH = Math.abs(entryY - slY);
      ctx.fillRect(boxStartX, slBoxY, boxWidth, slBoxH);

      ctx.strokeStyle = '#EF4444';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(boxStartX, slBoxY, boxWidth, slBoxH);

      // Reward (Take Profit) Box - Emerald Green
      ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
      const tpBoxY = Math.min(entryY, tp1Y);
      const tpBoxH = Math.abs(entryY - tp1Y);
      ctx.fillRect(boxStartX, tpBoxY, boxWidth, tpBoxH);

      ctx.strokeStyle = '#10B981';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(boxStartX, tpBoxY, boxWidth, tpBoxH);

      // TP2 (Opposing Pool) Line
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 2]);
      ctx.beginPath();
      ctx.moveTo(boxStartX, tp2Y);
      ctx.lineTo(boxStartX + boxWidth, tp2Y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Position Box Labels
      const slDist = Math.abs(tool.entry - tool.sl);
      const tp1Dist = Math.abs(tool.tp1 - tool.entry);
      const tp2Dist = Math.abs(tool.tp2 - tool.entry);
      const rr1 = (tp1Dist / (slDist || 1)).toFixed(2);
      const rr2 = (tp2Dist / (slDist || 1)).toFixed(2);

      ctx.font = 'bold 10px "JetBrains Mono", monospace';

      // SL Text
      ctx.fillStyle = '#EF4444';
      ctx.textAlign = 'left';
      ctx.fillText(`STOP LOSS: $${tool.sl.toFixed(2)} (-$${slDist.toFixed(2)} / ${Math.round(slDist * 10)} pips · 1.0R)`, boxStartX + 8, slY + (isLong ? 14 : -6));

      // Entry Text
      ctx.fillStyle = '#FFFFFF';
      ctx.fillText(`ENTRY: $${tool.entry.toFixed(2)} (M5 FVG Proximal Edge)`, boxStartX + 8, entryY - 4);

      // TP1 Text
      ctx.fillStyle = '#10B981';
      ctx.fillText(`TARGET 1 (2R BE): $${tool.tp1.toFixed(2)} (+1:${rr1} R:R)`, boxStartX + 8, tp1Y + (isLong ? -6 : 14));

      // TP2 Text
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`TARGET 2 (DOL): $${tool.tp2.toFixed(2)} (+1:${rr2} Opposing Pool)`, boxStartX + 8, tp2Y + (isLong ? -6 : 14));
    }

    // 8. LAYER 7: User Manual Drawings (Ruler, Rays, Rectangles)
    for (const d of userDrawings) {
      if (d.type === 'ray') {
        const y = getY(d.p1.price);
        ctx.strokeStyle = d.color || '#F59E0B';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotWidth, y);
        ctx.stroke();
      } else if (d.type === 'rect' && d.p2) {
        const y1 = getY(d.p1.price);
        const y2 = getY(d.p2.price);
        const x1 = Math.min(d.p1.x, d.p2.x);
        const x2 = Math.max(d.p1.x, d.p2.x);
        ctx.fillStyle = d.color || 'rgba(14, 165, 233, 0.15)';
        ctx.fillRect(x1, Math.min(y1, y2), x2 - x1, Math.abs(y2 - y1));
        ctx.strokeStyle = d.color || '#0EA5E9';
        ctx.strokeRect(x1, Math.min(y1, y2), x2 - x1, Math.abs(y2 - y1));
      } else if (d.type === 'ruler' && d.p2) {
        const x1 = d.p1.x;
        const y1 = d.p1.y;
        const x2 = d.p2.x;
        const y2 = d.p2.y;
        const pDiff = Math.abs(d.p2.price - d.p1.price);
        const pips = Math.round(pDiff * 10);

        ctx.strokeStyle = '#38BDF8';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        ctx.fillStyle = '#0284C7';
        ctx.fillRect((x1 + x2) / 2 - 40, (y1 + y2) / 2 - 12, 80, 24);
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(`$${pDiff.toFixed(2)} (${pips} p)`, (x1 + x2) / 2, (y1 + y2) / 2 + 3);
      }
    }

    // 9. LAYER 8: Real-Time Current Price Horizontal Line & Right Badge
    const liveY = getY(asset.price);
    if (liveY >= padTop && liveY <= padTop + plotHeight) {
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.moveTo(padLeft, liveY);
      ctx.lineTo(padLeft + plotWidth, liveY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Current Price Right Y-Axis Badge
      ctx.fillStyle = '#F59E0B';
      ctx.fillRect(padLeft + plotWidth, liveY - 11, padRight - 5, 22);
      ctx.fillStyle = '#000000';
      ctx.font = 'bold 11px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`$${asset.price.toFixed(2)}`, padLeft + plotWidth + 6, liveY + 3.5);

      // Real-Time Candle Countdown directly below price badge
      const countdownMins = Math.floor(candleSecondsRemaining / 60);
      const countdownSecs = candleSecondsRemaining % 60;
      const countdownStr = `${countdownMins.toString().padStart(2, '0')}:${countdownSecs.toString().padStart(2, '0')}`;

      ctx.fillStyle = '#18181B';
      ctx.fillRect(padLeft + plotWidth, liveY + 12, padRight - 5, 16);
      ctx.fillStyle = '#A1A1AA';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.fillText(`⏱ ${countdownStr}`, padLeft + plotWidth + 6, liveY + 23);
    }

    // 10. LAYER 9: Magnetic Crosshair (if active)
    if (cursorPos) {
      const cx = Math.max(padLeft, Math.min(padLeft + plotWidth, cursorPos.x));
      const cy = Math.max(padTop, Math.min(padTop + plotHeight, cursorPos.y));

      ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.4)' : 'rgba(255, 255, 255, 0.45)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(cx, padTop);
      ctx.lineTo(cx, padTop + plotHeight);
      ctx.stroke();

      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(padLeft, cy);
      ctx.lineTo(padLeft + plotWidth, cy);
      ctx.stroke();
      ctx.setLineDash([]);

      // Right Y-axis Crosshair Badge
      ctx.fillStyle = isLight ? '#0F172A' : '#27272A';
      ctx.fillRect(padLeft + plotWidth, cy - 10, padRight - 5, 20);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`$${hoveredPrice.toFixed(2)}`, padLeft + plotWidth + 6, cy + 3.5);

      // Bottom X-axis Timestamp Badge
      if (hoveredCandle) {
        const d = new Date(hoveredCandle.time * 1000);
        const gmtStr = d.toLocaleTimeString('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' });
        const estStr = d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit' });
        const timeBadgeText = `${gmtStr} GMT · ${estStr} EST`;

        const badgeW = 140;
        ctx.fillStyle = isLight ? '#0F172A' : '#27272A';
        ctx.fillRect(cx - badgeW / 2, padTop + plotHeight + 3, badgeW, 20);
        ctx.fillStyle = '#F59E0B';
        ctx.font = 'bold 9.5px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(timeBadgeText, cx, padTop + plotHeight + 16);
      }
    }

    ctx.restore();
  }, [
    dimensions,
    displayCandles,
    priceRange,
    barSpacing,
    scrollOffsetBars,
    verticalPriceOffset,
    showAsianRange,
    showLondonRange,
    showKillzone,
    showLiquidityRays,
    showMSS,
    showFVG,
    showDisplacementHighlights,
    showPositionProjection,
    activePositionTool,
    userDrawings,
    cursorPos,
    hoveredPrice,
    hoveredCandle,
    candleSecondsRemaining,
    chartStyle,
    smcEvaluation,
    asset.price,
    isLight,
    padLeft,
    padRight,
    padTop,
    plotWidth,
    plotHeight,
    getX,
    getY
  ]);

  // -------------------------------------------------------------
  // MOUSE & TOUCH EVENT HANDLERS (TradingView Interaction Standard)
  // -------------------------------------------------------------

  // Mouse Move: Crosshair + Panning Drag + Position Tool Drag
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setCursorPos({ x, y });

    const price = getPriceAtY(y);
    setHoveredPrice(price);

    const idx = getIndexAtX(x);
    if (idx >= 0 && idx < displayCandles.length) {
      setHoveredCandle(displayCandles[idx]);
    } else {
      setHoveredCandle(displayCandles[displayCandles.length - 1]);
    }

    // 1. Chart Panning Drag
    if (draggingTarget === 'chart_pan' && dragStartPoint) {
      const deltaX = x - dragStartPoint.x;
      const deltaBars = deltaX / barSpacing;
      setScrollOffsetBars(Math.max(0, dragStartPoint.initialScroll - deltaBars));

      if (!autoFitPriceScale) {
        const deltaY = y - dragStartPoint.y;
        const pricePerPx = priceRange.range / plotHeight;
        setVerticalPriceOffset(dragStartPoint.initialVertOffset + deltaY * pricePerPx);
      }
    }

    // 2. Right Y-Axis Price Compression / Expansion Drag
    if (draggingTarget === 'price_scale' && dragStartPoint) {
      const deltaY = y - dragStartPoint.y;
      const factor = 1 - deltaY / 200;
      setPriceScaleMultiplier(Math.max(0.2, Math.min(5.0, dragStartPoint.initialPriceScale * factor)));
      setAutoFitPriceScale(false);
    }

    // 3. Bottom X-Axis Time Compression / Expansion Drag
    if (draggingTarget === 'time_scale' && dragStartPoint) {
      const deltaX = x - dragStartPoint.x;
      const newSpacing = Math.max(3, Math.min(60, dragStartPoint.initialSpacing + deltaX / 5));
      setBarSpacing(newSpacing);
    }

    // 4. Drawing creation in progress (Ruler / Rectangle)
    if (currentDrawing && (activeDrawingTool === 'rect' || activeDrawingTool === 'ruler')) {
      setCurrentDrawing(prev => prev ? {
        ...prev,
        p2: { x, y, price, time: hoveredCandle?.time || Date.now() / 1000 }
      } : null);
    }
  };

  // Mouse Down: Start Pan, Price Drag, or Drawing Tool Placement
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Check if clicked on right Price Scale axis
    if (x >= padLeft + plotWidth) {
      setDraggingTarget('price_scale');
      setDragStartPoint({
        x,
        y,
        initialScroll: scrollOffsetBars,
        initialVertOffset: verticalPriceOffset,
        initialPriceScale: priceScaleMultiplier,
        initialSpacing: barSpacing
      });
      return;
    }

    // Check if clicked on bottom Time Axis
    if (y >= padTop + plotHeight) {
      setDraggingTarget('time_scale');
      setDragStartPoint({
        x,
        y,
        initialScroll: scrollOffsetBars,
        initialVertOffset: verticalPriceOffset,
        initialPriceScale: priceScaleMultiplier,
        initialSpacing: barSpacing
      });
      return;
    }

    // Active Drawing Tool Logic
    if (activeDrawingTool === 'ray') {
      const newDrawing: UserDrawing = {
        id: `ray-${Date.now()}`,
        type: 'ray',
        p1: { x, y, price: hoveredPrice, time: hoveredCandle?.time || Date.now() / 1000 },
        color: '#F59E0B'
      };
      setUserDrawings(prev => [...prev, newDrawing]);
      setActiveDrawingTool('pointer');
      return;
    }

    if (activeDrawingTool === 'rect' || activeDrawingTool === 'ruler') {
      if (!currentDrawing) {
        // First point
        setCurrentDrawing({
          id: `${activeDrawingTool}-${Date.now()}`,
          type: activeDrawingTool,
          p1: { x, y, price: hoveredPrice, time: hoveredCandle?.time || Date.now() / 1000 }
        });
      } else {
        // Complete drawing
        setUserDrawings(prev => [...prev, {
          id: currentDrawing.id || `draw-${Date.now()}`,
          type: currentDrawing.type || activeDrawingTool,
          p1: currentDrawing.p1!,
          p2: { x, y, price: hoveredPrice, time: hoveredCandle?.time || Date.now() / 1000 }
        } as UserDrawing]);
        setCurrentDrawing(null);
        setActiveDrawingTool('pointer');
      }
      return;
    }

    // Default: Start smooth canvas pan
    setDraggingTarget('chart_pan');
    setDragStartPoint({
      x,
      y,
      initialScroll: scrollOffsetBars,
      initialVertOffset: verticalPriceOffset,
      initialPriceScale: priceScaleMultiplier,
      initialSpacing: barSpacing
    });
  };

  const handleMouseUp = () => {
    setDraggingTarget(null);
    setDragStartPoint(null);
  };

  // Cursor-Centered Wheel Zoom
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newSpacing = Math.max(3, Math.min(65, barSpacing * zoomFactor));
    setBarSpacing(newSpacing);
  };

  // Double-Click Right Price Scale: Reset Auto-fit
  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;

    if (x >= padLeft + plotWidth) {
      // Double click on right scale resets vertical scale and auto-fits
      setVerticalPriceOffset(0);
      setPriceScaleMultiplier(1.0);
      setAutoFitPriceScale(true);
    }
  };

  return (
    <div 
      ref={containerRef}
      className={`relative w-full rounded-2xl border flex flex-col overflow-hidden select-none transition-colors ${
        isFullscreen ? 'fixed inset-0 z-50 p-2 sm:p-4 bg-canvas h-screen' : 'h-[440px] sm:h-[540px] lg:h-[640px]'
      } ${
        isLight ? 'bg-white border-zinc-200 shadow-sm' : 'bg-canvas border-zinc-800 shadow-2xl'
      }`}
    >
      {/* 1. TOP INSTITUTIONAL TELEMETRY & TOOLBAR */}
      <div className={`px-4 py-2.5 border-b flex flex-wrap items-center justify-between gap-3 text-xs ${
        isLight ? 'bg-zinc-50 border-zinc-200' : 'bg-surface border-zinc-800/80'
      }`}>
        {/* Left: Asset Ticker, Live Price & OHLC Telemetry Bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-black text-sm tracking-tight text-[#F59E0B] font-mono">
              XAU/USD
            </span>
            <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-300 font-mono">
              {timeframe}
            </span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              ● SPOT GOLD OTC
            </span>
          </div>

          {/* OHLC Telemetry HUD */}
          {hoveredCandle && (
            <div className="hidden lg:flex items-center gap-2 font-mono text-xs text-zinc-400 border-l border-zinc-800 pl-3">
              <span>O: <b className="text-zinc-200">{hoveredCandle.open.toFixed(2)}</b></span>
              <span>H: <b className="text-emerald-400">{hoveredCandle.high.toFixed(2)}</b></span>
              <span>L: <b className="text-rose-400">{hoveredCandle.low.toFixed(2)}</b></span>
              <span>C: <b className="text-zinc-200">{hoveredCandle.close.toFixed(2)}</b></span>
              <span className="text-zinc-500">·</span>
              <span>Range: <b className="text-zinc-200">${(hoveredCandle.high - hoveredCandle.low).toFixed(2)}</b></span>
              <span>Body: <b className="text-zinc-200">{Math.round((Math.abs(hoveredCandle.close - hoveredCandle.open) / (hoveredCandle.high - hoveredCandle.low || 1)) * 100)}%</b></span>
              <span>ATR(14): <b className="text-amber-400">${calculateAtr14(candles, 14).toFixed(2)}</b></span>
              {Math.abs(hoveredCandle.close - hoveredCandle.open) / (hoveredCandle.high - hoveredCandle.low || 1) >= 0.65 && (
                <span className="text-xs px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-400 font-bold border border-amber-500/30">
                  DISPLACEMENT
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right: Timeframe Switcher, Split View, Replay & Actions */}
        <div className="flex items-center gap-2">
          {/* Timeframe Selector (M5 Execution, M15 Liquidity Prep, H1 Macro) */}
          <div className="flex items-center p-0.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono font-bold">
            {['M5', 'M15', 'H1'].map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                className={`px-2.5 py-1 rounded-md transition cursor-pointer ${
                  timeframe === tf
                    ? 'bg-[#F59E0B] text-black font-extrabold shadow-sm'
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Split View Toggle */}
          <button
            onClick={() => setIsSplitView(prev => !prev)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-bold transition cursor-pointer ${
              isSplitView 
                ? 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/40'
                : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:text-white'
            }`}
            title="Dual-Timeframe Split Screen (M15 Liquidity Prep + M5 Silver Bullet Execution)"
          >
            <Columns className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Split View (M15+M5)</span>
          </button>

          {/* Simulate Silver Bullet Setup Trigger */}
          {onSimulateTrade && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => onSimulateTrade('BUY')}
                className="px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 text-xs font-bold transition cursor-pointer"
                title="Simulate Bullish Silver Bullet Setup (SSL Sweep -> MSS -> FVG)"
              >
                Simulate BUY
              </button>
              <button
                onClick={() => onSimulateTrade('SELL')}
                className="px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 text-xs font-bold transition cursor-pointer"
                title="Simulate Bearish Silver Bullet Setup (BSL Sweep -> MSS -> FVG)"
              >
                Simulate SELL
              </button>
            </div>
          )}

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(prev => !prev)}
            className="p-1.5 rounded-lg bg-zinc-900 text-zinc-400 border border-zinc-800 hover:text-white transition cursor-pointer"
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. MAIN WORKSPACE: Left Drawing Toolbar + Canvas Area */}
      <div className="relative flex-1 flex overflow-hidden">
        {/* Left TradingView-Style Interactive Drawing Toolbar */}
        <div className="w-10 border-r border-zinc-800/80 bg-canvas flex flex-col items-center py-3 gap-2.5 z-20 shrink-0">
          <button
            onClick={() => setActiveDrawingTool('pointer')}
            className={`w-7 h-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
              activeDrawingTool === 'pointer' ? 'bg-[#F59E0B] text-black font-bold shadow-sm' : 'text-zinc-400 hover:text-white hover:bg-zinc-800/60'
            }`}
            title="Crosshair / Navigation Pointer"
          >
            <Crosshair className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveDrawingTool('ruler')}
            className={`w-7 h-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
              activeDrawingTool === 'ruler' ? 'bg-[#F59E0B] text-black font-bold shadow-sm' : 'text-zinc-400 hover:text-white hover:bg-zinc-800/60'
            }`}
            title="Ruler / Pip & Price Measurement Tool (Click & Drag)"
          >
            <Ruler className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveDrawingTool('ray')}
            className={`w-7 h-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
              activeDrawingTool === 'ray' ? 'bg-[#F59E0B] text-black font-bold shadow-sm' : 'text-zinc-400 hover:text-white hover:bg-zinc-800/60'
            }`}
            title="Horizontal Liquidity Ray"
          >
            <Minus className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveDrawingTool('rect')}
            className={`w-7 h-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
              activeDrawingTool === 'rect' ? 'bg-[#F59E0B] text-black font-bold shadow-sm' : 'text-zinc-400 hover:text-white hover:bg-zinc-800/60'
            }`}
            title="Rectangle / FVG & Order Block Zone"
          >
            <Square className="w-4 h-4" />
          </button>

          <button
            onClick={() => {
              setShowPositionProjection(prev => !prev);
            }}
            className={`w-7 h-7 rounded-lg flex items-center justify-center transition cursor-pointer ${
              showPositionProjection ? 'bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/40' : 'text-zinc-400 hover:text-white hover:bg-zinc-800/60'
            }`}
            title="TradingView Risk-Reward Projection Tool (Long/Short)"
          >
            <Target className="w-4 h-4" />
          </button>

          <div className="w-5 h-[1px] bg-zinc-800 my-1" />

          <button
            onClick={() => setUserDrawings([])}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-500 hover:text-rose-400 hover:bg-rose-950/20 transition cursor-pointer"
            title="Clear All Custom Drawings"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Center Canvas Area */}
        <div className="relative flex-1 h-full overflow-hidden">
          <canvas
            ref={canvasRef}
            onMouseMove={handleMouseMove}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => {
              setCursorPos(null);
              setDraggingTarget(null);
            }}
            onWheel={handleWheel}
            onDoubleClick={handleDoubleClick}
            className="w-full h-full block cursor-crosshair"
          />

          {/* Floating ">> Jump to Real-Time" Pill Button (when scrolled into history) */}
          {scrollOffsetBars > 8 && (
            <button
              onClick={() => {
                setScrollOffsetBars(0);
                setVerticalPriceOffset(0);
                setPriceScaleMultiplier(1.0);
                setAutoFitPriceScale(true);
              }}
              className="absolute bottom-10 right-24 px-3.5 py-1.5 rounded-full bg-[#F59E0B] text-black font-black text-xs shadow-xl flex items-center gap-1.5 hover:scale-105 active:scale-95 transition-all cursor-pointer z-30 animate-pulse"
            >
              <span>Jump to Real-Time</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Top-Right Strategy Layer Controls (SMC Overlays) */}
          <div className="absolute top-2 right-16 sm:right-24 flex items-center gap-1 p-1 rounded-xl bg-black/80 backdrop-blur-md border border-zinc-800/80 z-20 text-xs font-mono max-w-[calc(100%-80px)] overflow-x-auto no-scrollbar">
            <button
              onClick={() => setShowKillzone(prev => !prev)}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer ${
                showKillzone ? 'bg-[#F59E0B]/20 text-[#F59E0B]' : 'text-zinc-500'
              }`}
              title="Toggle NY Silver Bullet 14:00-15:00 GMT Window"
            >
              KZ
            </button>
            <button
              onClick={() => setShowAsianRange(prev => !prev)}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer ${
                showAsianRange ? 'bg-[#818CF8]/20 text-[#818CF8]' : 'text-zinc-500'
              }`}
              title="Toggle Asian Session Range (00:00-08:00 GMT)"
            >
              ASIAN
            </button>
            <button
              onClick={() => setShowLondonRange(prev => !prev)}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer ${
                showLondonRange ? 'bg-[#0EA5E9]/20 text-[#0EA5E9]' : 'text-zinc-500'
              }`}
              title="Toggle London Session Range (08:00-13:55 GMT)"
            >
              LONDON
            </button>
            <button
              onClick={() => setShowMSS(prev => !prev)}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer ${
                showMSS ? 'bg-emerald-500/20 text-emerald-400' : 'text-zinc-500'
              }`}
              title="Toggle Market Structure Shift (MSS)"
            >
              MSS
            </button>
            <button
              onClick={() => setShowFVG(prev => !prev)}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer ${
                showFVG ? 'bg-amber-500/20 text-amber-400' : 'text-zinc-500'
              }`}
              title="Toggle 50% Consequent Encroachment (FVG)"
            >
              FVG
            </button>
          </div>
        </div>
      </div>

      {/* 3. HISTORICAL BAR-BY-BAR REPLAY CONTROL BAR */}
      <div className={`px-4 py-2 border-t flex flex-wrap items-center justify-between gap-3 text-xs ${
        isLight ? 'bg-zinc-100 border-zinc-200' : 'bg-canvas border-zinc-800'
      }`}>
        <div className="flex items-center gap-2">
          <span className="font-extrabold text-xs uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5" />
            <span>{isAr ? 'محاكي وسجل شمعة بشمعة (Bar-by-Bar Replay):' : 'Bar-by-Bar Replay Engine:'}</span>
          </span>

          <div className="flex items-center gap-1 font-mono">
            <button
              onClick={() => {
                setIsReplayActive(true);
                setReplayBarIndex(Math.max(20, candles.length - 25));
                setIsReplayPlaying(false);
              }}
              className="p-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition cursor-pointer"
              title="Jump to 13:50 GMT (Pre-Silver Bullet)"
            >
              <SkipBack className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => {
                setIsReplayActive(true);
                setIsReplayPlaying(prev => !prev);
              }}
              className={`px-2.5 py-1 rounded font-bold flex items-center gap-1 transition cursor-pointer ${
                isReplayPlaying ? 'bg-rose-500 text-white' : 'bg-emerald-600 text-white'
              }`}
            >
              {isReplayPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              <span>{isReplayPlaying ? 'Pause' : 'Play'}</span>
            </button>

            <button
              onClick={() => {
                setIsReplayActive(true);
                setReplayBarIndex(prev => Math.min(candles.length, prev + 1));
              }}
              className="p-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition cursor-pointer"
              title="Step +1 M5 Bar Forward"
            >
              <SkipForward className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => {
                setIsReplayActive(false);
                setIsReplayPlaying(false);
                setReplayBarIndex(candles.length);
              }}
              className="p-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition cursor-pointer"
              title="Exit Replay / Return to Live Feed"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            {/* Speed Presets */}
            <div className="flex items-center gap-0.5 ml-2 border-l border-zinc-700 pl-2">
              {([1, 2, 5] as const).map(spd => (
                <button
                  key={spd}
                  onClick={() => setReplaySpeed(spd)}
                  className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                    replaySpeed === spd ? 'bg-[#F59E0B] text-black' : 'text-zinc-400 hover:text-white'
                  }`}
                >
                  {spd}x
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Live Silver Bullet Status Feedback */}
        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="text-zinc-400">
            Current Stage: <b className="text-white">{smcEvaluation.stepStates?.step2_timeWindowActive === 'ACTIVE' ? 'Inside NY Window (14-15 GMT)' : 'Monitoring Session Liquidity'}</b>
          </span>
          <span className="text-zinc-500">|</span>
          <span className="text-zinc-400">
            Confluence: <b className="text-amber-400">{smcEvaluation.confluenceScore}%</b>
          </span>
          {smcEvaluation.status === 'VALID_SETUP' && (
            <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40">
              A+ SETUP VERIFIED
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
