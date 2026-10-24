import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
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
  createSeriesMarkers,
} from 'lightweight-charts';
import { 
  Maximize2, 
  Minimize2, 
  ZoomIn, 
  ZoomOut,
  RotateCcw,
  RefreshCw, 
  BarChart2, 
  Eye, 
  TrendingUp, 
  Droplet, 
  Scale, 
  SlidersHorizontal,
  BarChart,
  Activity,
  Sun,
  Moon,
  Coins,
  Crosshair
} from 'lucide-react';

export interface ExunuCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface ExunuSMCLevels {
  entryPrice?: number;
  stopLoss?: number;
  target1?: number;
  target2?: number;
  action?: 'BUY' | 'SELL' | 'WAIT';
  orderBlock?: {
    low: number;
    high: number;
    type?: string;
  };
  bosLevel?: number;
  chochLevel?: number;
  fvg?: {
    low: number;
    high: number;
    consequentEncroachment?: number;
    type?: string;
  };
  sweepType?: string;
  bslTarget?: number;
  sslTarget?: number;
  slPips?: number;
  tp1Pips?: number;
  tp2Pips?: number;
  riskReward?: string;
  confidence?: number;
  setupGrade?: string;
  strategy?: string;
}

interface ExunuChartProps {
  symbol: 'XAU/USD' | 'EUR/USD';
  currentPrice: number;
  candles: ExunuCandle[];
  smcLevels?: ExunuSMCLevels;
  activeTimeframe: string;
  onTimeframeChange: (tf: string) => void;
  isLoading?: boolean;
  onRefresh?: () => void;
}

// SMC Detected Data Types
interface DetectedFVG {
  id: string;
  type: 'BULLISH' | 'BEARISH';
  startTime: number;
  low: number;
  high: number;
  consequentEncroachment: number;
  label: string;
}

interface DetectedStructureLine {
  id: string;
  type: 'BOS' | 'CHOCH';
  direction: 'BULLISH' | 'BEARISH';
  startTime: number;
  price: number;
  label: string;
}

interface DetectedTrendline {
  startTime: number;
  endTime: number;
  startPrice: number;
  endPrice: number;
  type: 'BEARISH' | 'BULLISH';
  label: string;
  sublabel: string;
}

interface CalculatedSMCOverlays {
  fvgs: DetectedFVG[];
  structureLines: DetectedStructureLine[];
  bsl: { price: number; time: number } | null;
  ssl: { price: number; time: number } | null;
  inducement: { price: number; time: number } | null;
  trendline: DetectedTrendline | null;
}

export const ExunuChart: React.FC<ExunuChartProps> = ({
  symbol,
  currentPrice,
  candles,
  smcLevels,
  activeTimeframe,
  onTimeframeChange,
  isLoading,
  onRefresh,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const priceLinesRef = useRef<any[]>([]);
  const markersRef = useRef<any>(null);

  const [hoveredCandle, setHoveredCandle] = useState<ExunuCandle | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerWrapperRef = useRef<HTMLDivElement>(null);

  // Default to the terminal's dark theme so the chart matches the app shell
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  const [chartType, setChartType] = useState<'candles' | 'line'>('candles');
  const [showVolume, setShowVolume] = useState<boolean>(true);

  // Layer toggles
  const [showAllDrawings, setShowAllDrawings] = useState<boolean>(true);
  const [showFVG, setShowFVG] = useState<boolean>(true);
  const [showStructure, setShowStructure] = useState<boolean>(true);
  const [showLiquidity, setShowLiquidity] = useState<boolean>(true);
  const [showTrendlines, setShowTrendlines] = useState<boolean>(true);
  const [showRiskTool, setShowRiskTool] = useState<boolean>(true);

  const isGold = symbol === 'XAU/USD';
  const decimals = isGold ? 2 : 4;
  const pipUnit = isGold ? 'pts' : 'pips';
  const timeframes = ['1M', '5M', '15M', '1H', '4H', '1D'];

  // -------------------------------------------------------------------------
  // AUTOMATIC SMC CALCULATION LOGIC (Directly parses OHLCV candles)
  // -------------------------------------------------------------------------
  const detectedSMC = useMemo<CalculatedSMCOverlays>(() => {
    if (!candles || candles.length < 6) {
      return {
        fvgs: [],
        structureLines: [],
        bsl: null,
        ssl: null,
        inducement: null,
        trendline: null,
      };
    }

    const fvgs: DetectedFVG[] = [];
    const structureLines: DetectedStructureLine[] = [];
    const swingHighs: { price: number; time: number; idx: number }[] = [];
    const swingLows: { price: number; time: number; idx: number }[] = [];

    // 1. Detect Fair Value Gaps (3-Bar Imbalance: Bullish & Bearish)
    for (let i = 2; i < candles.length; i++) {
      const cCurrent = candles[i];
      const cMiddle = candles[i - 1];
      const cPrevious = candles[i - 2];

      // Bullish FVG: Low of candle i > High of candle i-2
      if (cCurrent.low > cPrevious.high) {
        const gapSize = cCurrent.low - cPrevious.high;
        const minGap = isGold ? 1.0 : 0.0003;
        if (gapSize >= minGap) {
          fvgs.push({
            id: `fvg-bull-${cMiddle.time}`,
            type: 'BULLISH',
            startTime: cMiddle.time,
            low: cPrevious.high,
            high: cCurrent.low,
            consequentEncroachment: (cPrevious.high + cCurrent.low) / 2,
            label: 'Bullish FVG',
          });
        }
      }

      // Bearish FVG: High of candle i < Low of candle i-2
      if (cCurrent.high < cPrevious.low) {
        const gapSize = cPrevious.low - cCurrent.high;
        const minGap = isGold ? 1.0 : 0.0003;
        if (gapSize >= minGap) {
          fvgs.push({
            id: `fvg-bear-${cMiddle.time}`,
            type: 'BEARISH',
            startTime: cMiddle.time,
            low: cCurrent.high,
            high: cPrevious.low,
            consequentEncroachment: (cCurrent.high + cPrevious.low) / 2,
            label: 'FVG',
          });
        }
      }
    }

    // 2. Detect Fractal Swings (Highs & Lows)
    for (let i = 2; i < candles.length - 2; i++) {
      const c = candles[i];
      if (c.high > candles[i - 1].high && c.high > candles[i - 2].high &&
          c.high > candles[i + 1].high && c.high > candles[i + 2].high) {
        swingHighs.push({ price: c.high, time: c.time, idx: i });
      }
      if (c.low < candles[i - 1].low && c.low < candles[i - 2].low &&
          c.low < candles[i + 1].low && c.low < candles[i + 2].low) {
        swingLows.push({ price: c.low, time: c.time, idx: i });
      }
    }

    // 3. Detect BOS (Break of Structure) & CHoCH (Change of Character)
    for (let h = 0; h < swingHighs.length; h++) {
      const sh = swingHighs[h];
      for (let c = sh.idx + 1; c < candles.length; c++) {
        if (candles[c].close > sh.price) {
          structureLines.push({
            id: `bos-high-${sh.time}`,
            type: h % 2 === 0 ? 'BOS' : 'CHOCH',
            direction: 'BULLISH',
            startTime: sh.time,
            price: sh.price,
            label: h % 2 === 0 ? 'BOS' : 'CHoCH',
          });
          break;
        }
      }
    }

    for (let l = 0; l < swingLows.length; l++) {
      const sl = swingLows[l];
      for (let c = sl.idx + 1; c < candles.length; c++) {
        if (candles[c].close < sl.price) {
          structureLines.push({
            id: `bos-low-${sl.time}`,
            type: l % 2 === 0 ? 'BOS' : 'CHOCH',
            direction: 'BEARISH',
            startTime: sl.time,
            price: sl.price,
            label: l % 2 === 0 ? 'BOS' : 'CHoCH',
          });
          break;
        }
      }
    }

    // Complement with AI Agent levels if available
    if (smcLevels?.bosLevel) {
      structureLines.push({
        id: 'agent-bos',
        type: 'BOS',
        direction: smcLevels.action === 'BUY' ? 'BULLISH' : 'BEARISH',
        startTime: candles[Math.max(0, candles.length - 12)].time,
        price: smcLevels.bosLevel,
        label: 'BOS',
      });
    }

    if (smcLevels?.chochLevel) {
      structureLines.push({
        id: 'agent-choch',
        type: 'CHOCH',
        direction: smcLevels.action === 'BUY' ? 'BULLISH' : 'BEARISH',
        startTime: candles[Math.max(0, candles.length - 8)].time,
        price: smcLevels.chochLevel,
        label: 'CHoCH',
      });
    }

    if (smcLevels?.fvg) {
      fvgs.push({
        id: 'agent-fvg',
        type: smcLevels.action === 'BUY' ? 'BULLISH' : 'BEARISH',
        startTime: candles[Math.max(0, candles.length - 14)].time,
        low: smcLevels.fvg.low,
        high: smcLevels.fvg.high,
        consequentEncroachment: smcLevels.fvg.consequentEncroachment || (smcLevels.fvg.low + smcLevels.fvg.high) / 2,
        label: smcLevels.action === 'BUY' ? 'Bullish FVG' : 'FVG',
      });
    }

    // 4. Buy-Side Liquidity (BSL) & Sell-Side Liquidity (SSL)
    const bsl = smcLevels?.bslTarget 
      ? { price: smcLevels.bslTarget, time: candles[Math.max(0, candles.length - 10)].time }
      : swingHighs.length > 0 
        ? swingHighs[swingHighs.length - 1] 
        : null;

    const ssl = smcLevels?.sslTarget
      ? { price: smcLevels.sslTarget, time: candles[Math.max(0, candles.length - 10)].time }
      : swingLows.length > 0
        ? swingLows[swingLows.length - 1]
        : null;

    // Minor Inducement Level (pullback before current continuation)
    const inducement = swingHighs.length > 1
      ? swingHighs[swingHighs.length - 2]
      : swingLows.length > 1 
        ? { price: swingLows[swingLows.length - 1].price * 1.002, time: swingLows[swingLows.length - 1].time }
        : null;

    // 5. Dynamic Trendline Corridor (Grey boxed dotted lines)
    let trendline: DetectedTrendline | null = null;
    if (swingHighs.length >= 2) {
      const p1 = swingHighs[0];
      const p2 = swingHighs[swingHighs.length - 1];
      trendline = {
        startTime: p1.time,
        endTime: candles[candles.length - 1].time,
        startPrice: p1.price,
        endPrice: p2.price,
        type: p1.price > p2.price ? 'BEARISH' : 'BULLISH',
        label: p1.price > p2.price ? 'Dynamic Bearish Trendline' : 'Dynamic Trendline',
        sublabel: 'Bullish Structure Shift',
      };
    }

    return {
      fvgs: fvgs.slice(-4), // keep the 4 most prominent active FVGs
      structureLines: structureLines.slice(-6),
      bsl,
      ssl,
      inducement,
      trendline,
    };
  }, [candles, smcLevels, isGold]);

  // Dynamic pixel coordinates for SVG overlay
  const [pixelCoords, setPixelCoords] = useState<{
    width: number;
    height: number;
    endX: number;
    fvgs: Array<DetectedFVG & { x1: number; x2: number; yTop: number; yHeight: number; ceY: number }>;
    structureLines: Array<DetectedStructureLine & { x1: number; x2: number; y: number }>;
    bsl: { x: number; y: number; price: number } | null;
    ssl: { x: number; y: number; price: number } | null;
    inducement: { x: number; y: number; price: number } | null;
    trendline: { x1: number; y1: number; x2: number; y2: number; label: string; sublabel: string } | null;
    riskTool: { startX: number; width: number; targetTop: number; targetHeight: number; stopTop: number; stopHeight: number } | null;
  }>({
    width: 800,
    height: 560,
    endX: 740,
    fvgs: [],
    structureLines: [],
    bsl: null,
    ssl: null,
    inducement: null,
    trendline: null,
    riskTool: null,
  });

  // Coordinate recalculation on zoom/scroll
  const updateOverlayCoordinates = useCallback(() => {
    if (!chartInstanceRef.current || !candlestickSeriesRef.current || !chartContainerRef.current) return;
    const container = chartContainerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;
    const endX = width - 58;

    const priceToY = (price?: number | null): number | null => {
      if (typeof price !== 'number' || isNaN(price) || price <= 0) return null;
      try {
        const y = candlestickSeriesRef.current?.priceToCoordinate(price);
        return typeof y === 'number' && !isNaN(y) ? y : null;
      } catch {
        return null;
      }
    };

    const timeScale = chartInstanceRef.current.timeScale();
    const timeToX = (time: number): number => {
      const rawTime = (time > 10000000000 ? Math.floor(time / 1000) : Number(time)) as any;
      const coord = timeScale.timeToCoordinate(rawTime);
      return typeof coord === 'number' && !isNaN(coord) ? coord : width * 0.3;
    };

    // 1. Calculate FVGs pixel coordinates
    const fvgPixels = detectedSMC.fvgs
      .map((f) => {
        const yHigh = priceToY(f.high);
        const yLow = priceToY(f.low);
        const ceY = priceToY(f.consequentEncroachment) || 0;
        if (yHigh === null || yLow === null) return null;

        const yTop = Math.min(yHigh, yLow);
        const yHeight = Math.max(12, Math.abs(yLow - yHigh));
        const x1 = Math.max(20, timeToX(f.startTime));
        const x2 = endX;

        return { ...f, x1, x2, yTop, yHeight, ceY };
      })
      .filter(Boolean) as any[];

    // 2. Calculate Structure Lines (BOS & CHoCH)
    const structPixels = detectedSMC.structureLines
      .map((s) => {
        const y = priceToY(s.price);
        if (y === null) return null;
        const x1 = Math.max(20, timeToX(s.startTime));
        const x2 = endX;
        return { ...s, x1, x2, y };
      })
      .filter(Boolean) as any[];

    // 3. Liquidity Points (BSL, SSL, Inducement)
    const bslY = priceToY(detectedSMC.bsl?.price);
    const bslPixel = bslY !== null && detectedSMC.bsl ? {
      x: Math.max(20, timeToX(detectedSMC.bsl.time)),
      y: bslY,
      price: detectedSMC.bsl.price,
    } : null;

    const sslY = priceToY(detectedSMC.ssl?.price);
    const sslPixel = sslY !== null && detectedSMC.ssl ? {
      x: Math.max(20, timeToX(detectedSMC.ssl.time)),
      y: sslY,
      price: detectedSMC.ssl.price,
    } : null;

    const indY = priceToY(detectedSMC.inducement?.price);
    const indPixel = indY !== null && detectedSMC.inducement ? {
      x: Math.max(20, timeToX(detectedSMC.inducement.time)),
      y: indY,
      price: detectedSMC.inducement.price,
    } : null;

    // 4. Dynamic Trendline
    let tlPixel = null;
    if (detectedSMC.trendline) {
      const y1 = priceToY(detectedSMC.trendline.startPrice);
      const y2 = priceToY(detectedSMC.trendline.endPrice);
      if (y1 !== null && y2 !== null) {
        tlPixel = {
          x1: Math.max(20, timeToX(detectedSMC.trendline.startTime)),
          y1,
          x2: endX - 10,
          y2,
          label: detectedSMC.trendline.label,
          sublabel: detectedSMC.trendline.sublabel,
        };
      }
    }

    // 5. Risk Tool
    let riskPixel = null;
    if (smcLevels?.entryPrice && smcLevels?.stopLoss && smcLevels?.target1) {
      const entryY = priceToY(smcLevels.entryPrice);
      const slY = priceToY(smcLevels.stopLoss);
      const tpY = priceToY(smcLevels.target1);

      if (entryY !== null && slY !== null && tpY !== null) {
        const lastCandleX = candles.length > 0 ? timeToX(candles[candles.length - 1].time) : width - 100;
        const startX = Math.max(20, Math.min(lastCandleX - 25, width - 260));
        const posWidth = Math.min(210, endX - startX);
        const isBuy = smcLevels.action === 'BUY';

        const targetTop = isBuy ? tpY : entryY;
        const targetHeight = Math.max(14, Math.abs(entryY - tpY));
        const stopTop = isBuy ? entryY : slY;
        const stopHeight = Math.max(14, Math.abs(slY - entryY));

        riskPixel = {
          startX,
          width: posWidth,
          targetTop,
          targetHeight,
          stopTop,
          stopHeight,
        };
      }
    }

    setPixelCoords({
      width,
      height,
      endX,
      fvgs: fvgPixels,
      structureLines: structPixels,
      bsl: bslPixel,
      ssl: sslPixel,
      inducement: indPixel,
      trendline: tlPixel,
      riskTool: riskPixel,
    });
  }, [candles, detectedSMC, smcLevels]);

  // Initialize TradingView lightweight chart instance
  useEffect(() => {
    if (!chartContainerRef.current) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
      candlestickSeriesRef.current = null;
      lineSeriesRef.current = null;
      volumeSeriesRef.current = null;
      priceLinesRef.current = [];
      markersRef.current = null;
    }

    const container = chartContainerRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 560;

    const isLight = theme === 'light';

    // Theme Color Configuration: Clean Light Ivory matching reference exactly
    const bgColor = isLight ? '#fcfbf7' : '#0D1016';
    const textColor = isLight ? '#374151' : '#8D96A6';
    const gridColor = isLight ? 'rgba(0, 0, 0, 0.045)' : 'rgba(255, 255, 255, 0.035)';
    const borderColor = isLight ? '#e5e7eb' : '#1F2430';

    // Japanese Candlesticks: Clean Red/Green
    const upCandleColor = '#16a34a';   // Green
    const downCandleColor = '#dc2626'; // Red

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Inter', system-ui, monospace",
      },
      grid: {
        vertLines: { color: gridColor, style: LineStyle.SparseDotted },
        horzLines: { color: gridColor, style: LineStyle.SparseDotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: isLight ? '#0284c7' : 'rgba(201, 160, 74, 0.55)',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: isLight ? '#1e293b' : '#1A1F29',
        },
        horzLine: {
          color: isLight ? '#0284c7' : 'rgba(201, 160, 74, 0.55)',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: isLight ? '#1e293b' : '#1A1F29',
        },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: {
          time: true,
          price: true,
        },
        axisDoubleClickReset: {
          time: true,
          price: true,
        },
        mouseWheel: true,
        pinch: true,
      },
      rightPriceScale: {
        borderColor,
        autoScale: true,
        scaleMargins: {
          top: 0.10,
          bottom: 0.16,
        },
      },
      timeScale: {
        borderColor,
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 10,
        minBarSpacing: 1.5,
        rightOffset: 16, // room to display projected liquidity targets
      },
    });

    // 1. Candlestick Series (Red & Green)
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: upCandleColor,
      downColor: downCandleColor,
      borderUpColor: upCandleColor,
      borderDownColor: downCandleColor,
      wickUpColor: upCandleColor,
      wickDownColor: downCandleColor,
      priceFormat: {
        type: 'price',
        precision: decimals,
        minMove: isGold ? 0.01 : 0.0001,
      },
    });

    // 2. Line Series
    const lineSeries = chart.addSeries(LineSeries, {
      color: isLight ? '#0284c7' : '#D6AE57',
      lineWidth: 2,
      priceFormat: {
        type: 'price',
        precision: decimals,
        minMove: isGold ? 0.01 : 0.0001,
      },
      visible: chartType === 'line',
    });

    // 3. Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.86,
        bottom: 0,
      },
    });

    chartInstanceRef.current = chart;
    candlestickSeriesRef.current = candlestickSeries;
    lineSeriesRef.current = lineSeries;
    volumeSeriesRef.current = volumeSeries;

    // Crosshair Hover Sync
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.seriesData) {
        setHoveredCandle(null);
        return;
      }
      const data = param.seriesData.get(candlestickSeries) as any;
      if (data && typeof data.close === 'number') {
        setHoveredCandle({
          time: Number(param.time),
          open: data.open,
          high: data.high,
          low: data.low,
          close: data.close,
        });
      } else {
        setHoveredCandle(null);
      }
      updateOverlayCoordinates();
    });

    chart.timeScale().subscribeVisibleTimeRangeChange(updateOverlayCoordinates);
    chart.timeScale().subscribeVisibleLogicalRangeChange(updateOverlayCoordinates);

    const handleResize = () => {
      if (chartContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
        updateOverlayCoordinates();
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
        candlestickSeriesRef.current = null;
        lineSeriesRef.current = null;
        volumeSeriesRef.current = null;
        priceLinesRef.current = [];
        markersRef.current = null;
      }
    };
  }, [decimals, isGold, updateOverlayCoordinates, chartType, theme]);

  // Load Candlestick and Volume Data
  useEffect(() => {
    if (!candlestickSeriesRef.current || !candles || candles.length === 0) return;

    const sorted = [...candles]
      .filter((c) => c && typeof c.open === 'number' && typeof c.close === 'number')
      .map((c) => ({
        time: (typeof c.time === 'number' && c.time > 10000000000 ? Math.floor(c.time / 1000) : Number(c.time)) as any,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
        volume: c.volume || 1000,
      }))
      .sort((a, b) => Number(a.time) - Number(b.time));

    const deduped: any[] = [];
    const seenTimes = new Set<number>();
    for (const bar of sorted) {
      if (!seenTimes.has(bar.time)) {
        seenTimes.add(bar.time);
        deduped.push(bar);
      }
    }

    if (deduped.length > 0) {
      candlestickSeriesRef.current.setData(deduped);

      if (lineSeriesRef.current) {
        lineSeriesRef.current.setData(deduped.map((d) => ({ time: d.time, value: d.close })));
      }

      if (volumeSeriesRef.current && showVolume) {
        volumeSeriesRef.current.setData(deduped.map((d) => ({
          time: d.time,
          value: d.volume,
          color: d.close >= d.open ? 'rgba(22, 163, 74, 0.35)' : 'rgba(220, 38, 38, 0.35)',
        })));
      }

      chartInstanceRef.current?.timeScale().fitContent();

      // Native TradingView series marker on the execution bar
      if (smcLevels && deduped.length >= 2) {
        const lastBar = deduped[deduped.length - 1];
        const isBuy = smcLevels.action === 'BUY';

        const markers: any[] = [
          {
            time: lastBar.time,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: isBuy ? '#16a34a' : '#dc2626',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            text: `CTO ${smcLevels.action || 'ENTRY'} (${smcLevels.confidence || 90}%)`,
            size: 1.2,
          }
        ];

        try {
          if (!markersRef.current) {
            markersRef.current = createSeriesMarkers(candlestickSeriesRef.current, markers);
          } else {
            markersRef.current.setMarkers(markers);
          }
        } catch {
          // ignore
        }
      }

      requestAnimationFrame(updateOverlayCoordinates);
    }
  }, [candles, smcLevels, showVolume, updateOverlayCoordinates, theme]);

  // Keep price lines updated
  useEffect(() => {
    if (!candlestickSeriesRef.current) return;

    priceLinesRef.current.forEach((line) => {
      try {
        candlestickSeriesRef.current?.removePriceLine(line);
      } catch {}
    });
    priceLinesRef.current = [];

    if (!smcLevels) return;

    const { entryPrice, stopLoss, target1 } = smcLevels;

    if (typeof entryPrice === 'number' && entryPrice > 0) {
      priceLinesRef.current.push(
        candlestickSeriesRef.current.createPriceLine({
          price: entryPrice,
          color: '#0284c7',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `ENTRY`,
        })
      );
    }

    if (typeof stopLoss === 'number' && stopLoss > 0) {
      priceLinesRef.current.push(
        candlestickSeriesRef.current.createPriceLine({
          price: stopLoss,
          color: '#dc2626',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'SL',
        })
      );
    }

    if (typeof target1 === 'number' && target1 > 0) {
      priceLinesRef.current.push(
        candlestickSeriesRef.current.createPriceLine({
          price: target1,
          color: '#16a34a',
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'TP1 (1:2.0)',
        })
      );
    }

    requestAnimationFrame(updateOverlayCoordinates);
  }, [smcLevels, updateOverlayCoordinates]);

  // Line vs Candlestick visibility toggle
  useEffect(() => {
    if (candlestickSeriesRef.current && lineSeriesRef.current) {
      candlestickSeriesRef.current.applyOptions({ visible: chartType === 'candles' });
      lineSeriesRef.current.applyOptions({ visible: chartType === 'line' });
    }
  }, [chartType]);

  // Zoom and Pan Handlers
  const handleZoomIn = () => {
    if (!chartInstanceRef.current) return;
    const timeScale = chartInstanceRef.current.timeScale();
    const currentSpacing = timeScale.options().barSpacing;
    timeScale.applyOptions({ barSpacing: Math.min(60, currentSpacing * 1.3) });
    setTimeout(updateOverlayCoordinates, 30);
  };

  const handleZoomOut = () => {
    if (!chartInstanceRef.current) return;
    const timeScale = chartInstanceRef.current.timeScale();
    const currentSpacing = timeScale.options().barSpacing;
    timeScale.applyOptions({ barSpacing: Math.max(1, currentSpacing * 0.75) });
    setTimeout(updateOverlayCoordinates, 30);
  };

  const handleResetView = () => {
    if (!chartInstanceRef.current) return;
    chartInstanceRef.current.timeScale().fitContent();
    chartInstanceRef.current.priceScale('right').applyOptions({ autoScale: true });
    setTimeout(updateOverlayCoordinates, 30);
  };

  const toggleFullscreen = () => {
    if (!containerWrapperRef.current) return;
    if (!isFullscreen) {
      if (containerWrapperRef.current.requestFullscreen) {
        containerWrapperRef.current.requestFullscreen();
      }
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
      setIsFullscreen(false);
    }
  };

  const activeCandle = hoveredCandle || (candles && candles.length > 0 ? candles[candles.length - 1] : null);
  const candleChange = activeCandle ? activeCandle.close - activeCandle.open : 0;
  const candleChangePct = activeCandle && activeCandle.open ? (candleChange / activeCandle.open) * 100 : 0;
  const isUp = candleChange >= 0;
  const isLight = theme === 'light';

  return (
    <div
      ref={containerWrapperRef}
      className={`relative flex flex-col rounded-xl overflow-hidden shadow-2xl transition-all ${
        isLight 
          ? 'bg-white border border-paper-line text-slate-800' 
          : 'bg-surface border border-line-2 text-slate-200'
      } ${isFullscreen ? 'fixed inset-0 z-50 rounded-none' : 'w-full h-[660px]'}`}
    >
      {/* ------------------------------------------------------------- */}
      {/* 1. TOP HEADER: TRADINGVIEW HUD BAR (Light-Themed Aesthetic)   */}
      {/* ------------------------------------------------------------- */}
      <div className={`flex flex-wrap items-center justify-between px-3.5 py-2.5 border-b gap-2 select-none ${
        isLight ? 'bg-white border-paper-line' : 'bg-surface-2 border-line-2'
      }`}>
        {/* Left: Gold/EUR Currency Circle + Symbol · 4h · TVC + OHLC */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-600 flex items-center justify-center font-bold text-xs">
              <Coins className="w-3.5 h-3.5 text-amber-600" />
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className={`text-sm font-bold tracking-tight font-mono ${isLight ? 'text-slate-900' : 'text-white'}`}>
                {symbol === 'XAU/USD' ? 'Gold' : 'EUR/USD'}
              </span>
              <span className={`text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>· {activeTimeframe}</span>
              <span className={`text-xs font-semibold ${isLight ? 'text-slate-400' : 'text-slate-500'}`}>· TVC</span>
            </div>
          </div>

          {/* Real-Time OHLC Bar matching reference exactly */}
          {activeCandle && (
            <div className={`hidden lg:flex items-center gap-2.5 text-xs font-mono tabular-nums pl-2.5 border-l ${
              isLight ? 'border-slate-200 text-slate-700' : 'border-line-2 text-slate-300'
            }`}>
              <span>O <span className="font-semibold">{activeCandle.open.toFixed(decimals)}</span></span>
              <span>H <span className="font-semibold">{activeCandle.high.toFixed(decimals)}</span></span>
              <span>L <span className="font-semibold">{activeCandle.low.toFixed(decimals)}</span></span>
              <span>C <span className="font-semibold">{activeCandle.close.toFixed(decimals)}</span></span>
              <span className={isUp ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>
                {isUp ? '+' : ''}{candleChange.toFixed(decimals)} ({isUp ? '+' : ''}{candleChangePct.toFixed(2)}%)
              </span>
            </div>
          )}
        </div>

        {/* Right: Currency Badge, Timeframes, Zoom, Theme & Tools */}
        <div className="flex items-center gap-1.5">
          {/* USD Currency Badge */}
          <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded border uppercase tracking-wider ${
            isLight 
              ? 'bg-slate-100 text-slate-700 border-slate-300' 
              : 'bg-slate-800 text-slate-300 border-slate-700'
          }`}>
            USD
          </span>

          {/* Timeframe Switcher */}
          <div className={`flex items-center rounded-lg p-0.5 border ${
            isLight ? 'bg-slate-100 border-slate-200' : 'bg-surface border-line-2'
          }`}>
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                className={`px-2 py-0.5 text-xs font-mono rounded font-medium transition-all ${
                  activeTimeframe === tf
                    ? isLight
                      ? 'bg-white text-slate-900 shadow-xs border border-slate-200'
                      : 'bg-gold-500/15 text-gold-300 border border-gold-500/30'
                    : isLight
                      ? 'text-slate-600 hover:text-slate-900'
                      : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Full Interactive Zoom Controls (Instant Button Access) */}
          <div className={`flex items-center rounded-lg p-0.5 border ${
            isLight ? 'bg-slate-100 border-slate-200' : 'bg-surface border-line-2'
          }`}>
            <button
              onClick={handleZoomIn}
              title="Zoom In (Expand Candles)"
              className={`p-1 rounded text-xs transition-colors ${
                isLight ? 'text-slate-700 hover:bg-slate-200' : 'text-slate-300 hover:bg-surface-3'
              }`}
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleZoomOut}
              title="Zoom Out (Contract Candles)"
              className={`p-1 rounded text-xs transition-colors ${
                isLight ? 'text-slate-700 hover:bg-slate-200' : 'text-slate-300 hover:bg-surface-3'
              }`}
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetView}
              title="Auto-Fit All Candles"
              className={`p-1 rounded text-xs transition-colors ${
                isLight ? 'text-slate-700 hover:bg-slate-200' : 'text-slate-300 hover:bg-surface-3'
              }`}
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Candlestick vs Line Toggle */}
          <div className={`flex items-center rounded-lg p-0.5 border ${
            isLight ? 'bg-slate-100 border-slate-200' : 'bg-surface border-line-2'
          }`}>
            <button
              onClick={() => setChartType('candles')}
              title="Candlestick View"
              className={`p-1 rounded text-xs transition-colors ${
                chartType === 'candles' 
                  ? isLight ? 'bg-white text-slate-900 shadow-xs' : 'bg-gold-500/15 text-gold-300' 
                  : 'text-slate-400 hover:text-slate-600'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartType('line')}
              title="Line Chart View"
              className={`p-1 rounded text-xs transition-colors ${
                chartType === 'line' 
                  ? isLight ? 'bg-white text-slate-900 shadow-xs' : 'bg-gold-500/15 text-gold-300' 
                  : 'text-slate-400 hover:text-slate-600'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Volume Histogram Toggle */}
          <button
            onClick={() => setShowVolume(!showVolume)}
            title={showVolume ? 'Hide Volume' : 'Show Volume'}
            className={`p-1.5 rounded-lg border text-xs transition-colors ${
              showVolume
                ? isLight ? 'bg-slate-200 text-slate-800 border-slate-300' : 'bg-gold-500/15 text-gold-300 border-gold-500/30'
                : isLight ? 'bg-slate-50 text-slate-400 border-slate-200' : 'bg-surface text-slate-500 border-line-2'
            }`}
          >
            <BarChart className="w-3.5 h-3.5" />
          </button>

          {/* Light / Dark Mode Toggle */}
          <button
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Theme'}
            className={`p-1.5 rounded-lg border transition-colors ${
              isLight ? 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100' : 'bg-surface text-slate-300 border-line-2 hover:bg-surface-3'
            }`}
          >
            {isLight ? <Sun className="w-3.5 h-3.5 text-amber-600" /> : <Moon className="w-3.5 h-3.5 text-gold-400" />}
          </button>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              title="Refresh Data"
              className={`p-1.5 rounded-lg border transition-colors ${
                isLight ? 'border-slate-200 hover:bg-slate-100 text-slate-600' : 'border-line-2 hover:bg-surface-3 text-slate-400'
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-500' : ''}`} />
            </button>
          )}

          <button
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            className={`p-1.5 rounded-lg border transition-colors ${
              isLight ? 'border-slate-200 hover:bg-slate-100 text-slate-600' : 'border-line-2 hover:bg-surface-3 text-slate-400'
            }`}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 2. SMC LAYER CONTROLS (Filter individual SMC components)      */}
      {/* ------------------------------------------------------------- */}
      <div className={`flex items-center justify-between px-3.5 py-1.5 border-b text-xs font-mono gap-2 overflow-x-auto select-none ${
        isLight ? 'bg-paper border-paper-line' : 'bg-surface border-line-2'
      }`}>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`font-bold flex items-center gap-1 mr-1 ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
            <SlidersHorizontal className="w-3 h-3 text-cyan-500" />
            SMC Elements:
          </span>

          {/* Master Toggle */}
          <button
            onClick={() => setShowAllDrawings(!showAllDrawings)}
            className={`px-2 py-0.5 rounded transition-all font-semibold flex items-center gap-1 border ${
              showAllDrawings
                ? isLight ? 'bg-cyan-100 text-cyan-800 border-cyan-300' : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-xs'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <Eye className="w-3 h-3" />
            <span>All SMC</span>
          </button>

          {/* FVG Toggle */}
          <button
            onClick={() => setShowFVG(!showFVG)}
            className={`px-2 py-0.5 rounded transition-all flex items-center gap-1 border ${
              showFVG && showAllDrawings
                ? isLight ? 'bg-emerald-50 text-emerald-800 border-emerald-300' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <Droplet className="w-3 h-3 text-emerald-600" />
            <span>FVG Zones</span>
          </button>

          {/* Structure Lines Toggle (BOS/CHoCH) */}
          <button
            onClick={() => setShowStructure(!showStructure)}
            className={`px-2 py-0.5 rounded transition-all flex items-center gap-1 border ${
              showStructure && showAllDrawings
                ? isLight ? 'bg-rose-50 text-rose-800 border-rose-300' : 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <TrendingUp className="w-3 h-3 text-rose-600" />
            <span>Structure (BOS/CHoCH)</span>
          </button>

          {/* Trendline Corridor Toggle */}
          <button
            onClick={() => setShowTrendlines(!showTrendlines)}
            className={`px-2 py-0.5 rounded transition-all flex items-center gap-1 border ${
              showTrendlines && showAllDrawings
                ? isLight ? 'bg-slate-200 text-slate-800 border-slate-300' : 'bg-slate-700 text-slate-200 border-slate-600'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <Activity className="w-3 h-3 text-slate-600" />
            <span>Trendlines (Corridor)</span>
          </button>

          {/* Liquidity Markers (BSL/SSL) */}
          <button
            onClick={() => setShowLiquidity(!showLiquidity)}
            className={`px-2 py-0.5 rounded transition-all flex items-center gap-1 border ${
              showLiquidity && showAllDrawings
                ? isLight ? 'bg-sky-50 text-sky-800 border-sky-300' : 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <Crosshair className="w-3 h-3 text-sky-600" />
            <span>Liquidity (BSL / SSL)</span>
          </button>

          {/* Risk Tool Toggle */}
          <button
            onClick={() => setShowRiskTool(!showRiskTool)}
            className={`px-2 py-0.5 rounded transition-all flex items-center gap-1 border ${
              showRiskTool && showAllDrawings
                ? isLight ? 'bg-emerald-50 text-emerald-800 border-emerald-300' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : isLight ? 'bg-white text-slate-400 border-slate-200' : 'bg-surface-2 text-slate-500 border-line-2'
            }`}
          >
            <Scale className="w-3 h-3 text-emerald-600" />
            <span>Risk Tool (1:2 R:R)</span>
          </button>
        </div>

        <div className={`hidden sm:flex items-center gap-2 text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
          <span>Click & drag to pan · Scroll wheel to zoom</span>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 3. MAIN CHART CANVAS + NON-BLOCKING CUSTOM SMC OVERLAYS       */}
      {/* ------------------------------------------------------------- */}
      <div className={`relative flex-1 w-full min-h-0 cursor-crosshair ${isLight ? 'bg-paper' : 'bg-surface'}`}>
        {/* Canvas for lightweight-charts (Receives 100% of user clicks/drag/wheel) */}
        <div ref={chartContainerRef} className="w-full h-full relative z-5" />

        {/* ----------------------------------------------------------- */}
        {/* CUSTOM SMC OVERLAY LAYER (STRICTLY NON-BLOCKING)            */}
        {/* ----------------------------------------------------------- */}
        {showAllDrawings && (
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none z-10 overflow-hidden"
            style={{ width: '100%', height: '100%', pointerEvents: 'none' }}
          >
            <defs>
              <marker id="arrowUpTeal" markerWidth="6" markerHeight="6" refX="3" refY="1" orient="auto">
                <path d="M0,6 L3,0 L6,6 Z" fill="#0284c7" />
              </marker>
              <marker id="arrowDownDark" markerWidth="6" markerHeight="6" refX="3" refY="5" orient="auto">
                <path d="M0,0 L3,6 L6,0 Z" fill="#0f172a" />
              </marker>
              <marker id="arrowRedBOS" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
                <path d="M0,0 L5,2.5 L0,5 Z" fill="#dc2626" />
              </marker>
              <marker id="arrowTealCHoCH" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
                <path d="M0,0 L5,2.5 L0,5 Z" fill="#0d9488" />
              </marker>
            </defs>

            {/* A. FVG ZONES: Translucent shaded rectangles (light green bullish, light red/cyan bearish) */}
            {showFVG && pixelCoords.fvgs.map((fvg) => {
              const isBull = fvg.type === 'BULLISH';
              const boxFill = isLight
                ? isBull ? 'rgba(34, 197, 94, 0.16)' : 'rgba(6, 182, 212, 0.14)'
                : isBull ? 'rgba(34, 197, 94, 0.12)' : 'rgba(6, 182, 212, 0.12)';
              const strokeColor = isBull ? '#86efac' : '#a5f3fc';
              const textColor = isBull ? '#15803d' : '#0891b2';

              return (
                <g key={fvg.id} className="transition-all duration-150 pointer-events-none">
                  {/* Shaded FVG Rectangle */}
                  <rect
                    x={fvg.x1}
                    y={fvg.yTop}
                    width={Math.max(80, fvg.x2 - fvg.x1)}
                    height={fvg.yHeight}
                    fill={boxFill}
                    stroke={strokeColor}
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                  {/* Small text label inside saying 'Bullish FVG' or 'FVG' */}
                  <text
                    x={fvg.x1 + 10}
                    y={fvg.yTop + 14}
                    fill={textColor}
                    fontStyle="italic"
                    fontWeight="700"
                    fontSize={11}
                    fontFamily="'Inter', system-ui, sans-serif"
                  >
                    {fvg.label}
                  </text>

                  {/* 50% Consequent Encroachment (CE) Dashed Midline */}
                  {fvg.ceY > 0 && (
                    <line
                      x1={fvg.x1}
                      y1={fvg.ceY}
                      x2={fvg.x2}
                      y2={fvg.ceY}
                      stroke={isBull ? '#22c55e' : '#06b6d4'}
                      strokeWidth={1.2}
                      strokeDasharray="4 3"
                    />
                  )}
                </g>
              );
            })}

            {/* B. STRUCTURE LINES: Horizontal dotted/dashed lines for BOS and CHoCH at exact swing points */}
            {showStructure && pixelCoords.structureLines.map((s) => {
              const isBOS = s.type === 'BOS';
              const lineColor = isBOS ? '#dc2626' : '#0d9488'; // BOS in red/green, CHoCH in teal
              const markerId = isBOS ? 'url(#arrowRedBOS)' : 'url(#arrowTealCHoCH)';

              return (
                <g key={s.id} className="transition-all duration-150 pointer-events-none">
                  <line
                    x1={s.x1}
                    y1={s.y}
                    x2={s.x2}
                    y2={s.y}
                    stroke={lineColor}
                    strokeWidth={1.3}
                    strokeDasharray="4 3"
                    markerEnd={markerId}
                  />
                  {/* Tiny text label ('BOS' or 'CHoCH') */}
                  <text
                    x={s.x1 + 14}
                    y={s.y - 4}
                    fill={lineColor}
                    fontWeight="700"
                    fontSize={10.5}
                    fontFamily="'Inter', system-ui, sans-serif"
                  >
                    {s.label}
                  </text>
                </g>
              );
            })}

            {/* C. DYNAMIC TRENDLINES: Grey boxed dotted lines */}
            {showTrendlines && pixelCoords.trendline && (
              <g className="transition-all duration-150 pointer-events-none">
                {/* Grey shaded boxed corridor */}
                <polygon
                  points={`
                    ${pixelCoords.trendline.x1},${pixelCoords.trendline.y1}
                    ${pixelCoords.trendline.x2},${pixelCoords.trendline.y2}
                    ${pixelCoords.trendline.x2},${pixelCoords.trendline.y2 + 20}
                    ${pixelCoords.trendline.x1},${pixelCoords.trendline.y1 + 20}
                  `}
                  fill={isLight ? 'rgba(241, 245, 249, 0.65)' : 'rgba(148, 163, 184, 0.12)'}
                  stroke="#94a3b8"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
                {/* Centerline */}
                <line
                  x1={pixelCoords.trendline.x1}
                  y1={pixelCoords.trendline.y1 + 10}
                  x2={pixelCoords.trendline.x2}
                  y2={pixelCoords.trendline.y2 + 10}
                  stroke="#475569"
                  strokeWidth={1.2}
                  strokeDasharray="2 3"
                />
                {/* Trendline Text Labels */}
                <text
                  x={(pixelCoords.trendline.x1 + pixelCoords.trendline.x2) / 2 - 80}
                  y={(pixelCoords.trendline.y1 + pixelCoords.trendline.y2) / 2 - 6}
                  fill={isLight ? '#0f172a' : '#f8fafc'}
                  fontStyle="italic"
                  fontWeight="700"
                  fontSize={11.5}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  {pixelCoords.trendline.label}
                </text>
                <text
                  x={(pixelCoords.trendline.x1 + pixelCoords.trendline.x2) / 2 - 20}
                  y={(pixelCoords.trendline.y1 + pixelCoords.trendline.y2) / 2 + 16}
                  fill={isLight ? '#0f172a' : '#f8fafc'}
                  fontStyle="italic"
                  fontWeight="700"
                  fontSize={11.5}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  {pixelCoords.trendline.sublabel}
                </text>
              </g>
            )}

            {/* D. LIQUIDITY MARKERS: Buy-Side Liquidity & Arrows pointing to exact price levels */}
            {showLiquidity && pixelCoords.bsl && (
              <g className="transition-all duration-150 pointer-events-none">
                <line
                  x1={pixelCoords.bsl.x}
                  y1={pixelCoords.bsl.y}
                  x2={pixelCoords.endX}
                  y2={pixelCoords.bsl.y}
                  stroke={isLight ? '#334155' : '#94a3b8'}
                  strokeWidth={1.2}
                  strokeDasharray="4 3"
                />
                <text
                  x={pixelCoords.endX - 190}
                  y={pixelCoords.bsl.y - 7}
                  fill={isLight ? '#0f172a' : '#f8fafc'}
                  fontStyle="italic"
                  fontWeight="700"
                  fontSize={12}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  Buy-Side Liquidity
                </text>
                <text
                  x={pixelCoords.endX - 175}
                  y={pixelCoords.bsl.y + 15}
                  fill="#0284c7"
                  fontWeight="600"
                  fontSize={10}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  [Swing high of Structure]
                </text>
                {/* Arrow pointing to exact BSL price level */}
                <line
                  x1={pixelCoords.endX - 110}
                  y1={pixelCoords.bsl.y + 26}
                  x2={pixelCoords.endX - 110}
                  y2={pixelCoords.bsl.y + 5}
                  stroke="#0284c7"
                  strokeWidth={1.4}
                  markerEnd="url(#arrowUpTeal)"
                />
              </g>
            )}

            {/* Minor Inducement Level */}
            {showLiquidity && pixelCoords.inducement && (
              <g className="transition-all duration-150 pointer-events-none">
                <line
                  x1={pixelCoords.inducement.x}
                  y1={pixelCoords.inducement.y}
                  x2={pixelCoords.endX}
                  y2={pixelCoords.inducement.y}
                  stroke="#0284c7"
                  strokeWidth={1.2}
                  strokeDasharray="4 3"
                />
                <text
                  x={pixelCoords.endX - 240}
                  y={pixelCoords.inducement.y - 6}
                  fill={isLight ? '#0f172a' : '#f8fafc'}
                  fontStyle="italic"
                  fontWeight="700"
                  fontSize={11.5}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  Minor Inducement Level
                </text>
                <text
                  x={pixelCoords.endX - 190}
                  y={pixelCoords.inducement.y - 18}
                  fill="#0284c7"
                  fontWeight="600"
                  fontSize={10}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  Minor Inducement
                </text>
                <line
                  x1={pixelCoords.endX - 130}
                  y1={pixelCoords.inducement.y + 22}
                  x2={pixelCoords.endX - 130}
                  y2={pixelCoords.inducement.y + 4}
                  stroke="#0284c7"
                  strokeWidth={1.4}
                  markerEnd="url(#arrowUpTeal)"
                />
              </g>
            )}

            {/* Sell-Side Liquidity & Discount */}
            {showLiquidity && pixelCoords.ssl && (
              <g className="transition-all duration-150 pointer-events-none">
                <line
                  x1={pixelCoords.ssl.x}
                  y1={pixelCoords.ssl.y}
                  x2={pixelCoords.endX}
                  y2={pixelCoords.ssl.y}
                  stroke={isLight ? '#0f172a' : '#cbd5e1'}
                  strokeWidth={1.2}
                  strokeDasharray="4 3"
                />
                <text
                  x={pixelCoords.endX - 200}
                  y={pixelCoords.ssl.y + 16}
                  fill={isLight ? '#0f172a' : '#f8fafc'}
                  fontStyle="italic"
                  fontWeight="700"
                  fontSize={11.5}
                  fontFamily="'Inter', system-ui, sans-serif"
                >
                  Discount & Sell-Side
                </text>
                <line
                  x1={pixelCoords.endX - 150}
                  y1={pixelCoords.ssl.y - 12}
                  x2={pixelCoords.endX - 150}
                  y2={pixelCoords.ssl.y + 2}
                  stroke={isLight ? '#0f172a' : '#cbd5e1'}
                  strokeWidth={1.4}
                  markerEnd="url(#arrowDownDark)"
                />
              </g>
            )}

            {/* E. RISK TOOL: TRADINGVIEW LONG/SHORT POSITION BOX */}
            {showRiskTool && pixelCoords.riskTool && (
              <g className="transition-all duration-150 pointer-events-none">
                {/* Target Profit Zone */}
                <rect
                  x={pixelCoords.riskTool.startX}
                  y={pixelCoords.riskTool.targetTop}
                  width={pixelCoords.riskTool.width}
                  height={pixelCoords.riskTool.targetHeight}
                  fill="rgba(34, 197, 94, 0.22)"
                  stroke="#16a34a"
                  strokeWidth={1.2}
                />
                <text
                  x={pixelCoords.riskTool.startX + 8}
                  y={pixelCoords.riskTool.targetTop + 14}
                  fill="#15803d"
                  fontSize={9.5}
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  Target (1:2.0 Net RR)
                </text>

                {/* Stop Loss Zone */}
                <rect
                  x={pixelCoords.riskTool.startX}
                  y={pixelCoords.riskTool.stopTop}
                  width={pixelCoords.riskTool.width}
                  height={pixelCoords.riskTool.stopHeight}
                  fill="rgba(220, 38, 38, 0.20)"
                  stroke="#dc2626"
                  strokeWidth={1.2}
                />
                <text
                  x={pixelCoords.riskTool.startX + 8}
                  y={pixelCoords.riskTool.stopTop + 14}
                  fill="#991b1b"
                  fontSize={9.5}
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  Stop Loss ({smcLevels?.slPips || 25} {pipUnit})
                </text>
              </g>
            )}
          </svg>
        )}

        {/* Bottom Left TradingView Caption (as in screenshot) */}
        <div className="absolute bottom-2.5 left-4 z-20 pointer-events-none select-none max-w-[85%] flex flex-col gap-1">
          <div className={`text-xs font-medium italic ${isLight ? 'text-slate-600' : 'text-slate-400'}`}>
            Price action shows how liquidity, CHoCH, BOS and FVGs work together to reveal market structure.
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[12px] font-black tracking-tight ${isLight ? 'text-slate-800' : 'text-slate-300'}`}>
              TradingView
            </span>
            <span className={`text-xs ${isLight ? 'text-slate-400' : 'text-slate-500'}`}>
              · EXUNU SMC INSTITUTIONAL TERMINAL
            </span>
          </div>
        </div>

        {/* Live Market Price Badge on Right Axis */}
        <div className="absolute right-1 bottom-14 z-20 pointer-events-none flex flex-col items-end gap-1 select-none">
          <div className="bg-sky-500 text-white text-xs font-mono font-bold px-2 py-0.5 rounded shadow-md">
            {currentPrice.toFixed(decimals)}
          </div>
        </div>
      </div>
    </div>
  );
};
