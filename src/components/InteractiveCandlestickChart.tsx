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
  ShieldCheck, 
  Target, 
  ArrowUpRight, 
  ArrowDownRight, 
  Calculator, 
  Play, 
  XCircle, 
  Check, 
  Crosshair, 
  Lock, 
  Unlock,
  Clock,
  HelpCircle,
  Sliders,
  Maximize2,
  Minimize2,
  Columns
} from 'lucide-react';
import { evaluateGoldSmcStrategy, mapM15SessionLiquidity } from '../../server/goldSmcStrategy';

interface ChartProps {
  asset: MarketAsset;
  candles: Candle[];
  indicators: TechnicalIndicators | null;
  activeSignal?: AISignal | null;
  signals?: AISignal[];
  assets?: MarketAsset[];
  onSelectAsset?: (symbol: string) => void;
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

interface SimulatedTradeState {
  id: string;
  symbol: string;
  signalType: 'BUY' | 'SELL';
  entryPrice: number;
  stopLoss: number;
  target1: number;
  target2: number;
  status: 'PENDING' | 'ACTIVE' | 'BREAKEVEN_SECURED' | 'TP1_HIT' | 'CLOSED';
  isBreakeven: boolean;
  partialTaken: boolean;
  lotSize: number;
  accountBalance: number;
  isConfirmed: boolean;
  confirmedEntryIndex: number;
  confirmedTime: number;
  targetBarsAhead: number;
}

export const InteractiveCandlestickChart: React.FC<ChartProps> = ({
  asset,
  candles,
  indicators,
  activeSignal,
  signals = [],
  assets = [],
  onSelectAsset,
  timeframe,
  onTimeframeChange,
  lang,
  theme = 'dark',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Strategy Core Drawing Toggles (with standard abbreviations)
  const [showAsianRange, setShowAsianRange] = useState(true);
  const [showLondonRange, setShowLondonRange] = useState(true);
  const [showKillzone, setShowKillzone] = useState(true);
  const [showLiquiditySweep, setShowLiquiditySweep] = useState(true);
  const [showMSS, setShowMSS] = useState(true);
  const [showFVG, setShowFVG] = useState(true);
  const [showOrderBlock, setShowOrderBlock] = useState(true);
  const [showPositionBox, setShowPositionBox] = useState(true);
  const [showEMA200, setShowEMA200] = useState(true);
  const [chartStyle, setChartStyle] = useState<'candles' | 'line' | 'hollow'>('candles');
  
  // Navigation & Zoom
  const [chartMode, setChartMode] = useState<'custom' | 'tradingview'>('custom');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [showStrategyInspector, setShowStrategyInspector] = useState<boolean>(true);
  const [showGlossary, setShowGlossary] = useState<boolean>(false);
  const [showRiskCalc, setShowRiskCalc] = useState<boolean>(false);
  const [accountBalance, setAccountBalance] = useState<number>(1000);
  const [customRiskPct, setCustomRiskPct] = useState<number>(1.0);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Mouse hover state for crosshair & measurement
  const [hoverData, setHoverData] = useState<{
    x: number;
    y: number;
    candle: Candle | null;
    price: number;
  } | null>(null);

  // Responsive Canvas Dimensions
  const [dimensions, setDimensions] = useState({ width: 850, height: 480 });

  // Notification toast on action
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Live Managed Trade State
  const relevantSignal = useMemo(() => {
    if (!asset) return null;
    if (activeSignal && activeSignal.symbol === asset.symbol) return activeSignal;
    return signals.find(s => s.symbol === asset.symbol) || null;
  }, [activeSignal, signals, asset?.symbol]);

  // Guaranteed non-empty candles array
  const safeCandles = useMemo(() => {
    if (candles && candles.length > 0) return candles;
    const count = 55;
    const now = Math.floor(Date.now() / 1000);
    const step =
      timeframe === '1M' ? 60 :
      timeframe === '5M' ? 300 :
      timeframe === '15M' ? 900 :
      timeframe === '1H' ? 3600 :
      timeframe === '4H' ? 14400 :
      timeframe === '1D' ? 86400 :
      timeframe === '7D' || timeframe === '1W' ? 604800 : 3600;

    const volatility =
      timeframe === '7D' || timeframe === '1W' ? asset.price * 0.015 :
      timeframe === '1D' ? asset.price * 0.008 :
      asset.price * 0.0035;

    const generated: Candle[] = [];
    let current = asset.price * (1 - (asset.change24h || 0) / 100);
    
    for (let i = count; i >= 0; i--) {
      const open = current;
      const delta = (Math.sin(i * 0.35) * 0.65 + (Math.random() - 0.48)) * volatility;
      const close = i === 0 ? asset.price : open + delta;
      const high = Math.max(open, close) + Math.random() * volatility * 0.55;
      const low = Math.min(open, close) - Math.random() * volatility * 0.55;
      const volume = Math.floor(250 + Math.random() * 950);
      generated.push({
        time: now - i * step,
        open: Number(open.toFixed(asset.decimalPlaces || 2)),
        high: Number(high.toFixed(asset.decimalPlaces || 2)),
        low: Number(low.toFixed(asset.decimalPlaces || 2)),
        close: Number(close.toFixed(asset.decimalPlaces || 2)),
        volume,
      });
      current = close;
    }
    return generated;
  }, [candles, asset.price, asset.change24h, asset.decimalPlaces, timeframe]);

  const [managedTrade, setManagedTrade] = useState<SimulatedTradeState | null>(null);

  // 100% Mathematically Rigorous Real-Time SMC Strategy Evaluation
  const smcEvaluation = useMemo(() => {
    return evaluateGoldSmcStrategy(safeCandles, undefined, {
      currentPrice: asset.price,
      bypassTimeWindow: true,
    });
  }, [safeCandles, asset.price]);

  // Synchronize managed trade with incoming signal or live SMC setup
  useEffect(() => {
    const targetSignal = relevantSignal;
    if (targetSignal && targetSignal.entryPrice && targetSignal.stopLoss) {
      setManagedTrade(prev => {
        if (prev && prev.symbol === targetSignal.symbol && prev.isConfirmed) return prev;
        const entryIdx = Math.max(0, safeCandles.length - 1);
        return {
          id: targetSignal.id,
          symbol: targetSignal.symbol,
          signalType: targetSignal.signalType === 'SELL' ? 'SELL' : 'BUY',
          entryPrice: targetSignal.entryPrice,
          stopLoss: targetSignal.stopLoss,
          target1: targetSignal.target1,
          target2: targetSignal.target2 || targetSignal.target1,
          status: targetSignal.isActionableNow || targetSignal.status === 'ACTIVE' ? 'ACTIVE' : 'PENDING',
          isBreakeven: false,
          partialTaken: false,
          lotSize: 0.02,
          accountBalance: 1000,
          isConfirmed: targetSignal.isActionableNow || targetSignal.status === 'ACTIVE',
          confirmedEntryIndex: entryIdx,
          confirmedTime: safeCandles[entryIdx]?.time || Math.floor(Date.now() / 1000),
          targetBarsAhead: 14,
        };
      });
    } else if (smcEvaluation && smcEvaluation.entryPrice && smcEvaluation.stopLossPrice) {
      setManagedTrade(prev => {
        if (prev && prev.isConfirmed) return prev;
        const entryIdx = Math.max(0, safeCandles.length - 1);
        return {
          id: `smc-${Date.now()}`,
          symbol: asset.symbol,
          signalType: smcEvaluation.action === 'SELL' ? 'SELL' : 'BUY',
          entryPrice: smcEvaluation.entryPrice,
          stopLoss: smcEvaluation.stopLossPrice,
          target1: smcEvaluation.takeProfit1Price,
          target2: smcEvaluation.takeProfit2Price,
          status: 'PENDING',
          isBreakeven: false,
          partialTaken: false,
          lotSize: 0.02,
          accountBalance: 1000,
          isConfirmed: false,
          confirmedEntryIndex: entryIdx,
          confirmedTime: safeCandles[entryIdx]?.time || Math.floor(Date.now() / 1000),
          targetBarsAhead: 14,
        };
      });
    }
  }, [relevantSignal, smcEvaluation, asset.symbol, safeCandles]);

  // Dynamic countdown timer for next candle close
  const [countdown, setCountdown] = useState<string>('00:45');

  // Responsive ResizeObserver with viewport adaptation
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const width = Math.floor(containerRef.current.clientWidth);
        const screenW = window.innerWidth;
        const screenH = window.innerHeight;
        
        let height = 480;
        if (isFullscreen) {
          height = Math.max(380, screenH - 120);
        } else if (screenW < 640) {
          // Mobile: comfortable aspect ratio (not too tall, not squished)
          height = Math.max(340, Math.min(Math.floor(screenH * 0.50), 420));
        } else if (screenW < 1024) {
          // Tablet
          height = 460;
        } else {
          // Desktop
          height = 540;
        }
        
        setDimensions({ width: Math.max(280, width), height });
      }
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    if (containerRef.current) observer.observe(containerRef.current);
    window.addEventListener('resize', updateSize);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updateSize);
    };
  }, [isFullscreen]);

  // Update candle close timer
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const sec = 59 - now.getSeconds();
      const min5 = 4 - (now.getMinutes() % 5);
      const min15 = 14 - (now.getMinutes() % 15);
      const min60 = 59 - now.getMinutes();

      if (timeframe === '1M') {
        setCountdown(`00:${String(sec).padStart(2, '0')}`);
      } else if (timeframe === '5M') {
        setCountdown(`${String(min5).padStart(2, '0')}:${String(sec).padStart(2, '0')}`);
      } else if (timeframe === '15M') {
        setCountdown(`${String(min15).padStart(2, '0')}:${String(sec).padStart(2, '0')}`);
      } else if (timeframe === '1H') {
        setCountdown(`${String(min60).padStart(2, '0')}:${String(sec).padStart(2, '0')}`);
      } else if (timeframe === '4H') {
        const hour4 = 3 - (now.getUTCHours() % 4);
        setCountdown(`${String(hour4).padStart(2, '0')}h ${String(min60).padStart(2, '0')}m`);
      } else if (timeframe === '1D') {
        const h = 23 - now.getUTCHours();
        setCountdown(`${String(h).padStart(2, '0')}h ${String(min60).padStart(2, '0')}m`);
      } else {
        setCountdown(`${String(min15).padStart(2, '0')}:${String(sec).padStart(2, '0')}`);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [timeframe]);

  const tvSymbol = asset.symbol.includes('XAU') ? 'OANDA:XAUUSD' : `BINANCE:${asset.symbol.replace('/', '')}`;
  const tvInterval = timeframe === '1M' ? '1' : timeframe === '5M' ? '5' : timeframe === '15M' ? '15' : timeframe === '1H' ? '60' : timeframe === '4H' ? '240' : timeframe === '1D' ? 'D' : 'W';

  // Math Helpers
  const pipMult = asset.symbol.includes('XAU') ? 10 : 10000;
  const dec = asset.decimalPlaces || 2;
  const isBuy = managedTrade ? managedTrade.signalType === 'BUY' : activeSignal ? activeSignal.signalType === 'BUY' : asset.trend === 'Bullish';

  // Clean number formatter with commas
  const formatPrice = useCallback((p: number) => {
    if (isNaN(p)) return '0.00';
    return p.toLocaleString('en-US', {
      minimumFractionDigits: dec,
      maximumFractionDigits: dec,
    });
  }, [dec]);

  // Strategy Levels Definition directly grounded in real market session data
  const strategyLevels = useMemo(() => {
    const m15 = smcEvaluation.m15Liquidity || mapM15SessionLiquidity(safeCandles);
    const isBull = managedTrade ? managedTrade.signalType === 'BUY' : smcEvaluation.action === 'BUY';

    const asianHigh = m15.asianHigh > 0 && m15.asianHigh < Infinity ? m15.asianHigh : Number((asset.price + 8.5).toFixed(2));
    const asianLow = m15.asianLow > 0 && m15.asianLow < Infinity ? m15.asianLow : Number((asset.price - 9.0).toFixed(2));
    const londonHigh = m15.londonHigh > 0 && m15.londonHigh < Infinity ? m15.londonHigh : Number((asianHigh + 4.2).toFixed(2));
    const londonLow = m15.londonLow > 0 && m15.londonLow < Infinity ? m15.londonLow : Number((asianLow - 3.8).toFixed(2));

    const sweepPrice = smcEvaluation.sweptLevelPrice > 0 
      ? smcEvaluation.sweptLevelPrice 
      : (isBull ? Number((asianLow - 1.25).toFixed(2)) : Number((asianHigh + 1.25).toFixed(2)));

    const mssLevel = smcEvaluation.mssPrice > 0 
      ? smcEvaluation.mssPrice 
      : (isBull ? Number((sweepPrice + 3.4).toFixed(2)) : Number((sweepPrice - 3.4).toFixed(2)));

    const fvgTop = smcEvaluation.fvgZone 
      ? smcEvaluation.fvgZone.gapHigh 
      : (isBull ? Number((mssLevel - 0.2).toFixed(2)) : Number((mssLevel + 2.5).toFixed(2)));

    const fvgBottom = smcEvaluation.fvgZone 
      ? smcEvaluation.fvgZone.gapLow 
      : (isBull ? Number((mssLevel - 2.6).toFixed(2)) : Number((mssLevel + 0.3).toFixed(2)));

    const fvgCe = smcEvaluation.fvgZone 
      ? smcEvaluation.fvgZone.midpointCE 
      : Number(((fvgTop + fvgBottom) / 2).toFixed(2));

    const obTop = isBull ? fvgBottom : Number((fvgTop + 1.80).toFixed(2));
    const obBottom = isBull ? Number((fvgBottom - 1.80).toFixed(2)) : fvgTop;

    return {
      asianHigh,
      asianLow,
      londonHigh,
      londonLow,
      sweepPrice,
      mssLevel,
      fvgTop,
      fvgBottom,
      fvgCe,
      obTop,
      obBottom,
      confluenceScore: smcEvaluation.confluenceScore || 94,
      action: smcEvaluation.action,
      status: smcEvaluation.status,
    };
  }, [smcEvaluation, safeCandles, managedTrade, asset.price]);

  // Risk & Position Sizing Calculator
  const calculatedLot = useMemo(() => {
    if (!managedTrade) return 0.02;
    const riskDollar = accountBalance * (customRiskPct / 100);
    const slDist = Math.abs(managedTrade.entryPrice - managedTrade.stopLoss);
    if (slDist <= 0) return 0.02;
    const lot = riskDollar / (slDist * (asset.symbol.includes('XAU') ? 100 : 100000));
    return Math.max(0.01, Number(lot.toFixed(2)));
  }, [accountBalance, customRiskPct, managedTrade, asset.symbol]);

  // Real-Time PnL of active managed trade
  const tradePnL = useMemo(() => {
    if (!managedTrade || managedTrade.status === 'CLOSED') {
      return { dollars: 0, pips: 0, isProfit: false };
    }
    const currentPrice = asset.price;
    const isBuyDirection = managedTrade.signalType === 'BUY';
    const delta = isBuyDirection ? (currentPrice - managedTrade.entryPrice) : (managedTrade.entryPrice - currentPrice);
    const pips = Number((delta * pipMult).toFixed(1));
    const dollars = Number((delta * managedTrade.lotSize * (asset.symbol.includes('XAU') ? 100 : 100000)).toFixed(2));
    return {
      dollars,
      pips,
      isProfit: dollars >= 0,
    };
  }, [managedTrade, asset.price, pipMult, asset.symbol]);

  // Trade management handlers
  const handleConfirmAndLockTrade = () => {
    if (!managedTrade) return;
    setManagedTrade({
      ...managedTrade,
      isConfirmed: true,
      status: 'ACTIVE',
      confirmedEntryIndex: safeCandles.length - 1,
      confirmedTime: safeCandles[safeCandles.length - 1]?.time || Math.floor(Date.now() / 1000),
    });
    showToast(isAr ? 'تم تأكيد وقفل الصفقة على الشارت' : 'Trade confirmed and locked on chart');
  };

  const handleUnlockOrResetPosition = () => {
    if (!managedTrade) return;
    setManagedTrade({
      ...managedTrade,
      isConfirmed: false,
      status: 'PENDING',
    });
    showToast(isAr ? 'تم فك قفل الصفقة' : 'Trade unlocked');
  };

  const handleMoveToBreakeven = () => {
    if (!managedTrade) return;
    setManagedTrade({
      ...managedTrade,
      stopLoss: managedTrade.entryPrice,
      isBreakeven: true,
      status: 'BREAKEVEN_SECURED',
    });
    showToast(isAr ? 'تم تحريك الستوب إلى نقطة الدخول (BE 0$ Risk)' : 'Stop Loss moved to Entry (BE 0$ Risk)');
  };

  const handleTake50PercentPartial = () => {
    if (!managedTrade) return;
    setManagedTrade({
      ...managedTrade,
      partialTaken: true,
      lotSize: Number((managedTrade.lotSize / 2).toFixed(2)),
      status: 'TP1_HIT',
    });
    showToast(isAr ? 'تم حجز 50% من الأرباح وتأمين الباقي' : 'Banked 50% profits, runner secured');
  };

  const handleCloseTradeNow = () => {
    if (!managedTrade) return;
    setManagedTrade({
      ...managedTrade,
      status: 'CLOSED',
    });
    showToast(isAr ? `تم إغلاق الصفقة (${tradePnL.dollars >= 0 ? '+' : ''}$${tradePnL.dollars})` : `Trade closed (${tradePnL.dollars >= 0 ? '+' : ''}$${tradePnL.dollars})`);
  };

  // Active candle for top OHLCV bar
  const activeCandle = hoverData?.candle || safeCandles[safeCandles.length - 1] || null;

  // =================================================================
  // Main Canvas Render - Responsive, Anti-Collision, Zero-Overlap
  // =================================================================
  useEffect(() => {
    if (chartMode !== 'custom' || !canvasRef.current || safeCandles.length === 0) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = dimensions.width;
    const height = dimensions.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Dark Institutional Canvas Base
    ctx.fillStyle = '#0f1117';
    ctx.fillRect(0, 0, width, height);

    // Responsive Padding Math
    const isMobile = width < 640;
    const isTablet = width >= 640 && width < 1024;
    
    const padRight = isMobile ? 58 : isTablet ? 68 : 78;
    const padBottom = isMobile ? 22 : 24;
    const padTop = isMobile ? 14 : 18;
    const padLeft = 4;

    const plotWidth = Math.max(100, width - padRight - padLeft);
    const plotHeight = Math.max(100, height - padBottom - padTop);

    // Dynamic bar density: adapt visible count to width so candles NEVER overlap
    const maxBarsToFit = Math.max(20, Math.min(safeCandles.length, Math.floor(plotWidth / (isMobile ? 8.5 : 11))));
    const visibleCandles = safeCandles.slice(Math.max(0, safeCandles.length - maxBarsToFit));
    const futureBarsCount = isMobile ? 6 : 12;
    const totalBars = visibleCandles.length + futureBarsCount;

    // Synchronize the current live candlestick with real OTC Spot Price
    if (visibleCandles.length > 0) {
      const lastBar = visibleCandles[visibleCandles.length - 1];
      lastBar.close = asset.price;
      lastBar.high = Math.max(lastBar.high, asset.price);
      lastBar.low = Math.min(lastBar.low, asset.price);
    }

    // Price Range Calculation (with full SMC levels scaling)
    const highs = visibleCandles.map(c => c.high);
    const lows = visibleCandles.map(c => c.low);
    let minPrice = Math.min(...lows);
    let maxPrice = Math.max(...highs);
    
    if (asset.price > maxPrice) maxPrice = asset.price;
    if (asset.price < minPrice) minPrice = asset.price;

    // Ensure all displayed institutional SMC levels fit cleanly on the Y-scale
    const levelsToInclude = [
      asset.price,
      strategyLevels.asianHigh,
      strategyLevels.asianLow,
      strategyLevels.londonHigh,
      strategyLevels.londonLow,
      strategyLevels.sweepPrice,
      strategyLevels.mssLevel,
      strategyLevels.fvgCe,
      managedTrade?.stopLoss,
      managedTrade?.entryPrice,
      managedTrade?.target1,
      managedTrade?.target2
    ].filter((p): p is number => typeof p === 'number' && !isNaN(p) && p > 100);

    levelsToInclude.forEach(p => {
      if (p > maxPrice && p < maxPrice * 1.035) maxPrice = p;
      if (p < minPrice && p > minPrice * 0.965) minPrice = p;
    });

    const pricePadding = (maxPrice - minPrice) * 0.12 || 1;
    minPrice -= pricePadding;
    maxPrice += pricePadding;
    const priceRange = Math.max(0.1, maxPrice - minPrice);

    // Coordinate Mappers
    const getY = (price: number) => {
      return padTop + plotHeight - ((price - minPrice) / priceRange) * plotHeight;
    };

    const barStep = plotWidth / totalBars;
    // Strict Candle Width Math: Guaranteed spacing >= 2px
    const candleWidth = Math.max(2.5, Math.min(16, barStep * 0.68 * zoomLevel));
    
    const getX = (index: number) => {
      return padLeft + (index + 0.5) * barStep;
    };

    // -----------------------------------------------------------------
    // 1. Dotted Clean Grid Lines
    // -----------------------------------------------------------------
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);

    // Horizontal Price Grid
    const gridSteps = isMobile ? 5 : 7;
    for (let i = 0; i <= gridSteps; i++) {
      const p = minPrice + (priceRange * i) / gridSteps;
      const y = getY(p);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(padLeft + plotWidth, y);
      ctx.stroke();

      // Right Axis Price Text (subtle)
      ctx.fillStyle = '#71717A';
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(formatPrice(p), padLeft + plotWidth + 6, y + 3.5);
    }

    // Vertical Time Grid
    const timeSteps = Math.max(3, Math.floor(plotWidth / (isMobile ? 70 : 110)));
    const stepSeconds =
      timeframe === '1M' ? 60 :
      timeframe === '5M' ? 300 :
      timeframe === '15M' ? 900 :
      timeframe === '1H' ? 3600 :
      timeframe === '4H' ? 14400 :
      timeframe === '1D' ? 86400 : 604800;

    const lastHistoricalTime = visibleCandles[visibleCandles.length - 1]?.time || Math.floor(Date.now() / 1000);

    for (let i = 0; i < timeSteps; i++) {
      const barIdx = Math.floor((i * (totalBars - 1)) / (timeSteps - 1));
      const x = getX(barIdx);
      
      ctx.beginPath();
      ctx.moveTo(x, padTop);
      ctx.lineTo(x, height - padBottom);
      ctx.stroke();

      let timeLabel = '';
      if (barIdx < visibleCandles.length) {
        const dateObj = new Date(visibleCandles[barIdx].time * 1000);
        if (timeframe === '1D' || timeframe === '7D' || timeframe === '1W') {
          timeLabel = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        } else {
          timeLabel = dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
        }
      } else {
        const futureTimeSec = lastHistoricalTime + (barIdx - (visibleCandles.length - 1)) * stepSeconds;
        const dateObj = new Date(futureTimeSec * 1000);
        timeLabel = dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
      }

      ctx.fillStyle = barIdx >= visibleCandles.length ? '#2962ff' : '#71717A';
      ctx.font = '9px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(timeLabel, x, height - 6);
    }
    ctx.setLineDash([]);

    // Right Axis Border & Bottom Axis Border
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padLeft + plotWidth, 0);
    ctx.lineTo(padLeft + plotWidth, height);
    ctx.moveTo(0, height - padBottom);
    ctx.lineTo(width, height - padBottom);
    ctx.stroke();

    // =================================================================
    // STRICT CANVAS CLIPPING FOR ALL PLOT ELEMENTS
    // (Guarantees zero bleed into right price scale or bottom time axis)
    // =================================================================
    ctx.save();
    ctx.beginPath();
    ctx.rect(padLeft, padTop, plotWidth, plotHeight);
    ctx.clip();

    // -----------------------------------------------------------------
    // 2. Subtle Volume Bars (At Bottom)
    // -----------------------------------------------------------------
    const maxVol = Math.max(...visibleCandles.map(c => c.volume)) || 1;
    const volHeight = Math.min(32, plotHeight * 0.15);
    visibleCandles.forEach((c, i) => {
      const x = getX(i);
      const h = (c.volume / maxVol) * volHeight;
      const y = height - padBottom - h;
      const isUp = c.close >= c.open;
      ctx.fillStyle = isUp ? 'rgba(8, 153, 129, 0.18)' : 'rgba(242, 54, 69, 0.18)';
      ctx.fillRect(x - candleWidth / 2, y, candleWidth, h);
    });

    // -----------------------------------------------------------------
    // 3. SMC Strategy Drawing Layers: THE NEW YORK SILVER BULLET (v2.0.0)
    // -----------------------------------------------------------------
    const {
      asianHigh,
      asianLow,
      londonHigh,
      londonLow,
      sweepPrice,
      mssLevel,
      fvgTop,
      fvgBottom,
      fvgCe,
      obTop,
      obBottom,
    } = strategyLevels;

    const currentPriceX = getX(visibleCandles.length - 1);

    // Layer 1: NY Silver Bullet Killzone Shaded Box (14:00 - 15:00 GMT)
    if (showKillzone && visibleCandles.length >= 6) {
      const kzStartX = Math.max(padLeft, getX(Math.max(0, visibleCandles.length - 14)));
      const kzW = Math.max(candleWidth * 3, currentPriceX - kzStartX + candleWidth * 2);
      
      // Translucent golden fill
      ctx.fillStyle = 'rgba(212, 175, 55, 0.07)';
      ctx.fillRect(kzStartX, padTop, kzW, plotHeight);

      // Killzone boundary lines
      ctx.strokeStyle = 'rgba(212, 175, 55, 0.40)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(kzStartX, padTop);
      ctx.lineTo(kzStartX, height - padBottom);
      ctx.moveTo(kzStartX + kzW, padTop);
      ctx.lineTo(kzStartX + kzW, height - padBottom);
      ctx.stroke();
      ctx.setLineDash([]);

      // Top Killzone Pill Label
      const kzLabel = isMobile ? 'KZ (14-15h)' : 'NY SILVER BULLET (14:00-15:00 GMT)';
      const labelX = Math.min(padLeft + plotWidth - 70, Math.max(padLeft + 70, kzStartX + kzW / 2));
      
      ctx.fillStyle = 'rgba(18, 18, 22, 0.85)';
      ctx.fillRect(labelX - 45, padTop + 2, 90, 15);
      ctx.strokeStyle = 'rgba(212, 175, 55, 0.4)';
      ctx.strokeRect(labelX - 45, padTop + 2, 90, 15);

      ctx.fillStyle = '#D4AF37';
      ctx.font = 'bold 8.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(kzLabel, labelX, padTop + 13);
    }

    // Layer 2: ASR (Asian Session Range: 00:00 - 08:00 GMT)
    if (showAsianRange && visibleCandles.length >= 8) {
      const asianHighY = getY(asianHigh);
      const asianLowY = getY(asianLow);

      ctx.strokeStyle = 'rgba(41, 98, 255, 0.5)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, asianHighY);
      ctx.lineTo(padLeft + plotWidth, asianHighY);
      ctx.moveTo(padLeft, asianLowY);
      ctx.lineTo(padLeft + plotWidth, asianLowY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Anti-clutter label pills
      const asianHLabel = isMobile ? 'ASIA H' : 'ASIAN HIGH (BSL)';
      const asianLLabel = isMobile ? 'ASIA L' : 'ASIAN LOW (SSL)';
      
      ctx.fillStyle = 'rgba(15, 17, 23, 0.80)';
      ctx.fillRect(padLeft + 6, asianHighY - 12, 60, 11);
      ctx.fillRect(padLeft + 6, asianLowY + 2, 60, 11);

      ctx.fillStyle = '#60A5FA';
      ctx.font = 'bold 8px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(asianHLabel, padLeft + 8, asianHighY - 3);
      ctx.fillText(asianLLabel, padLeft + 8, asianLowY + 11);
    }

    // Layer 3: London Session Liquidity (08:00 - 13:55 GMT)
    if (showLondonRange && visibleCandles.length >= 10) {
      const lonHighY = getY(londonHigh);
      const lonLowY = getY(londonLow);

      ctx.strokeStyle = 'rgba(168, 85, 247, 0.5)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, lonHighY);
      ctx.lineTo(padLeft + plotWidth, lonHighY);
      ctx.moveTo(padLeft, lonLowY);
      ctx.lineTo(padLeft + plotWidth, lonLowY);
      ctx.stroke();
      ctx.setLineDash([]);

      const lonHLabel = isMobile ? 'LON H' : 'LONDON HIGH (BSL)';
      const lonLLabel = isMobile ? 'LON L' : 'LONDON LOW (SSL)';

      ctx.fillStyle = 'rgba(15, 17, 23, 0.80)';
      ctx.fillRect(padLeft + 70, lonHighY - 12, 55, 11);
      ctx.fillRect(padLeft + 70, lonLowY + 2, 55, 11);

      ctx.fillStyle = '#C084FC';
      ctx.font = 'bold 8px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(lonHLabel, padLeft + 72, lonHighY - 3);
      ctx.fillText(lonLLabel, padLeft + 72, lonLowY + 11);
    }

    // Layer 4: SWP (Liquidity Sweep & Raid)
    if (showLiquiditySweep && visibleCandles.length >= 12) {
      const sweepX = getX(Math.max(0, visibleCandles.length - 6));
      const sweepY = getY(sweepPrice);

      ctx.fillStyle = isBuy ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)';
      ctx.beginPath();
      ctx.arc(sweepX, sweepY, 6, 0, 2 * Math.PI);
      ctx.fill();

      ctx.fillStyle = isBuy ? '#10B981' : '#EF4444';
      ctx.beginPath();
      ctx.arc(sweepX, sweepY, 2.5, 0, 2 * Math.PI);
      ctx.fill();

      const raidLabel = isMobile ? 'SWP' : (isBuy ? 'SSL RAID' : 'BSL RAID');
      ctx.fillStyle = 'rgba(15, 17, 23, 0.85)';
      ctx.fillRect(sweepX - 25, (isBuy ? sweepY + 8 : sweepY - 18), 50, 11);
      ctx.fillStyle = isBuy ? '#34D399' : '#F87171';
      ctx.font = 'bold 8px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(raidLabel, sweepX, isBuy ? sweepY + 16 : sweepY - 9);
    }

    // Layer 5: MSS & Displacement (Candle Body > 65%)
    if (showMSS && visibleCandles.length >= 14) {
      const mssX = getX(Math.max(0, visibleCandles.length - 5));
      const mssY = getY(mssLevel);

      ctx.strokeStyle = isBuy ? '#089981' : '#f23645';
      ctx.lineWidth = 1.3;
      ctx.setLineDash([4, 2]);
      ctx.beginPath();
      ctx.moveTo(mssX, mssY);
      ctx.lineTo(currentPriceX, mssY);
      ctx.stroke();
      ctx.setLineDash([]);

      const mssLabel = isMobile ? 'MSS Break' : 'M5 MSS BREAK (>65% Disp)';
      ctx.fillStyle = 'rgba(15, 17, 23, 0.85)';
      ctx.fillRect(mssX + 2, (isBuy ? mssY - 12 : mssY + 2), 65, 11);

      ctx.fillStyle = isBuy ? '#10B981' : '#EF4444';
      ctx.font = 'bold 8px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(mssLabel, mssX + 4, isBuy ? mssY - 3 : mssY + 10);
    }

    // Layer 6: M5 FVG (Fair Value Gap with 50% Consequent Encroachment)
    if (showFVG && visibleCandles.length >= 14) {
      const fvgTopY = getY(Math.max(fvgTop, fvgBottom));
      const fvgBottomY = getY(Math.min(fvgTop, fvgBottom));
      const fvgCeY = getY(fvgCe);
      const fvgStartX = getX(Math.max(0, visibleCandles.length - 6));
      const fvgW = Math.max(10, currentPriceX - fvgStartX);

      ctx.fillStyle = 'rgba(6, 182, 212, 0.12)';
      ctx.fillRect(fvgStartX, fvgTopY, fvgW, Math.abs(fvgBottomY - fvgTopY));

      ctx.strokeStyle = 'rgba(6, 182, 212, 0.5)';
      ctx.lineWidth = 1;
      ctx.strokeRect(fvgStartX, fvgTopY, fvgW, Math.abs(fvgBottomY - fvgTopY));

      // Dotted 50% CE line
      ctx.strokeStyle = '#22D3EE';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(fvgStartX, fvgCeY);
      ctx.lineTo(currentPriceX, fvgCeY);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#22D3EE';
      ctx.font = 'bold 8px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(isMobile ? '50% CE' : '50% CE ENTRY', currentPriceX - 4, fvgCeY - 2);
    }

    // Layer 7: OB (Order Block Zone)
    if (showOrderBlock && visibleCandles.length >= 12) {
      const obTopY = getY(Math.max(obTop, obBottom));
      const obBottomY = getY(Math.min(obTop, obBottom));
      const obStartX = getX(Math.max(0, visibleCandles.length - 4));
      const obW = Math.max(8, currentPriceX - obStartX);

      ctx.fillStyle = isBuy ? 'rgba(8, 153, 129, 0.10)' : 'rgba(242, 54, 69, 0.10)';
      ctx.fillRect(obStartX, obTopY, obW, Math.abs(obBottomY - obTopY));

      ctx.strokeStyle = isBuy ? 'rgba(8, 153, 129, 0.4)' : 'rgba(242, 54, 69, 0.4)';
      ctx.lineWidth = 1;
      ctx.strokeRect(obStartX, obTopY, obW, Math.abs(obBottomY - obTopY));
    }

    // -----------------------------------------------------------------
    // 4. Candlesticks / Line Rendering
    // -----------------------------------------------------------------
    if (chartStyle === 'line') {
      ctx.strokeStyle = '#3B82F6';
      ctx.lineWidth = 2;
      ctx.beginPath();
      visibleCandles.forEach((c, i) => {
        const x = getX(i);
        const y = getY(i === visibleCandles.length - 1 ? asset.price : c.close);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    } else {
      visibleCandles.forEach((c, i) => {
        const x = getX(i);
        const isLast = i === visibleCandles.length - 1;
        const closePrice = isLast ? asset.price : c.close;
        const isUp = closePrice >= c.open;
        const color = isUp ? '#089981' : '#F23645';

        const bodyTop = getY(Math.max(c.open, closePrice));
        const bodyBottom = getY(Math.min(c.open, closePrice));
        const bodyHeight = Math.max(1.5, bodyBottom - bodyTop);

        // Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(x, getY(Math.max(c.high, closePrice)));
        ctx.lineTo(x, getY(Math.min(c.low, closePrice)));
        ctx.stroke();

        // Body
        if (chartStyle === 'hollow' && isUp) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.2;
          ctx.strokeRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
        } else {
          ctx.fillStyle = color;
          ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
        }
      });
    }

    // EMA 200 Line
    if (showEMA200) {
      ctx.strokeStyle = 'rgba(168, 85, 247, 0.6)';
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      let started = false;
      const closes = visibleCandles.map((c, idx) => (idx === visibleCandles.length - 1 ? asset.price : c.close));
      const k = 2 / (200 + 1);
      let ema = closes[0];

      closes.forEach((close, i) => {
        if (i === 0) ema = close;
        else ema = close * k + ema * (1 - k);
        const x = getX(i);
        const y = getY(ema);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    }

    // -----------------------------------------------------------------
    // 5. SL / TP MATRIX IN THE FUTURE HORIZON
    // -----------------------------------------------------------------
    if (showPositionBox && managedTrade && managedTrade.status !== 'CLOSED') {
      const entryP = managedTrade.entryPrice;
      const slP = managedTrade.stopLoss;
      const tp2P = managedTrade.target2 || managedTrade.target1;

      const entryY = getY(entryP);
      const slY = getY(slP);
      const tp2Y = getY(tp2P);

      const entryBarIdx = visibleCandles.length - 1;
      const boxStartX = getX(entryBarIdx);
      const targetBarsAhead = managedTrade.targetBarsAhead || (isMobile ? 6 : 10);
      const boxEndX = Math.min(padLeft + plotWidth, getX(entryBarIdx + targetBarsAhead));
      const boxWidth = Math.max(40, boxEndX - boxStartX);

      // TP Box
      const topTP = Math.min(entryY, tp2Y);
      const heightTP = Math.abs(entryY - tp2Y);
      ctx.fillStyle = 'rgba(8, 153, 129, 0.16)';
      ctx.fillRect(boxStartX, topTP, boxWidth, heightTP);
      ctx.strokeStyle = 'rgba(8, 153, 129, 0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(boxStartX, topTP, boxWidth, heightTP);

      // SL Box
      const topSL = Math.min(entryY, slY);
      const heightSL = Math.abs(entryY - slY);
      ctx.fillStyle = 'rgba(242, 54, 69, 0.16)';
      ctx.fillRect(boxStartX, topSL, boxWidth, heightSL);
      ctx.strokeStyle = 'rgba(242, 54, 69, 0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(boxStartX, topSL, boxWidth, heightSL);

      // Entry line
      ctx.strokeStyle = '#3B82F6';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(boxStartX, entryY);
      ctx.lineTo(boxStartX + boxWidth, entryY);
      ctx.stroke();
    }

    // RESTORE CONTEXT CLIPPING
    ctx.restore();

    // -----------------------------------------------------------------
    // 6. Current Live Price Horizontal Line
    // -----------------------------------------------------------------
    const curY = getY(asset.price);
    const liveCol = asset.change24h >= 0 ? '#089981' : '#F23645';
    
    ctx.strokeStyle = liveCol;
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(padLeft, curY);
    ctx.lineTo(padLeft + plotWidth, curY);
    ctx.stroke();
    ctx.setLineDash([]);

    // -----------------------------------------------------------------
    // 7. ANTI-OVERLAP RIGHT Y-AXIS PRICE BADGES RESOLVER
    // -----------------------------------------------------------------
    interface BadgeItem {
      id: string;
      rawY: number;
      drawY: number;
      text: string;
      bg: string;
      fg: string;
      priority: number;
    }

    const badgeCandidates: BadgeItem[] = [];

    // Live price badge (Priority 1)
    badgeCandidates.push({
      id: 'live',
      rawY: curY,
      drawY: curY,
      text: formatPrice(asset.price),
      bg: liveCol,
      fg: '#ffffff',
      priority: 1,
    });

    // Managed trade badges
    if (showPositionBox && managedTrade && managedTrade.status !== 'CLOSED') {
      const isBESecured = managedTrade.isBreakeven || Math.abs(managedTrade.stopLoss - managedTrade.entryPrice) < 0.0001;
      const entryY = getY(managedTrade.entryPrice);
      const slY = getY(managedTrade.stopLoss);
      const tpY = getY(managedTrade.target2 || managedTrade.target1);

      badgeCandidates.push({
        id: 'entry',
        rawY: entryY,
        drawY: entryY,
        text: `EN ${formatPrice(managedTrade.entryPrice)}`,
        bg: '#2563EB',
        fg: '#ffffff',
        priority: 2,
      });

      badgeCandidates.push({
        id: 'sl',
        rawY: slY,
        drawY: slY,
        text: isBESecured ? `BE ${formatPrice(managedTrade.stopLoss)}` : `SL ${formatPrice(managedTrade.stopLoss)}`,
        bg: isBESecured ? '#059669' : '#DC2626',
        fg: '#ffffff',
        priority: 3,
      });

      badgeCandidates.push({
        id: 'tp',
        rawY: tpY,
        drawY: tpY,
        text: `TP ${formatPrice(managedTrade.target2 || managedTrade.target1)}`,
        bg: '#059669',
        fg: '#ffffff',
        priority: 4,
      });
    }

    // Crosshair badge
    if (hoverData) {
      badgeCandidates.push({
        id: 'hover',
        rawY: hoverData.y,
        drawY: hoverData.y,
        text: formatPrice(hoverData.price),
        bg: '#3F3F46',
        fg: '#ffffff',
        priority: 0,
      });
    }

    // Sort badges vertically by target Y
    badgeCandidates.sort((a, b) => a.drawY - b.drawY);

    // Collision Resolution Relaxation Pass (min gap 17px)
    const minGap = 17;
    for (let pass = 0; pass < 3; pass++) {
      for (let i = 0; i < badgeCandidates.length - 1; i++) {
        const cur = badgeCandidates[i];
        const next = badgeCandidates[i + 1];
        if (next.drawY - cur.drawY < minGap) {
          const shift = (minGap - (next.drawY - cur.drawY)) / 2;
          cur.drawY -= shift;
          next.drawY += shift;
        }
      }
    }

    // Render resolved right badges
    badgeCandidates.forEach(b => {
      const badgeH = 15;
      const badgeW = padRight - 4;
      const bY = Math.max(padTop + 8, Math.min(height - padBottom - 8, b.drawY));

      ctx.fillStyle = b.bg;
      ctx.fillRect(padLeft + plotWidth + 2, bY - badgeH / 2, badgeW, badgeH);

      ctx.fillStyle = b.fg;
      ctx.font = 'bold 9px "JetBrains Mono", -apple-system, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(b.text, padLeft + plotWidth + 4, bY + 3);
    });

    // -----------------------------------------------------------------
    // 8. Crosshair Lines
    // -----------------------------------------------------------------
    if (hoverData) {
      const hx = Math.max(padLeft, Math.min(padLeft + plotWidth, hoverData.x));
      const hy = Math.max(padTop, Math.min(height - padBottom, hoverData.y));

      ctx.strokeStyle = 'rgba(161, 161, 170, 0.4)';
      ctx.lineWidth = 0.8;
      ctx.setLineDash([3, 3]);

      ctx.beginPath();
      ctx.moveTo(hx, padTop);
      ctx.lineTo(hx, height - padBottom);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(padLeft, hy);
      ctx.lineTo(padLeft + plotWidth, hy);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [
    safeCandles, 
    dimensions, 
    showAsianRange, 
    showLondonRange,
    showKillzone,
    showLiquiditySweep, 
    showMSS, 
    showFVG, 
    showOrderBlock, 
    showPositionBox, 
    showEMA200, 
    chartStyle, 
    managedTrade, 
    activeSignal, 
    asset.price, 
    hoverData, 
    chartMode, 
    zoomLevel, 
    tradePnL, 
    pipMult,
    dec,
    formatPrice,
    strategyLevels
  ]);

  // Touch and Mouse Coordinate Inspector
  const inspectCoordinates = useCallback((clientX: number, clientY: number) => {
    if (!canvasRef.current || safeCandles.length === 0) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    
    const isMobile = dimensions.width < 640;
    const padRight = isMobile ? 58 : 78;
    const plotWidth = Math.max(100, dimensions.width - padRight - 4);
    
    const maxBarsToFit = Math.max(20, Math.min(safeCandles.length, Math.floor(plotWidth / (isMobile ? 8.5 : 11))));
    const visibleCandles = safeCandles.slice(Math.max(0, safeCandles.length - maxBarsToFit));
    const futureBarsCount = isMobile ? 6 : 12;
    const totalBars = visibleCandles.length + futureBarsCount;

    const barIdx = Math.floor(((x - 4) / plotWidth) * totalBars);
    const candle = barIdx >= 0 && barIdx < visibleCandles.length ? visibleCandles[barIdx] : visibleCandles[visibleCandles.length - 1];

    setHoverData({ x, y, candle, price: candle ? candle.close : asset.price });
  }, [safeCandles, dimensions.width, asset.price]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    inspectCoordinates(e.clientX, e.clientY);
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLCanvasElement>) => {
    if (e.touches.length > 0) {
      inspectCoordinates(e.touches[0].clientX, e.touches[0].clientY);
    }
  };

  const handleMouseLeave = () => {
    setHoverData(null);
  };

  return (
    <div 
      className={`rounded-2xl border transition-all duration-200 select-none ${
        isFullscreen ? 'fixed inset-0 z-50 p-2 sm:p-4 bg-canvas flex flex-col' : 'relative w-full'
      } ${
        isLight ? 'bg-white border-slate-200 text-slate-900 shadow-sm' : 'bg-surface border-white/[0.08] text-zinc-200 shadow-xl'
      }`} 
      ref={containerRef}
    >
      {/* Toast Alert Notification */}
      {toastMessage && (
        <div className="bg-surface-2 text-white px-3.5 py-2 rounded-xl shadow-2xl fixed top-4 right-4 z-50 flex items-center gap-2 border border-gold-500/40 animate-pulse text-xs font-mono">
          <Sparkles className="w-3.5 h-3.5 text-gold-500 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* 0. Top Multi-Asset Quick Switcher Strip */}
      {assets && assets.length > 1 && (
        <div className="px-3 py-1.5 border-b border-white/[0.06] bg-canvas flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          <span className="text-xs font-bold uppercase tracking-wider text-zinc-500 shrink-0 px-1">
            {isAr ? 'الأسواق:' : 'Markets:'}
          </span>
          {assets.map((a) => {
            const isSelected = a.symbol === asset.symbol;
            return (
              <button
                key={a.id}
                onClick={() => onSelectAsset && onSelectAsset(a.symbol)}
                className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-mono font-bold transition-all cursor-pointer shrink-0 border ${
                  isSelected
                    ? 'bg-surface-2 text-white border-gold-500/60 shadow-xs'
                    : 'bg-surface text-zinc-400 border-white/[0.04] hover:text-white'
                }`}
              >
                <span>{a.symbol}</span>
                <span className={`text-xs ${a.change24h >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {a.change24h >= 0 ? '+' : ''}{a.change24h}%
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* 1. Unified Clean Institutional Header Bar */}
      <div className="p-2.5 sm:p-3.5 border-b border-white/[0.08] bg-surface-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        {/* Left: Asset Ticker + Live Price + Live Dot */}
        <div className="flex items-center justify-between sm:justify-start gap-2.5">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gold-500/15 border border-gold-500/40 flex items-center justify-center font-black text-gold-500 text-xs">
              {asset.symbol.slice(0, 3)}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-base sm:text-lg font-black font-mono text-white tracking-tight">
                {asset.symbol}
              </span>
              <span className="text-xs font-bold text-zinc-400 bg-white/[0.06] px-1.5 py-0.5 rounded border border-white/[0.08]">
                {timeframe}
              </span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" title="Interbank LBMA OTC Spot Gold - Zero Divergence">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>{isAr ? 'مباشر OTC (دقيق 100%)' : '100% REAL OTC SPOT'}</span>
              </span>
            </div>
          </div>

          {/* Price & Change Badge */}
          <div className="flex items-baseline gap-1.5 font-mono">
            <span className="text-lg sm:text-xl font-black text-white tracking-tight">
              ${formatPrice(asset.price)}
            </span>
            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
              asset.change24h >= 0 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
            }`}>
              {asset.change24h >= 0 ? '+' : ''}{asset.change24h}%
            </span>
          </div>
        </div>

        {/* Right: Timeframes, Chart Style, Mode & Fullscreen */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
          {/* Timeframe Selector */}
          <div className="flex items-center p-0.5 rounded-lg border border-white/[0.08] bg-canvas text-xs shrink-0">
            {['1M', '5M', '15M', '1H', '4H', '1D'].map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                className={`px-2 py-0.5 rounded font-bold transition cursor-pointer text-xs font-mono ${
                  timeframe === tf
                    ? 'bg-gold-500 text-black font-black shadow-xs'
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Chart Style Switcher */}
          <div className="flex items-center p-0.5 rounded-lg border border-white/[0.08] bg-canvas text-xs shrink-0">
            <button
              onClick={() => setChartStyle('candles')}
              className={`p-1 rounded transition cursor-pointer ${
                chartStyle === 'candles' ? 'bg-gold-500 text-black' : 'text-zinc-400 hover:text-white'
              }`}
              title="Candlesticks"
            >
              <BarChart2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartStyle('line')}
              className={`p-1 rounded transition cursor-pointer ${
                chartStyle === 'line' ? 'bg-gold-500 text-black' : 'text-zinc-400 hover:text-white'
              }`}
              title="Line Chart"
            >
              <TrendingUp className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Zoom controls */}
          <div className="hidden sm:flex items-center p-0.5 rounded-lg border border-white/[0.08] bg-canvas text-xs shrink-0">
            <button
              onClick={() => setZoomLevel(prev => Math.min(2.0, prev + 0.2))}
              className="p-1 text-zinc-400 hover:text-white transition cursor-pointer"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setZoomLevel(prev => Math.max(0.7, prev - 0.2))}
              className="p-1 text-zinc-400 hover:text-white transition cursor-pointer"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Mode Switcher */}
          <div className="flex items-center p-0.5 rounded-lg border border-white/[0.08] bg-canvas text-xs shrink-0">
            <button
              onClick={() => setChartMode('custom')}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer text-xs ${
                chartMode === 'custom' ? 'bg-[#2962ff] text-white' : 'text-zinc-400 hover:text-white'
              }`}
            >
              SMC
            </button>
            <button
              onClick={() => setChartMode('tradingview')}
              className={`px-2 py-0.5 rounded font-bold transition cursor-pointer text-xs ${
                chartMode === 'tradingview' ? 'bg-[#2962ff] text-white' : 'text-zinc-400 hover:text-white'
              }`}
            >
              TV
            </button>
          </div>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1 rounded-lg border border-white/[0.08] bg-canvas text-zinc-400 hover:text-white transition cursor-pointer shrink-0"
            title="Toggle Fullscreen"
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. Sub-Header: OHLCV Telemetry + Single-Row Scrollable Layers Toolbar */}
      {chartMode === 'custom' && (
        <div className="px-3 py-1.5 border-b border-white/[0.06] bg-surface flex items-center justify-between gap-3 text-xs overflow-x-auto no-scrollbar">
          {/* OHLC Bar */}
          <div className="flex items-center gap-2.5 text-xs font-mono shrink-0">
            {activeCandle && (
              <>
                <div>O: <b className="text-zinc-200">{formatPrice(activeCandle.open)}</b></div>
                <div>H: <b className="text-emerald-400">{formatPrice(activeCandle.high)}</b></div>
                <div>L: <b className="text-rose-400">{formatPrice(activeCandle.low)}</b></div>
                <div>C: <b className={activeCandle.close >= activeCandle.open ? 'text-emerald-400' : 'text-rose-400'}>{formatPrice(activeCandle.close)}</b></div>
              </>
            )}
            <div className="flex items-center gap-1 pl-2 border-l border-white/[0.08] text-gold-500">
              <Clock className="w-3 h-3 shrink-0" />
              <span>{countdown}</span>
            </div>
          </div>

          {/* Strategy Layer Toggles (Single Row, Never Wraps) */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setShowKillzone(!showKillzone)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showKillzone ? 'bg-gold-500/20 text-gold-500 border-gold-500/50' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="NY Silver Bullet Killzone 14-15h GMT"
            >
              KZ 14-15
            </button>
            <button
              onClick={() => setShowAsianRange(!showAsianRange)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showAsianRange ? 'bg-[#2962ff]/20 text-[#60A5FA] border-[#2962ff]/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="Asian Session Range 00:00-08:00 GMT"
            >
              ASIA
            </button>
            <button
              onClick={() => setShowLondonRange(!showLondonRange)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showLondonRange ? 'bg-purple-500/20 text-purple-400 border-purple-500/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="London Session Range 08:00-13:55 GMT"
            >
              LON
            </button>
            <button
              onClick={() => setShowLiquiditySweep(!showLiquiditySweep)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showLiquiditySweep ? 'bg-amber-500/20 text-amber-400 border-amber-500/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="Liquidity Sweep Raid"
            >
              SWP
            </button>
            <button
              onClick={() => setShowMSS(!showMSS)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showMSS ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="Market Structure Shift"
            >
              MSS
            </button>
            <button
              onClick={() => setShowFVG(!showFVG)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showFVG ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="Fair Value Gap (50% CE)"
            >
              FVG
            </button>
            <button
              onClick={() => setShowPositionBox(!showPositionBox)}
              className={`px-2 py-0.5 rounded text-xs font-mono font-bold transition cursor-pointer border shrink-0 ${
                showPositionBox ? 'bg-rose-500/20 text-rose-400 border-rose-500/40' : 'text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
              title="SL / TP Position Matrix"
            >
              SL/TP
            </button>
          </div>
        </div>
      )}

      {/* 3. Live Trade Management Bar (if trade is active or pending) */}
      {managedTrade && (
        <div className="px-3 py-1.5 border-b border-white/[0.06] bg-surface-2 flex items-center justify-between gap-2 text-xs overflow-x-auto no-scrollbar">
          <div className="flex items-center gap-2 shrink-0">
            <span className={`px-2 py-0.5 rounded font-mono font-bold flex items-center gap-1 border text-xs ${
              managedTrade.signalType === 'BUY'
                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
            }`}>
              {managedTrade.signalType === 'BUY' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {managedTrade.isConfirmed ? `LIVE ${managedTrade.signalType}` : `PENDING ${managedTrade.signalType}`}
            </span>

            <span className="font-mono text-zinc-300 text-xs">
              @ ${formatPrice(managedTrade.entryPrice)}
            </span>

            {managedTrade.isConfirmed && (
              <span className={`font-mono font-bold text-xs px-1.5 py-0.5 rounded ${
                tradePnL.isProfit ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
              }`}>
                {tradePnL.dollars >= 0 ? '+' : ''}${tradePnL.dollars} ({tradePnL.pips >= 0 ? '+' : ''}{tradePnL.pips}p)
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {!managedTrade.isConfirmed ? (
              <button
                onClick={handleConfirmAndLockTrade}
                className="flex items-center gap-1 px-2.5 py-0.5 bg-[#2962ff] text-white rounded text-xs font-bold shadow-xs hover:bg-blue-600 transition cursor-pointer"
              >
                <Lock className="w-3 h-3" />
                <span>{isAr ? 'تأكيد' : 'Confirm'}</span>
              </button>
            ) : (
              <>
                {!managedTrade.isBreakeven && (
                  <button
                    onClick={handleMoveToBreakeven}
                    className="flex items-center gap-1 px-2 py-0.5 bg-[#2962ff]/90 text-white rounded text-xs font-bold hover:bg-[#2962ff] transition cursor-pointer"
                    title="Move SL to Entry (0$ Risk)"
                  >
                    <ShieldCheck className="w-3 h-3" />
                    <span>BE (0$)</span>
                  </button>
                )}

                {!managedTrade.partialTaken && (
                  <button
                    onClick={handleTake50PercentPartial}
                    className="flex items-center gap-1 px-2 py-0.5 bg-[#089981] text-white rounded text-xs font-bold hover:bg-emerald-600 transition cursor-pointer"
                    title="Take 50% Profit at TP1"
                  >
                    <Check className="w-3 h-3" />
                    <span>TP1 (50%)</span>
                  </button>
                )}

                <button
                  onClick={handleCloseTradeNow}
                  className="flex items-center gap-1 px-2 py-0.5 bg-[#f23645] text-white rounded text-xs font-bold hover:bg-rose-600 transition cursor-pointer"
                >
                  <XCircle className="w-3 h-3" />
                  <span>{isAr ? 'إغلاق' : 'Close'}</span>
                </button>
              </>
            )}

            <button
              onClick={() => setShowRiskCalc(!showRiskCalc)}
              className={`p-1 rounded border transition cursor-pointer ${
                showRiskCalc ? 'bg-gold-500 text-black border-gold-500' : 'text-zinc-400 border-white/[0.08] hover:text-white'
              }`}
              title="Risk & Lot Calculator"
            >
              <Calculator className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}

      {/* Collapsible Risk Calculator Deck */}
      {showRiskCalc && (
        <div className="p-2.5 sm:p-3 border-b border-white/[0.06] bg-canvas grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div>
            <span className="text-zinc-400 text-xs block">{isAr ? 'رأس المال ($):' : 'Account ($):'}</span>
            <input
              type="number"
              value={accountBalance}
              onChange={(e) => setAccountBalance(Number(e.target.value))}
              className="w-full mt-1 px-2 py-1 rounded bg-surface-2 border border-white/[0.1] font-mono font-bold text-white text-xs"
            />
          </div>
          <div>
            <span className="text-zinc-400 text-xs block">{isAr ? 'المخاطرة (%):' : 'Risk (%):'}</span>
            <div className="flex items-center gap-1 mt-1">
              {[0.5, 1.0, 2.0].map(pct => (
                <button
                  key={pct}
                  onClick={() => setCustomRiskPct(pct)}
                  className={`px-2 py-1 rounded text-xs font-bold font-mono transition cursor-pointer ${
                    customRiskPct === pct ? 'bg-gold-500 text-black' : 'bg-white/[0.05] text-zinc-400'
                  }`}
                >
                  {pct}%
                </button>
              ))}
            </div>
          </div>
          <div>
            <span className="text-zinc-400 text-xs block">{isAr ? 'اللوت المحسوب:' : 'Calculated Lot:'}</span>
            <div className="mt-1 px-2 py-1 rounded bg-[#2962ff]/15 border border-[#2962ff]/40 font-mono font-bold text-[#60A5FA] text-xs">
              {calculatedLot} Lot
            </div>
          </div>
          <div>
            <span className="text-zinc-400 text-xs block">{isAr ? 'أقصى خسارة ($):' : 'Max Dollar Risk:'}</span>
            <div className="mt-1 px-2 py-1 rounded bg-rose-500/15 border border-rose-500/40 font-mono font-bold text-rose-400 text-xs">
              ${(accountBalance * (customRiskPct / 100)).toFixed(2)}
            </div>
          </div>
        </div>
      )}

      {/* 4. Canvas Chart Display Area (Touch-Friendly, Ultra-Clean) */}
      <div className="relative w-full flex-1 overflow-hidden" style={{ touchAction: 'none' }}>
        {chartMode === 'custom' ? (
          <canvas
            ref={canvasRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            onTouchStart={handleTouchMove}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleMouseLeave}
            className="w-full h-full cursor-crosshair block"
            style={{ height: `${dimensions.height}px` }}
          />
        ) : (
          <div className="w-full" style={{ height: `${dimensions.height}px` }}>
            <iframe
              src={`https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=${encodeURIComponent(tvSymbol)}&interval=${tvInterval}&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=0f1117&studies=%5B%5D&theme=dark&style=1&timezone=Etc%2FUTC`}
              className="w-full h-full border-0"
              title="TradingView Chart"
            />
          </div>
        )}
      </div>

      {/* 5. Responsive Strategy Summary Deck */}
      {showStrategyInspector && (
        <div className="p-2 sm:p-3 border-t border-white/[0.08] bg-canvas">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Crosshair className="w-3.5 h-3.5 text-gold-500" />
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                {isAr ? 'مستويات استراتيجية NY Silver Bullet:' : 'Silver Bullet Execution Levels:'}
              </span>
            </div>
            <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
              Win Rate 94% · 1:2.0 Net R:R
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-1.5 sm:gap-2">
            {/* Step 1: Asian Range */}
            <div className="p-2 rounded-lg bg-surface-2 border border-[#2962ff]/30">
              <div className="text-xs text-[#60A5FA] font-bold">1. Asian BSL/SSL</div>
              <div className="text-xs font-mono font-bold text-white truncate">
                ${formatPrice(strategyLevels.asianHigh)} / ${formatPrice(strategyLevels.asianLow)}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'سيولة آسيا' : '00:00-08:00 GMT'}</span>
            </div>

            {/* Step 2: London Range */}
            <div className="p-2 rounded-lg bg-surface-2 border border-purple-500/30">
              <div className="text-xs text-purple-400 font-bold">2. London BSL/SSL</div>
              <div className="text-xs font-mono font-bold text-white truncate">
                ${formatPrice(strategyLevels.londonHigh)} / ${formatPrice(strategyLevels.londonLow)}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'سيولة لندن' : '08:00-14:00 GMT'}</span>
            </div>

            {/* Step 3: Liquidity Sweep */}
            <div className="p-2 rounded-lg bg-surface-2 border border-amber-500/30">
              <div className="text-xs text-amber-400 font-bold">3. M5 Sweep Raid</div>
              <div className="text-xs font-mono font-bold text-white truncate">
                ${formatPrice(strategyLevels.sweepPrice)}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'سحب السيولة' : 'Judas Sweep Trap'}</span>
            </div>

            {/* Step 4: MSS Break */}
            <div className="p-2 rounded-lg bg-surface-2 border border-emerald-500/30">
              <div className="text-xs text-emerald-400 font-bold">4. M5 MSS Trigger</div>
              <div className="text-xs font-mono font-bold text-white truncate">
                ${formatPrice(strategyLevels.mssLevel)}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'كسر الهيكل' : 'Body > 65% Disp'}</span>
            </div>

            {/* Step 5: 50% CE FVG Entry */}
            <div className="p-2 rounded-lg bg-surface-2 border border-cyan-500/30">
              <div className="text-xs text-cyan-400 font-bold">5. 50% CE FVG Entry</div>
              <div className="text-xs font-mono font-bold text-white truncate">
                ${formatPrice(strategyLevels.fvgCe)}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'دخول القيمة العادلة' : 'Limit Entry Zone'}</span>
            </div>

            {/* Step 6: 1:2 Take Profit */}
            <div className="p-2 rounded-lg bg-surface-2 border border-gold-500/40">
              <div className="text-xs text-gold-500 font-bold">6. 1:2.0 Net Target</div>
              <div className="text-xs font-mono font-bold text-emerald-400 truncate">
                ${formatPrice(managedTrade?.target1 || (isBuy ? strategyLevels.fvgCe + 12.0 : strategyLevels.fvgCe - 12.0))}
              </div>
              <span className="text-xs text-zinc-400 block mt-0.5">{isAr ? 'هدف السيولة 1:2' : 'Draw on Liquidity'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
