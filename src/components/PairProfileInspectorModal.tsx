import React from 'react';
import { MarketAsset, AISignal, Language, PairProfile, DynamicSLTPAnalysis } from '../types';
import { 
  X, 
  ShieldCheck, 
  Layers, 
  Clock, 
  Target, 
  Zap, 
  AlertTriangle, 
  Activity, 
  Crosshair, 
  SlidersHorizontal,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Calendar
} from 'lucide-react';
import { TradingBadge, MarketRegimeTag, StatCard, TradingButton } from './common/TradingDesignSystem';
import { buildDynamicPairProfile, detectMarketStructureAndRegime, calculateStructureFirstSLTP } from '../services/pairProfileEngine';

interface PairProfileInspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: MarketAsset;
  signal?: AISignal | null;
  lang: Language;
}

export const PairProfileInspectorModal: React.FC<PairProfileInspectorModalProps> = ({
  isOpen,
  onClose,
  asset,
  signal,
  lang,
}) => {
  if (!isOpen || !asset) return null;

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  // Extract or synthesize pair profile
  const pairProfile: PairProfile = signal?.pairProfile || buildDynamicPairProfile(asset, []);
  const dynamicSLTP: DynamicSLTPAnalysis = signal?.dynamicSLTP || calculateStructureFirstSLTP(
    asset,
    asset.trend === 'Bullish' ? 'BUY' : 'SELL',
    [],
    pairProfile,
    detectMarketStructureAndRegime([], asset, pairProfile)
  );

  const isWait = dynamicSLTP.lifecycleState === 'WAIT' || signal?.signalType === 'WAIT';
  const isBuy = signal?.signalType === 'BUY' || asset.trend === 'Bullish';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-3xl my-6 rounded-2xl bg-surface border border-white/[0.1] shadow-2xl overflow-hidden text-zinc-100 flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-surface-2/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gold-500/10 border border-gold-500/30 flex items-center justify-center text-gold-500">
              <Crosshair className="w-5 h-5 text-gold-500" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-mono text-base font-bold text-white tracking-tight">
                  {asset.symbol}
                </h3>
                <span className="px-2 py-0.5 rounded text-xs font-mono font-medium uppercase tracking-wider bg-white/[0.06] text-zinc-300 border border-white/[0.08]">
                  {pairProfile.assetType.replace('_', ' ')}
                </span>
                <span className="px-2 py-0.5 rounded text-xs font-mono font-bold uppercase tracking-wider bg-gold-500/15 text-gold-500 border border-gold-500/30">
                  {pairProfile.volatilityRegime.replace('_', ' ')}
                </span>
              </div>
              <p className="text-xs text-zinc-400">
                {isAr ? 'الملف الكمي المستقل والستوب الهيكلي الديناميكي' : isFr ? 'Profil Quantitatif Indépendant & SL/TP Dynamique' : 'Independent Pair Profile & Dynamic Structure-First SL/TP'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/[0.06] border border-transparent hover:border-white/[0.08] transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 text-xs">
          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-surface-2 border border-white/[0.06]">
              <span className="text-xs font-mono uppercase text-zinc-400 block mb-1">
                {isAr ? 'السعر الحالي' : 'Live Price'}
              </span>
              <span className="font-mono text-sm font-bold text-zinc-100">
                {asset.price.toLocaleString(undefined, { minimumFractionDigits: asset.price < 10 ? 4 : 2 })}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface-2 border border-white/[0.06]">
              <span className="text-xs font-mono uppercase text-zinc-400 block mb-1">
                {isAr ? 'السبريد الحالي' : 'Live Spread'}
              </span>
              <span className="font-mono text-sm font-bold text-gold-500">
                {pairProfile.currentSpreadPips} pips
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface-2 border border-white/[0.06]">
              <span className="text-xs font-mono uppercase text-zinc-400 block mb-1">
                {isAr ? 'المدى اليومي ADR' : 'Avg Daily Range'}
              </span>
              <span className="font-mono text-sm font-bold text-zinc-100">
                {pairProfile.averageDailyRangePips} pips
              </span>
            </div>

            <div className="p-3 rounded-xl bg-surface-2 border border-white/[0.06]">
              <span className="text-xs font-mono uppercase text-zinc-400 block mb-1">
                {isAr ? 'حساسية الأخبار' : 'News Sensitivity'}
              </span>
              <span className={`font-mono text-sm font-bold ${
                pairProfile.newsSensitivity === 'Extreme' ? 'text-rose-400' :
                pairProfile.newsSensitivity === 'High' ? 'text-amber-400' : 'text-emerald-400'
              }`}>
                {pairProfile.newsSensitivity}
              </span>
            </div>
          </div>

          {/* 1. Multi-Timeframe ATR Matrix */}
          <div className="p-4 rounded-xl bg-surface-2 border border-white/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-gold-500" />
                <h4 className="font-mono font-bold text-zinc-100 uppercase text-xs">
                  {isAr ? 'مصفوفة التقلبات الحقيقية (ATR Matrix)' : 'Real Multi-Timeframe ATR Matrix'}
                </h4>
              </div>
              <span className="text-xs font-mono text-zinc-400">
                Period 14-ATR
              </span>
            </div>

            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-xs font-mono text-zinc-500 block">15M ATR</span>
                <span className="font-mono font-semibold text-zinc-200 text-xs">
                  {pairProfile.atrByTimeframe.m15}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-xs font-mono text-zinc-500 block">1H ATR</span>
                <span className="font-mono font-semibold text-gold-500 text-xs">
                  {pairProfile.atrByTimeframe.h1}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-xs font-mono text-zinc-500 block">4H ATR</span>
                <span className="font-mono font-semibold text-zinc-200 text-xs">
                  {pairProfile.atrByTimeframe.h4}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-xs font-mono text-zinc-500 block">D1 ATR</span>
                <span className="font-mono font-semibold text-zinc-200 text-xs">
                  {pairProfile.atrByTimeframe.d1}
                </span>
              </div>
            </div>
          </div>

          {/* 2. Structure-First Stop Loss Engine Breakdown */}
          <div className="p-4 rounded-xl bg-surface-2 border border-white/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-rose-400" />
                <h4 className="font-mono font-bold text-zinc-100 uppercase text-xs">
                  {isAr ? 'محرك الستوب الهيكلي (Structure-First SL Engine)' : 'Structure-First Stop Loss Engine'}
                </h4>
              </div>
              <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                SL = {dynamicSLTP.stopLossPrice} ({dynamicSLTP.slDistancePips} pips)
              </span>
            </div>

            <div className="p-3 rounded-lg bg-surface border border-white/[0.04] space-y-2">
              <div className="flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-rose-400 mt-1.5 shrink-0" />
                <div>
                  <span className="text-zinc-400 font-mono text-xs block">
                    {isAr ? 'نقطة الإلغاء الفني الحقيقي (Technical Invalidation Point):' : 'Technical Invalidation Level:'}
                  </span>
                  <span className="font-mono font-bold text-zinc-200 text-xs">
                    {dynamicSLTP.invalidationLevel}
                  </span>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {isAr ? dynamicSLTP.invalidationReasonAr : dynamicSLTP.invalidationReason}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2 pt-2 border-t border-white/[0.04]">
                <div className="w-1.5 h-1.5 rounded-full bg-gold-500 mt-1.5 shrink-0" />
                <div>
                  <span className="text-zinc-400 font-mono text-xs block">
                    {isAr ? 'هامش حماية التقلبات (Anti-Hunt Volatility Buffer):' : 'Volatility-Aware Breathing Room:'}
                  </span>
                  <span className="font-mono font-semibold text-gold-500 text-xs">
                    +{dynamicSLTP.volatilityBuffer} ({pairProfile.falseBreakoutFrequency} false breakout profile)
                  </span>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {dynamicSLTP.bufferReason}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 3. Structure-First Take Profit Targets (Multi-Target) */}
          <div className="p-4 rounded-xl bg-surface-2 border border-white/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-emerald-400" />
                <h4 className="font-mono font-bold text-zinc-100 uppercase text-xs">
                  {isAr ? 'أهداف السيولة الهيكلية (Realistic Targets)' : 'Structure-First Take Profit Targets'}
                </h4>
              </div>
              <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                R:R {dynamicSLTP.overallRR}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div className="p-3 rounded-lg bg-surface border border-white/[0.04]">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono font-bold text-emerald-400 text-xs">
                    TP1: {dynamicSLTP.takeProfit1Price}
                  </span>
                  <span className="text-xs font-mono text-zinc-400">
                    1:{dynamicSLTP.takeProfit1RR.toFixed(2)} R:R
                  </span>
                </div>
                <p className="text-xs text-zinc-400">
                  {isAr 
                    ? 'حجز 50% أرباح عند أول مسبح سيولة معاكس + نقل الستوب فوراً لنقطة الدخول (Breakeven).'
                    : dynamicSLTP.takeProfit1Reason}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-surface border border-white/[0.04]">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono font-bold text-emerald-400 text-xs">
                    TP2: {dynamicSLTP.takeProfit2Price}
                  </span>
                  <span className="text-xs font-mono text-zinc-400">
                    1:{dynamicSLTP.takeProfit2RR.toFixed(2)} R:R
                  </span>
                </div>
                <p className="text-xs text-zinc-400">
                  {isAr
                    ? 'هدف السيولة الخارجية الكبرى للهيكل الفني (HTF Liquidity Pool).'
                    : dynamicSLTP.takeProfit2Reason}
                </p>
              </div>
            </div>
          </div>

          {/* 4. Session Behavior & Typical Tendencies */}
          <div className="p-4 rounded-xl bg-surface-2 border border-white/[0.06] space-y-3">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-gold-500" />
              <h4 className="font-mono font-bold text-zinc-100 uppercase text-xs">
                {isAr ? 'سلوك جلسات التداول وطبيعة الزوج' : 'Session Behavior Profile'}
              </h4>
            </div>

            <div className="space-y-2 text-xs">
              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-zinc-500 font-mono block mb-0.5">
                  {isAr ? 'الجلسة النشطة حالياً:' : 'Active Session Now:'}
                </span>
                <span className="font-mono font-bold text-gold-500">
                  {pairProfile.typicalSessionBehavior.activeSessionNow}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-zinc-500 font-mono block mb-0.5">
                  {isAr ? 'سلوك الجلسة الآسيوية:' : 'Asian Session:'}
                </span>
                <span className="text-zinc-300">
                  {pairProfile.typicalSessionBehavior.asianSessionCharacter}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-zinc-500 font-mono block mb-0.5">
                  {isAr ? 'سلوك جلسة لندن:' : 'London Session:'}
                </span>
                <span className="text-zinc-300">
                  {pairProfile.typicalSessionBehavior.londonSessionCharacter}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface border border-white/[0.04]">
                <span className="text-zinc-500 font-mono block mb-0.5">
                  {isAr ? 'سلوك جلسة نيويورك:' : 'New York Session:'}
                </span>
                <span className="text-zinc-300">
                  {pairProfile.typicalSessionBehavior.newYorkSessionCharacter}
                </span>
              </div>
            </div>
          </div>

          {/* 5. Best-Performing Strategy Families */}
          <div className="p-4 rounded-xl bg-surface-2 border border-white/[0.06] space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-gold-500" />
              <h4 className="font-mono font-bold text-zinc-100 uppercase text-xs">
                {isAr ? 'عائلات الاستراتيجيات المناسبة لهذا الزوج' : 'Strategy families suited to this pair'}
              </h4>
            </div>

            <div className="space-y-2">
              {pairProfile.historicalStrategyPerformance.map((strat, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-surface border border-white/[0.04] text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-md bg-gold-500/10 text-gold-500 font-mono font-bold flex items-center justify-center text-xs">
                      {idx + 1}
                    </span>
                    <span className="font-mono font-medium text-zinc-200">
                      {strat.strategyName}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono text-xs">
                    <span className="text-zinc-400">
                      Target {strat.avgRR}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-white/[0.08] bg-surface-2/90">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-zinc-400">
              {isAr ? 'حالة الصفقة:' : 'Setup Lifecycle:'}
            </span>
            <TradingBadge variant={isWait ? 'wait' : isBuy ? 'buy' : 'sell'}>
              {dynamicSLTP.lifecycleState}
            </TradingBadge>
          </div>

          <TradingButton variant="secondary" onClick={onClose} size="sm">
            {isAr ? 'إغلاق' : 'Close'}
          </TradingButton>
        </div>
      </div>
    </div>
  );
};
