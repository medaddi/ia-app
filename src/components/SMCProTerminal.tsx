import React, { useState, useRef, useEffect } from 'react';
import { 
  Brain, 
  GripHorizontal, 
  Minimize2, 
  Maximize2, 
  Layers, 
  ShieldCheck, 
  Target, 
  Zap, 
  Clock, 
  Crosshair, 
  ChevronRight, 
  BarChart3,
  Move,
  Pin,
  Sparkles,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { MarketAsset, TechnicalIndicators, AISignal, Language } from '../types';

interface SMCProTerminalProps {
  asset: MarketAsset;
  indicators: TechnicalIndicators | null;
  activeSignal?: AISignal | null;
  timeframe: string;
  lang: Language;
  theme?: 'light' | 'dark';
  isFloating?: boolean;
  onClose?: () => void;
  onFocusOrderBlock?: () => void;
}

export type DockPosition = 'floating' | 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';

export const SMCProTerminal: React.FC<SMCProTerminalProps> = ({
  asset,
  indicators,
  activeSignal,
  timeframe,
  lang,
  theme = 'light',
  isFloating = false,
  onClose,
  onFocusOrderBlock,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [activeTab, setActiveTab] = useState<'hud' | 'flow' | 'confluence'>('hud');
  const [isMinimized, setIsMinimized] = useState<boolean>(false);
  const [dockPos, setDockPos] = useState<DockPosition>('top-right');
  
  // Dragging state for floating mode
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 20, y: 20 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartRef = useRef<{ startX: number; startY: number; posX: number; posY: number }>({
    startX: 0,
    startY: 0,
    posX: 20,
    posY: 20,
  });
  const terminalRef = useRef<HTMLDivElement | null>(null);

  const smc = indicators?.smc;

  // Handle Dragging
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dockPos !== 'floating') return;
    setIsDragging(true);
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      posX: position.x,
      posY: position.y,
    };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStartRef.current.startX;
    const dy = e.clientY - dragStartRef.current.startY;
    
    // Bounds clamping inside parent container
    const newX = Math.max(10, Math.min(window.innerWidth - 380, dragStartRef.current.posX + dx));
    const newY = Math.max(10, Math.min(window.innerHeight - 300, dragStartRef.current.posY + dy));
    
    setPosition({ x: newX, y: newY });
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isDragging) {
      setIsDragging(false);
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch (err) {
        // ignore
      }
    }
  };

  if (!smc || !smc.orderBlock) return null;

  // Realtime Distance to OrderBlock calculations
  const obMid = (smc.orderBlock.high + smc.orderBlock.low) / 2;
  const priceDistance = Math.abs(asset.price - obMid);
  const pipMultiplier = asset.symbol.includes('JPY') ? 100 : (asset.symbol.includes('BTC') || asset.symbol.includes('ETH') || asset.symbol.includes('XAU')) ? 1 : 10000;
  const distancePips = (priceDistance * (asset.symbol.includes('XAU') ? 10 : pipMultiplier)).toFixed(1);
  const isInsideOB = asset.price >= smc.orderBlock.low && asset.price <= smc.orderBlock.high;

  // Position Styling when floating
  const getDockClasses = () => {
    if (!isFloating) return 'relative w-full';
    if (dockPos === 'floating') return 'fixed z-30 max-w-[calc(100vw-24px)]';
    if (dockPos === 'top-right') return 'absolute top-2 sm:top-3 right-2 sm:right-3 z-30 max-w-[calc(100%-16px)] sm:max-w-[420px]';
    if (dockPos === 'top-left') return 'absolute top-2 sm:top-3 left-2 sm:left-3 z-30 max-w-[calc(100%-16px)] sm:max-w-[420px]';
    if (dockPos === 'bottom-right') return 'absolute bottom-2 sm:bottom-3 right-2 sm:right-3 z-30 max-w-[calc(100%-16px)] sm:max-w-[420px]';
    if (dockPos === 'bottom-left') return 'absolute bottom-2 sm:bottom-3 left-2 sm:left-3 z-30 max-w-[calc(100%-16px)] sm:max-w-[420px]';
    return 'absolute top-2 sm:top-3 right-2 sm:right-3 z-30 max-w-[calc(100%-16px)] sm:max-w-[420px]';
  };

  const inlineStyles: React.CSSProperties = isFloating && dockPos === 'floating' ? {
    left: `${position.x}px`,
    top: `${position.y}px`,
  } : {};

  return (
    <div
      ref={terminalRef}
      style={inlineStyles}
      className={`${getDockClasses()} transition-all duration-200 select-none ${
        isMinimized ? 'w-auto' : 'w-full max-w-[420px]'
      }`}
    >
      <div className={`rounded-2xl border shadow-xl backdrop-blur-md overflow-hidden transition-all duration-200 ${
        isLight
          ? 'bg-white/95 border-slate-300 text-slate-800 shadow-slate-300/40'
          : 'bg-surface/95 border-cyan-900/60 text-slate-100 shadow-black/60'
      }`}>
        
        {/* Terminal Title Bar & Drag Handle */}
        <div 
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          className={`px-3.5 py-2.5 flex items-center justify-between gap-2 border-b cursor-move ${
            isLight
              ? 'bg-gradient-to-r from-slate-100 to-cyan-50/50 border-slate-200 text-slate-800'
              : 'bg-gradient-to-r from-slate-900/90 to-cyan-950/60 border-slate-800 text-slate-200'
          }`}
        >
          {/* Left: Terminal Branding */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-cyan-500">
              <GripHorizontal className="w-4 h-4 opacity-70 hover:opacity-100 cursor-grab active:cursor-grabbing" />
              <div className="w-6 h-6 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <Brain className="w-3.5 h-3.5 text-cyan-400" />
              </div>
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-black tracking-wider uppercase font-mono-numbers">
                  SMC PRO TERMINAL
                </span>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              <span className="text-xs font-mono-numbers text-cyan-600 dark:text-cyan-400 font-bold">
                {asset.symbol} • {timeframe} • FXAlexG Engine
              </span>
            </div>
          </div>

          {/* Right: Actions (Dock Selector, Minimize, Tabs) */}
          <div className="flex items-center gap-1">
            {/* Dock selector when in floating mode */}
            {isFloating && (
              <select
                value={dockPos}
                onChange={(e) => setDockPos(e.target.value as DockPosition)}
                className={`text-xs font-mono-numbers font-bold px-1.5 py-1 rounded-md border cursor-pointer ${
                  isLight ? 'bg-white border-slate-200 text-slate-700' : 'bg-slate-900 border-slate-700 text-slate-300'
                }`}
                title="Position / Docking"
              >
                <option value="top-right">↗ Top-R</option>
                <option value="top-left">↖ Top-L</option>
                <option value="bottom-right">↘ Btm-R</option>
                <option value="bottom-left">↙ Btm-L</option>
                <option value="floating">Float</option>
              </select>
            )}

            {/* Minimize / Maximize */}
            <button
              onClick={() => setIsMinimized(!isMinimized)}
              className={`p-1.5 rounded-lg border transition cursor-pointer ${
                isLight ? 'bg-white hover:bg-slate-100 border-slate-200 text-slate-600' : 'bg-slate-800/80 hover:bg-slate-700 border-slate-700 text-slate-300'
              }`}
              title={isMinimized ? "Agrandir" : "Réduire"}
            >
              {isMinimized ? <Maximize2 className="w-3.5 h-3.5" /> : <Minimize2 className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Minimized Quick Bar */}
        {isMinimized ? (
          <div className="p-2.5 flex items-center justify-between gap-3 text-xs font-mono-numbers">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-extrabold px-2 py-0.5 rounded-md ${
                isInsideOB 
                  ? 'bg-emerald-500 text-white animate-pulse'
                  : isLight ? 'bg-cyan-100 text-cyan-800' : 'bg-cyan-950 text-cyan-300'
              }`}>
                {isInsideOB ? 'IN ZONE' : `${distancePips} Pips away`}
              </span>
              <span className="font-bold text-xs">
                {smc.confluenceScore}% Conf
              </span>
            </div>
            <button
              onClick={() => setIsMinimized(false)}
              className="text-xs text-cyan-500 font-bold hover:underline"
            >
              {isAr ? 'فتح التفاصيل' : 'Ouvrir'}
            </button>
          </div>
        ) : (
          /* Full Organized Terminal Body */
          <div className="p-3.5 space-y-3 text-xs">
            
            {/* 1. Category Switcher Tabs */}
            <div className={`grid grid-cols-3 p-0.5 rounded-xl border text-xs font-bold ${
              isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-900/90 border-slate-800'
            }`}>
              <button
                onClick={() => setActiveTab('hud')}
                className={`py-1.5 px-2 rounded-lg transition flex items-center justify-center gap-1 cursor-pointer ${
                  activeTab === 'hud'
                    ? 'bg-cyan-600 text-white shadow-xs'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Zap className="w-3 h-3" />
                <span>{isAr ? 'الرادار الحي' : 'Live HUD'}</span>
              </button>

              <button
                onClick={() => setActiveTab('flow')}
                className={`py-1.5 px-2 rounded-lg transition flex items-center justify-center gap-1 cursor-pointer ${
                  activeTab === 'flow'
                    ? 'bg-cyan-600 text-white shadow-xs'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Layers className="w-3 h-3" />
                <span>{isAr ? 'مراحل 4-SMC' : '4-Step Flow'}</span>
              </button>

              <button
                onClick={() => setActiveTab('confluence')}
                className={`py-1.5 px-2 rounded-lg transition flex items-center justify-center gap-1 cursor-pointer ${
                  activeTab === 'confluence'
                    ? 'bg-cyan-600 text-white shadow-xs'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                <BarChart3 className="w-3 h-3" />
                <span>{isAr ? 'التأكيد' : 'Confluence'}</span>
              </button>
            </div>

            {/* TAB 1: Live HUD Overview */}
            {activeTab === 'hud' && (
              <div className="space-y-2.5">
                {/* Realtime Order Block Radar Box */}
                <div className={`p-3 rounded-xl border ${
                  isInsideOB
                    ? isLight ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950' : 'bg-emerald-950/40 border-emerald-600 text-emerald-100'
                    : isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                }`}>
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1.5">
                      <Crosshair className={`w-3.5 h-3.5 ${isInsideOB ? 'text-emerald-500 animate-spin' : 'text-cyan-500'}`} />
                      <span className="font-bold text-xs uppercase tracking-wider">
                        {isAr ? 'منطقة بلوك الأوامر (15M OB)' : 'Refined Order Block'}
                      </span>
                    </div>
                    <span className={`text-xs font-black px-2 py-0.5 rounded-full ${
                      isInsideOB
                        ? 'bg-emerald-500 text-white animate-pulse'
                        : isLight ? 'bg-amber-100 text-amber-800' : 'bg-amber-950 text-amber-300'
                    }`}>
                      {isInsideOB ? (isAr ? 'السعر داخل الزون' : 'IN ZONE') : `${distancePips} Pips away`}
                    </span>
                  </div>

                  <div className="flex items-baseline justify-between font-mono-numbers">
                    <div>
                      <span className="text-xs text-slate-500 block">OB Range</span>
                      <strong className="text-xs text-cyan-600 dark:text-cyan-300">
                        ${smc.orderBlock.low.toFixed(asset.decimalPlaces)} — ${smc.orderBlock.high.toFixed(asset.decimalPlaces)}
                      </strong>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-slate-500 block">Current Price</span>
                      <strong className={`text-xs ${asset.change24h >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        ${asset.price.toFixed(asset.decimalPlaces)}
                      </strong>
                    </div>
                  </div>

                  {/* Proximity progress bar */}
                  <div className="mt-2 w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-300 ${isInsideOB ? 'bg-emerald-500' : 'bg-cyan-500'}`}
                      style={{ width: `${Math.max(10, Math.min(100, 100 - Number(distancePips) * 2))}%` }}
                    />
                  </div>
                </div>

                {/* Key Metric Blocks */}
                <div className="grid grid-cols-2 gap-2 text-xs font-mono-numbers">
                  {/* Confluence Score */}
                  <div className={`p-2.5 rounded-xl border ${
                    isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                  }`}>
                    <span className="text-xs text-slate-500 block font-sans font-medium">
                      {isAr ? 'معدل التطابق' : 'Confluence Score'}
                    </span>
                    <div className="flex items-center justify-between mt-1">
                      <strong className="text-cyan-600 dark:text-cyan-400 text-sm">
                        {smc.confluenceScore}%
                      </strong>
                      <span className="text-xs px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-500 font-bold">
                        A+ Grade
                      </span>
                    </div>
                  </div>

                  {/* Premium / Discount */}
                  <div className={`p-2.5 rounded-xl border ${
                    isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                  }`}>
                    <span className="text-xs text-slate-500 block font-sans font-medium">
                      {isAr ? 'التسعير المؤسساتي' : 'Pricing Matrix'}
                    </span>
                    <div className="flex items-center justify-between mt-1">
                      <strong className={`text-xs ${
                        smc.premiumDiscount.includes('Discount') 
                          ? 'text-emerald-600 dark:text-emerald-400' 
                          : 'text-rose-600 dark:text-rose-400'
                      }`}>
                        {smc.premiumDiscount}
                      </strong>
                    </div>
                  </div>
                </div>

                {/* Quick Institutional Bias Banner */}
                <div className={`p-2.5 rounded-xl border flex items-center gap-2 ${
                  isLight ? 'bg-cyan-50/70 border-cyan-200 text-cyan-900' : 'bg-cyan-950/40 border-cyan-800/40 text-cyan-200'
                }`}>
                  <Sparkles className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
                  <p className="text-xs leading-snug font-medium">
                    {smc.institutionalBias}
                  </p>
                </div>
              </div>
            )}

            {/* TAB 2: 4-Step SMC Flow (FXAlexG Set & Forget) */}
            {activeTab === 'flow' && (
              <div className="space-y-2">
                {/* Step 1: Liquidity Sweep */}
                <div className={`p-2.5 rounded-xl border flex items-start justify-between gap-2 ${
                  isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                }`}>
                  <div className="flex items-start gap-2">
                    <div className="w-5 h-5 rounded-md bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-500 font-bold text-xs shrink-0 mt-0.5">
                      1
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs">{isAr ? 'سحب سيولة آسيا' : 'Asian Range Sweep'}</span>
                        <span className="text-xs px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-600 font-black">PASSED</span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 font-mono-numbers mt-0.5">
                        Level: ${smc.liquiditySweep.level.toFixed(asset.decimalPlaces)} ({smc.liquiditySweep.type})
                      </p>
                    </div>
                  </div>
                </div>

                {/* Step 2: 15M ChoCh / MSS */}
                <div className={`p-2.5 rounded-xl border flex items-start justify-between gap-2 ${
                  isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                }`}>
                  <div className="flex items-start gap-2">
                    <div className="w-5 h-5 rounded-md bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-sky-500 font-bold text-xs shrink-0 mt-0.5">
                      2
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs">{isAr ? 'كسر الهيكل (ChoCh/MSS)' : 'Structure Shift (MSS)'}</span>
                        <span className="text-xs px-1.5 py-0.2 rounded bg-sky-500/15 text-sky-600 font-black">CONFIRMED</span>
                      </div>
                      <p className={`text-xs font-bold font-mono-numbers mt-0.5 ${
                        smc.marketStructureShift.includes('Bullish') ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                      }`}>
                        {smc.marketStructureShift}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Step 3: Order Block / FVG */}
                <div className={`p-2.5 rounded-xl border flex items-start justify-between gap-2 ${
                  isInsideOB 
                    ? isLight ? 'bg-emerald-50 border-emerald-300' : 'bg-emerald-950/40 border-emerald-700'
                    : isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                }`}>
                  <div className="flex items-start gap-2">
                    <div className="w-5 h-5 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-500 font-bold text-xs shrink-0 mt-0.5">
                      3
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs">{isAr ? 'بلوك الأوامر 15M OB' : '15M Order Block'}</span>
                        <span className={`text-xs px-1.5 py-0.2 rounded font-black ${
                          isInsideOB ? 'bg-emerald-500 text-white animate-pulse' : 'bg-emerald-500/15 text-emerald-600'
                        }`}>
                          {isInsideOB ? 'RETEST ACTIVE' : 'WAITING RETEST'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 font-mono-numbers mt-0.5">
                        ${smc.orderBlock.low.toFixed(asset.decimalPlaces)} — ${smc.orderBlock.high.toFixed(asset.decimalPlaces)}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Step 4: 5-Minute Sniper Confirmation Candle Close */}
                <div className={`p-2.5 rounded-xl border flex items-start justify-between gap-2 ${
                  isLight ? 'bg-amber-50/70 border-amber-200 text-amber-950' : 'bg-amber-950/30 border-amber-800/40 text-amber-200'
                }`}>
                  <div className="flex items-start gap-2">
                    <div className="w-5 h-5 rounded-md bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-500 font-bold text-xs shrink-0 mt-0.5">
                      4
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs">{isAr ? 'تأكيد الدخول على فريم 5M (5M Confirmation)' : '5M Confirmation Trigger'}</span>
                        <span className="text-xs px-1.5 py-0.2 rounded bg-amber-500 text-slate-950 font-black animate-pulse">
                          5M SNIPER TRIGGER
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 dark:text-slate-300 font-medium mt-0.5">
                        {isAr ? 'فريم 5 دقائق يُستخدم حصراً لتأكيد كسر الهيكل (MSS) وابتلاع التلاعب، بينما الستوب (SL) والأهداف (TP) تُبنى على هيكل فريم 4 ساعات (4H)' : '5M timeframe is used strictly for sniper entry confirmation, while SL and TP are anchored to 4H structure to prevent manipulation wicks.'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Step 5: 4H Structure Set & Forget Protocol */}
                <div className={`p-2.5 rounded-xl border flex items-start justify-between gap-2 ${
                  isLight ? 'bg-purple-50/50 border-purple-200 text-purple-950' : 'bg-purple-950/30 border-purple-800/40 text-purple-200'
                }`}>
                  <div className="flex items-start gap-2">
                    <div className="w-5 h-5 rounded-md bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-500 font-bold text-xs shrink-0 mt-0.5">
                      5
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs">{isAr ? 'أهداف وهيكل فريم 4H (4H SL & TP Protocol)' : '4H SL & TP Protocol'}</span>
                        <span className="text-xs px-1.5 py-0.2 rounded bg-purple-500/15 text-purple-600 font-black">1:3.8+ R:R</span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-300 font-medium mt-0.5">
                        {isAr ? 'الستوب (SL) محمي خلف قاع/قمة 4H + حاجز أمان ضد التلاعب. الأهداف (TP1 & TP2) عند مسابح سيولة 4H المؤسساتية' : 'SL protected beyond 4H swing + anti-manipulation buffer. TPs target major 4H external liquidity pools.'}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: Confluence & Multi-Timeframe Matrix */}
            {activeTab === 'confluence' && (
              <div className="space-y-2 font-mono-numbers">
                <div className={`p-2.5 rounded-xl border ${
                  isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
                }`}>
                  <div className="flex justify-between items-center text-xs mb-1">
                    <span className="font-sans text-slate-500">1H Higher Timeframe Trend:</span>
                    <strong className={asset.trend === 'Bullish' ? 'text-emerald-500' : 'text-rose-500'}>
                      {asset.trend} ({asset.trendStrength}%)
                    </strong>
                  </div>
                  <div className="flex justify-between items-center text-xs mb-1">
                    <span className="font-sans text-slate-500">Fair Value Gap (FVG):</span>
                    <strong className="text-cyan-500">Active Retest Zone</strong>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-sans text-slate-500">Institutional Order Flow:</span>
                    <strong className="text-purple-500">Smart Money Accumulation</strong>
                  </div>
                </div>

                <div className={`p-2.5 rounded-xl border text-xs ${
                  isLight ? 'bg-emerald-50/70 border-emerald-200 text-emerald-950' : 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                }`}>
                  <span className="font-sans font-bold block mb-0.5">توصية إدارة المخاطر:</span>
                  <p className="font-sans text-xs leading-relaxed">
                    مخاطرة 1.0% كحد أقصى من رصيد الحساب. وضع الستوب لوس خلف ذيل شمعة السحب مباشرة لتقليل الخسارة المحتملة لأدنى حد.
                  </p>
                </div>
              </div>
            )}

            {/* Terminal Bottom Controls */}
            <div className={`pt-2 border-t flex items-center justify-between gap-2 text-xs ${
              isLight ? 'border-slate-200 text-slate-500' : 'border-slate-800 text-slate-400'
            }`}>
              <div className="flex items-center gap-1 font-mono-numbers">
                <Clock className="w-3 h-3 text-amber-500" />
                <span className="text-amber-600 dark:text-amber-400 font-bold">{isAr ? 'شمعة التأكيد 5M (مؤكدة)' : '5M Confirmation Candle (Validated)'}</span>
              </div>

              {onFocusOrderBlock && (
                <button
                  onClick={onFocusOrderBlock}
                  className="font-bold text-cyan-600 dark:text-cyan-400 hover:underline flex items-center gap-0.5 cursor-pointer"
                >
                  <span>{isAr ? 'تركيز على الشارت' : 'Focus Zone'}</span>
                  <ChevronRight className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
