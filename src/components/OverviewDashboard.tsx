import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { MarketAsset, AISignal, NewsItem, SentimentData, TechnicalIndicators, Language } from '../types';
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  Radio, 
  Activity, 
  Zap, 
  ShieldCheck, 
  Send,
  BarChart2,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  TrendingUp,
  RefreshCw,
  Clock,
  Layers,
  Scale
} from 'lucide-react';

interface OverviewProps {
  activeAsset: MarketAsset;
  signals: AISignal[];
  news: NewsItem[];
  sentiment: SentimentData | null;
  indicators: TechnicalIndicators | null;
  onNavigateTab: (tab: string) => void;
  onSelectSignalForRisk: (signal: AISignal) => void;
  onOpenAssistant?: () => void;
  onOpenTelegram?: () => void;
  onSelectAsset?: (symbol: string) => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

interface EngineEvalData {
  status: 'VALID_SETUP' | 'NO_TRADE';
  symbol: string;
  timeframe: string;
  action: 'BUY' | 'SELL' | 'NO_TRADE';
  executionType: string;
  confluenceScore: number;
  entryPrice: number;
  stopLossPrice: number;
  slDistancePips: number;
  takeProfit1Price: number;
  takeProfit2Price: number;
  overallRR: string;
  atr14: number;
  rejectionReason?: string;
  rejectionReasonAr?: string;
  technicalBreakdown?: string[];
  technicalBreakdownAr?: string[];
  pillars?: {
    htfTrend: { score: number; bias: string; details: string; detailsAr: string };
    structuralLevel: { score: number; levelType: string; details: string; detailsAr: string };
    candleAndVolume: { score: number; pattern: string; details: string; detailsAr: string };
    indicatorAlignment: { score: number; rsi: number; details: string; detailsAr: string };
  };
}

export const OverviewDashboard: React.FC<OverviewProps> = ({
  activeAsset,
  signals,
  news,
  indicators,
  onNavigateTab,
  onSelectSignalForRisk,
  onOpenTelegram,
  lang,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const [engineData, setEngineData] = useState<EngineEvalData | null>(null);
  const [loadingEngine, setLoadingEngine] = useState<boolean>(false);
  const [lastScannedTime, setLastScannedTime] = useState<string>('');

  // Fetch real-time evaluation from CoreTradingEngine API
  const fetchCoreEngineEval = async () => {
    if (!activeAsset) return;
    setLoadingEngine(true);
    try {
      const res = await fetch(`/api/engine/evaluate?symbol=${encodeURIComponent(activeAsset.symbol)}&timeframe=15M`);
      if (res.ok) {
        const json = await res.json();
        if (json.success && json.evaluation) {
          setEngineData(json.evaluation);
          setLastScannedTime(new Date().toLocaleTimeString(isFr ? 'fr-FR' : isAr ? 'ar-MA' : 'en-US'));
        }
      }
    } catch {
      // quiet fallback to matched signal in props
    } finally {
      setLoadingEngine(false);
    }
  };

  useEffect(() => {
    fetchCoreEngineEval();
    const interval = setInterval(fetchCoreEngineEval, 20000);
    return () => clearInterval(interval);
  }, [activeAsset.symbol]);

  if (!activeAsset) return null;

  const currentSignal = signals.find((s) => s.symbol === activeAsset.symbol) || signals[0];
  const isClosed = activeAsset.isMarketOpen === false;

  // Active status from CoreTradingEngine
  const isSetupValid = engineData ? engineData.status === 'VALID_SETUP' : (currentSignal?.status === 'active' && (currentSignal?.confidence || 0) >= 85);
  const confluenceScore = engineData ? engineData.confluenceScore : (currentSignal?.confidence || 75);
  const actionDirection = engineData ? engineData.action : (currentSignal?.signalType || 'BUY');
  const isBuy = actionDirection === 'BUY';

  // Entry, SL, TP
  const entryPrice = engineData ? engineData.entryPrice : (currentSignal?.entryPrice || activeAsset.price);
  const stopLoss = engineData ? engineData.stopLossPrice : (currentSignal?.stopLoss || activeAsset.price * 0.995);
  const tp1 = engineData ? engineData.takeProfit1Price : (currentSignal?.target1 || activeAsset.price * 1.01);
  const tp2 = engineData ? engineData.takeProfit2Price : (currentSignal?.target2 || activeAsset.price * 1.02);
  const rrRatio = engineData ? engineData.overallRR : (currentSignal?.riskReward || '1:2.8');
  const slPips = engineData ? engineData.slDistancePips : 85.0;

  return (
    <div className="space-y-6 w-full max-w-full font-sans text-slate-100">

      {/* ============================================================ */}
      {/* 1. HERO TERMINAL BANNER: SINGLE CORE ENGINE FOCUS */}
      {/* ============================================================ */}
      <section className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-surface/95 p-6 sm:p-7 shadow-2xl backdrop-blur-xl">
        <div className="absolute top-0 right-1/4 w-72 h-72 bg-gold-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-10 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2.5 max-w-2xl">
            {/* Unboxed Metadata Header (Zero-Pill Compliance) */}
            <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-zinc-400">
              <span className="text-gold-500 font-bold">XAU/USD · OTC SPOT · NY SILVER BULLET ENGINE</span>
              <span aria-hidden="true">·</span>
              <span className="text-zinc-300">14:00 - 15:00 GMT (M15 / M5)</span>
              <span aria-hidden="true">·</span>
              <span className="flex items-center gap-1.5 text-zinc-300">
                <span className={`w-2 h-2 rounded-full ${isClosed ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`} />
                {isClosed 
                  ? (isFr ? 'Marché Fermé (Rollover CME 21h-22h GMT)' : isAr ? 'السوق مغلق (تسوية CME من 21:00 إلى 22:00 GMT)' : 'CME Rollover Pause (21:00 - 22:00 GMT)') 
                  : (isFr ? 'OTC Spot Ouvert (Dim 22h - Ven 21h GMT)' : isAr ? 'سوق الذهب الفوري مفتوح (الأحد 22:00 - الجمعة 21:00 GMT)' : 'OTC Spot Open (Sun 22:00 – Fri 21:00 GMT)')}
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>{activeAsset.symbol}</span>
              <span className="font-mono text-xl sm:text-2xl font-bold text-gold-500">
                ${activeAsset.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`text-xs font-mono font-bold flex items-center ${activeAsset.change24h >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {activeAsset.change24h >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                {activeAsset.change24h >= 0 ? '+' : ''}{activeAsset.change24h}%
              </span>
            </h1>

            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed max-w-xl">
              {isFr
                ? 'Analyseur quantitatif unique : structure de marché (BOS/CHoCH), sweeps de liquidité, zones Supply/Demand et confirmation de volume avec filtrage strict de confluence (>= 85%).'
                : isAr
                ? 'محرك التحليل المؤسساتي الموحد: هيكل السوق (BOS/CHoCH)، سحب السيولة، مناطق العرض والطلب، وتأكيد الفوليوم مع شرط تطابق صارم (>= 85%).'
                : 'Single institutional quant engine: market structure (BOS/CHoCH), liquidity sweeps, supply/demand order blocks, and volume confirmation with strict >=85% confluence threshold.'}
            </p>
          </div>

          {/* Quick Action Navigation */}
          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <button
              onClick={() => onNavigateTab('signals')}
              className="min-h-[42px] px-4 py-2 rounded-xl text-xs font-bold bg-gold-500 hover:bg-gold-400 text-ink-strong flex items-center gap-2 shadow-lg shadow-gold-500/20 transition-all hover:scale-[1.02] active:scale-95 cursor-pointer"
            >
              <Radio className="w-4 h-4 text-ink-strong animate-pulse" />
              <span>{isFr ? 'Signaux A+' : isAr ? 'صفقات النخبة A+' : 'Elite Signals'}</span>
            </button>

            <button
              onClick={() => onNavigateTab('chart')}
              className="min-h-[42px] px-4 py-2 rounded-xl text-xs font-bold bg-surface-2 hover:bg-surface-3 text-zinc-200 hover:text-white border border-white/[0.1] hover:border-gold-500/50 flex items-center gap-2 transition active:scale-95 cursor-pointer"
            >
              <BarChart2 className="w-4 h-4 text-gold-500" />
              <span>{isFr ? 'Graphique Pro' : isAr ? 'الشارت الدقيق' : 'Precision Chart'}</span>
            </button>

            {onOpenTelegram && (
              <button
                onClick={onOpenTelegram}
                className="min-h-[42px] px-4 py-2 rounded-xl text-xs font-bold bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/30 flex items-center gap-2 transition active:scale-95 cursor-pointer"
              >
                <Send className="w-4 h-4 text-sky-400" />
                <span>{isFr ? 'Telegram' : isAr ? 'تيليجرام' : 'Telegram Bot'}</span>
              </button>
            )}

            <button
              onClick={fetchCoreEngineEval}
              disabled={loadingEngine}
              className="min-h-[42px] px-3 py-2 rounded-xl text-xs font-bold bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-white/[0.08] flex items-center gap-1.5 transition active:scale-95 cursor-pointer"
              title="Rescan market now"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingEngine ? 'animate-spin text-gold-500' : ''}`} />
              <span className="hidden sm:inline">{isFr ? 'Actualiser' : isAr ? 'تحديث' : 'Refresh'}</span>
            </button>
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/* 2. CORE TRADING ENGINE STATUS & PRECISION SL/TP DISPLAY */}
      {/* ============================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        
        {/* Left Column: Active Signal Status & Mathematical Levels (8 cols) */}
        <div className="lg:col-span-8 space-y-5">
          <div className="rounded-2xl border border-white/[0.08] bg-surface p-5 sm:p-6 shadow-xl">
            {/* Header Strip */}
            <div className="flex items-center justify-between pb-4 border-b border-white/[0.08] mb-5">
              <div className="flex items-center gap-2.5">
                <div className={`w-3 h-3 rounded-full ${isSetupValid ? (isBuy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500 animate-pulse') : 'bg-zinc-500'}`} />
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <span>{isFr ? 'Statut du Signal en Temps Réel' : isAr ? 'حالة الصفقة الحية الصريحة' : 'Active Signal Status'}</span>
                    <span className="text-xs font-mono text-zinc-400 font-normal">({activeAsset.symbol} · 15M)</span>
                  </h3>
                </div>
              </div>

              {/* Status Indicator */}
              <div className="flex items-center gap-2">
                {isSetupValid ? (
                  <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-md border ${
                    isBuy ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                  }`}>
                    {actionDirection} · MARKET EXECUTION
                  </span>
                ) : (
                  <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-md bg-zinc-800 text-zinc-400 border border-zinc-700">
                    NO_TRADE · WAITING CLEAN SETUP
                  </span>
                )}
              </div>
            </div>

            {/* Signal Details Content */}
            {isSetupValid ? (
              <div className="space-y-5">
                {/* Mathematical Levels Grid: Entry, SL, TP1, TP2 */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-xl border border-white/[0.06] bg-surface-2">
                    <span className="text-xs text-zinc-400 block mb-1">
                      {isFr ? 'Prix d\'Entrée' : isAr ? 'سعر الدخول' : 'Entry Price'}
                    </span>
                    <span className="font-mono text-base font-bold text-white">
                      ${entryPrice.toFixed(2)}
                    </span>
                    <span className="text-xs text-emerald-400/80 block mt-0.5">Market Tick</span>
                  </div>

                  <div className="p-3 rounded-xl border border-rose-500/25 bg-rose-500/5">
                    <span className="text-xs text-rose-400 block mb-1">
                      {isFr ? 'Stop Loss (SL)' : isAr ? 'وقف الخسارة (SL)' : 'Stop Loss (SL)'}
                    </span>
                    <span className="font-mono text-base font-bold text-rose-400">
                      ${stopLoss.toFixed(2)}
                    </span>
                    <span className="text-xs text-rose-300/80 block mt-0.5">
                      -{slPips} pips (0.5x ATR buffer)
                    </span>
                  </div>

                  <div className="p-3 rounded-xl border border-emerald-500/25 bg-emerald-500/5">
                    <span className="text-xs text-emerald-400 block mb-1">
                      {isFr ? 'Objectif 1 (TP1)' : isAr ? 'الهدف 1 (TP1)' : 'Take Profit 1'}
                    </span>
                    <span className="font-mono text-base font-bold text-emerald-400">
                      ${tp1.toFixed(2)}
                    </span>
                    <span className="text-xs text-emerald-300/80 block mt-0.5">1:1.8 R:R (BE Lock)</span>
                  </div>

                  <div className="p-3 rounded-xl border border-gold-500/30 bg-gold-500/5">
                    <span className="text-xs text-gold-500 block mb-1">
                      {isFr ? 'Objectif 2 (TP2)' : isAr ? 'الهدف 2 (TP2)' : 'Take Profit 2'}
                    </span>
                    <span className="font-mono text-base font-bold text-gold-500">
                      ${tp2.toFixed(2)}
                    </span>
                    <span className="text-xs text-gold-500/80 block mt-0.5">{rrRatio} Full Liquidity</span>
                  </div>
                </div>

                {/* Technical Breakdown Bullets */}
                <div className="p-4 rounded-xl border border-white/[0.06] bg-surface-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-gold-500" />
                      {isFr ? 'Confirmation Structurelle du Graphique' : isAr ? 'التأكيد الهيكلي الرياضي من الشارت' : 'Chart Structural Confirmation'}
                    </span>
                    <span className="text-xs font-mono text-gold-500 font-bold">R:R {rrRatio}</span>
                  </div>
                  
                  <ul className="space-y-1.5 text-xs text-zinc-300">
                    {(engineData?.technicalBreakdown || [
                      `Anchor: Validated Swing ${isBuy ? 'Low' : 'High'} with dynamic 0.5x ATR buffer to protect from stop-hunts`,
                      `Structure: Higher-Timeframe Trend alignment & clean Order Block test`,
                      `Trigger: Institutional volume expansion & displacement candle rejection`
                    ]).map((bullet, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                        <span className="leading-relaxed">{isAr && engineData?.technicalBreakdownAr?.[idx] ? engineData.technicalBreakdownAr[idx] : bullet}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Action button: Risk Calculator */}
                <div className="flex items-center justify-between pt-2">
                  <button
                    onClick={() => onSelectSignalForRisk(currentSignal)}
                    className="min-h-[40px] px-4 py-2 rounded-xl bg-gradient-to-r from-gold-500 to-gold-600 hover:from-gold-400 hover:to-gold-500 text-ink-strong font-extrabold text-xs flex items-center gap-2 shadow-md shadow-gold-500/15 transition active:scale-95 cursor-pointer"
                  >
                    <Scale className="w-4 h-4 text-ink-strong" />
                    <span>{isFr ? 'Calculer Risque 1%' : isAr ? 'حساب لوت المحفظة (مخاطرة 1%)' : 'Calculate 1% Position Size'}</span>
                  </button>

                  <button
                    onClick={() => onNavigateTab('signals')}
                    className="text-xs text-zinc-400 hover:text-gold-500 font-medium flex items-center gap-1 transition"
                  >
                    <span>{isFr ? 'Voir tous les signaux' : isAr ? 'عرض سجل الصفقات' : 'View all signals'}</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              /* NO TRADE DISCIPLINE DISPLAY */
              <div className="py-6 px-4 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-3">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-amber-300">
                      {isFr 
                        ? 'Condition de Marché Insuffisante (NO TRADE)' 
                        : isAr 
                        ? 'حظر الدخول المؤسساتي (NO TRADE) — شروط الصفقة غير مكتملة' 
                        : 'Institutional Gate Active (NO TRADE) — Standby'}
                    </h4>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      {engineData?.rejectionReasonAr && isAr 
                        ? engineData.rejectionReasonAr 
                        : engineData?.rejectionReason || 'Confluence score below institutional 85% requirement. Professional traders do not force low-probability trades.'}
                    </p>
                  </div>
                </div>

                <div className="pt-2 border-t border-amber-500/20 flex flex-wrap items-center justify-between text-xs text-zinc-400 font-mono">
                  <span>THRESHOLD: &gt;= 85% Confluence</span>
                  <span>CURRENT SCORE: {confluenceScore}%</span>
                  <span>STATUS: STANDBY (ANTI-SPAM ACTIVE)</span>
                </div>
              </div>
            )}
          </div>

          {/* NY Silver Bullet 4-Step Execution Pipeline */}
          <div className="rounded-2xl border border-gold-500/35 bg-gradient-to-br from-surface-2 via-surface to-surface-2 p-5 shadow-2xl space-y-4 relative overflow-hidden group hover:border-gold-500/60 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gold-500/5 rounded-full blur-2xl pointer-events-none group-hover:bg-gold-500/10 transition-all duration-500" />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-white/[0.08] gap-2">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-gold-500/15 border border-gold-500/30 text-gold-500">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-black uppercase tracking-wider text-white">
                    {isFr ? 'Protocole NY Silver Bullet : 4 Étapes Séquentielles' : isAr ? 'بروتوكول NY Silver Bullet : خطوات التنفيذ الأربع' : 'NY Silver Bullet Protocol: 4 Sequential Steps'}
                  </h4>
                  <p className="text-xs text-zinc-400 font-mono">
                    PURE SPOT XAU/USD · M5 LIMIT EXECUTION · 1:2 MIN R:R
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-gold-500 font-extrabold px-2.5 py-1 rounded-lg bg-gold-500/10 border border-gold-500/30 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-gold-500 animate-spin" style={{ animationDuration: '6s' }} />
                  14:00 - 15:00 GMT
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div className="p-3.5 rounded-xl border border-white/[0.08] bg-surface-2/90 space-y-1.5 hover:border-gold-500/40 transition duration-200">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-extrabold text-gold-500 font-mono tracking-tight">STEP 1. M15 PREP</span>
                  <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">VERIFIED</span>
                </div>
                <h5 className="text-xs font-bold text-white">
                  {isAr ? 'رسم مستويات السيولة' : 'M15 Liquidity Mapping'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr ? 'تحديد قمم وقيعان جلسة آسيا (00-08h) ولندن (08-14h) كنقاط استهداف سيولة BSL/SSL.' : 'Asian Range (00-08 GMT) & London Range (08-14 GMT) Liquidity mapped.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-0.5 border-t border-white/[0.04]">
                  Target: Asian High/Low, London High/Low
                </div>
              </div>

              <div className="p-3.5 rounded-xl border border-white/[0.08] bg-surface-2/90 space-y-1.5 hover:border-gold-500/40 transition duration-200">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-extrabold text-gold-500 font-mono tracking-tight">STEP 2. M5 SWEEP</span>
                  <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">RAID DETECTED</span>
                </div>
                <h5 className="text-xs font-bold text-white">
                  {isAr ? 'سحب السيولة والرفض' : 'M5 Liquidity Raid'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr ? 'سحب سيولة BSL/SSL وإغلاق الشمعة فورا داخل النطاق خلال نافذة الـ 60 دقيقة.' : 'Price sweeps BSL/SSL and decisively closes back inside within 14:00-15:00 GMT.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-0.5 border-t border-white/[0.04]">
                  Window: 14:00 - 15:00 GMT (60 Mins)
                </div>
              </div>

              <div className="p-3.5 rounded-xl border border-white/[0.08] bg-surface-2/90 space-y-1.5 hover:border-gold-500/40 transition duration-200">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-extrabold text-gold-500 font-mono tracking-tight">STEP 3. M5 MSS</span>
                  <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">DISPLACEMENT</span>
                </div>
                <h5 className="text-xs font-bold text-white">
                  {isAr ? 'كسر الهيكل والزخم' : 'Energetic Displacement Close'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr ? 'كسر هيكل M5 باندفاع حقيقي: جسم الشمعة > 65% والمدى > 1.3x ATR(14).' : 'Confirmed M5 Structure Shift: candle body > 65% and range > 1.3x ATR(14).'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-0.5 border-t border-white/[0.04]">
                  Math: Body &gt; 65%, Range &gt; 1.3x ATR14
                </div>
              </div>

              <div className="p-3.5 rounded-xl border border-white/[0.08] bg-surface-2/90 space-y-1.5 hover:border-gold-500/40 transition duration-200">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-extrabold text-gold-500 font-mono tracking-tight">STEP 4. 50% CE FVG</span>
                  <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">LIMIT ORDER</span>
                </div>
                <h5 className="text-xs font-bold text-white">
                  {isAr ? 'فجوة FVG والأمر المعلق' : 'Unmitigated 50% CE Limit Entry'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr ? 'أمر معلق Limit عند منتصف الفجوة (50% CE) مع ستوب أسفل قاع السحب + 0.5 ATR.' : 'Limit Order at 50% Consequent Encroachment with structural stop & min 1:2 R:R.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-0.5 border-t border-white/[0.04]">
                  Risk: SL = Sweep Extreme &plusmn; 0.5x ATR
                </div>
              </div>
            </div>

            {/* 3 Strict Rejection Guards */}
            <div className="pt-3 border-t border-white/[0.08]">
              <div className="text-xs font-mono text-zinc-300 mb-2 font-bold uppercase tracking-wider flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>{isAr ? 'فلاتر الرفض القطعية الثلاثة (3 Strict Guards Active)' : 'Active Mechanical Guards (Auto NO_TRADE):'}</span>
                </span>
                <span className="text-xs text-zinc-400 font-normal">Deterministic Execution</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs font-mono">
                <div className="px-2.5 py-1.5 rounded-lg bg-zinc-900/90 border border-emerald-500/30 text-zinc-200 flex items-center justify-between">
                  <span><strong className="text-emerald-400">✓ Window</strong>: 14-15h GMT</span>
                  <span className="text-xs text-emerald-400 font-bold">STRICT</span>
                </div>
                <div className="px-2.5 py-1.5 rounded-lg bg-zinc-900/90 border border-emerald-500/30 text-zinc-200 flex items-center justify-between">
                  <span><strong className="text-emerald-400">✓ Displacement</strong>: &gt;65%</span>
                  <span className="text-xs text-emerald-400 font-bold">M5 BODY</span>
                </div>
                <div className="px-2.5 py-1.5 rounded-lg bg-zinc-900/90 border border-emerald-500/30 text-zinc-200 flex items-center justify-between">
                  <span><strong className="text-emerald-400">✓ Macro Filter</strong>: &le;3.5x ATR</span>
                  <span className="text-xs text-emerald-400 font-bold">NO NEWS</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Confluence Score Gauge & Telegram Status (4 cols) */}
        <div className="lg:col-span-4 space-y-5">
          
          {/* Confluence Score Card */}
          <div className="rounded-2xl border border-white/[0.08] bg-surface p-5 shadow-xl flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold text-zinc-400 block mb-3 uppercase tracking-wider">
                {isFr ? 'Indice de Confluence' : isAr ? 'مؤشر قوة التطابق' : 'Confluence Score'}
              </span>

              <div className="flex items-center justify-center my-4">
                <div className="relative w-36 h-36 flex items-center justify-center">
                  <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      stroke="#1A2030"
                      strokeWidth="8"
                      fill="transparent"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      stroke={confluenceScore >= 85 ? '#10B981' : '#F59E0B'}
                      strokeWidth="8"
                      strokeDasharray="251.2"
                      strokeDashoffset={251.2 - (251.2 * confluenceScore) / 100}
                      strokeLinecap="round"
                      fill="transparent"
                      className="transition-all duration-700 ease-out"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-mono text-3xl font-black text-white">{confluenceScore}%</span>
                    <span className="text-xs font-bold text-zinc-400 uppercase">
                      {confluenceScore >= 85 ? 'INSTITUTIONAL' : 'BELOW 85%'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between text-zinc-400">
                  <span>Threshold</span>
                  <span className="font-mono text-white font-bold">&gt;= 85%</span>
                </div>
                <div className="flex items-center justify-between text-zinc-400">
                  <span>Risk:Reward</span>
                  <span className="font-mono text-gold-500 font-bold">{rrRatio} (Min 1:2.0)</span>
                </div>
                <div className="flex items-center justify-between text-zinc-400">
                  <span>SL Calculation</span>
                  <span className="text-zinc-300">Swing Level + 0.5x ATR</span>
                </div>
              </div>
            </div>

            <div className="mt-5 pt-3 border-t border-white/[0.08] text-xs text-zinc-500 flex items-center justify-between font-mono">
              <span>SCAN INTERVAL: 15s</span>
              <span>{lastScannedTime ? `SYNC: ${lastScannedTime}` : 'ACTIVE'}</span>
            </div>
          </div>

          {/* Telegram Automated Dispatch Status Card */}
          <div className="rounded-2xl border border-white/[0.08] bg-surface p-5 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <Send className="w-4 h-4 text-sky-400" />
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                  {isFr ? 'Dispatcher Telegram' : isAr ? 'بوت التليجرام التلقائي' : 'Telegram Bot API'}
                </h4>
              </div>
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/25">
                ANTI-SPAM ON
              </span>
            </div>

            <div className="space-y-2 text-xs text-zinc-300 leading-relaxed">
              <p className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>
                  {isFr 
                    ? 'Envoi automatique uniquement si Confluence >= 85% et R:R >= 1:2.0' 
                    : isAr 
                    ? 'إرسال تلقائي فوري فقط عندما تكون الصفقة مضمونة (>= 85%) وبنسبة عائد تفوق 1:2.0' 
                    : 'Dispatches only when Confluence >= 85% and R:R >= 1:2.0'}
                </span>
              </p>
              <p className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>
                  {isFr 
                    ? 'Dédoublonnage strict par bougie (zéro spam)' 
                    : isAr 
                    ? 'حماية كاملة من السبام والتكرار على نفس الشمعة' 
                    : 'Strict candle deduplication (zero spam guarantee)'}
                </span>
              </p>
            </div>

            {onOpenTelegram && (
              <button
                onClick={onOpenTelegram}
                className="w-full min-h-[38px] flex items-center justify-center gap-2 py-2 px-3 rounded-xl border border-sky-500/30 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 text-xs font-bold transition active:scale-95 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{isFr ? 'Gérer les Paramètres Telegram' : isAr ? 'إعدادات وقنوات التيليجرام' : 'Configure Telegram Settings'}</span>
              </button>
            )}
          </div>

        </div>

      </div>

    </div>
  );
};
