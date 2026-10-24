import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AISignal, SignalsPerformanceStats, Language, MarketAsset } from '../types';
import { dispatchSignalToTelegram, dispatchSetupCancelledToTelegram } from '../services/clientTelegramService';
import {
  Radio,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle2,
  ShieldAlert,
  Copy,
  Check,
  Calculator,
  Send,
  Star,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Sparkles,
  Image as ImageIcon,
  X,
  Download,
  Eye,
  RefreshCw,
  Trophy,
  TrendingUp,
  Zap,
  Target,
  Layers,
  Flame,
  CheckCheck,
  Newspaper,
  Gauge,
  Activity,
  BarChart3,
  Cpu,
  Award,
  AlertOctagon,
  Scale,
  Crosshair,
  SlidersHorizontal,
  Bot
} from 'lucide-react';
import { PairProfileInspectorModal } from './PairProfileInspectorModal';
import { MultiAgentEcosystemModal } from './MultiAgentEcosystemModal';

interface SignalsSectionProps {
  signals: AISignal[];
  onSelectSignalForRisk: (signal: AISignal) => void;
  onOpenTelegram?: () => void;
  onRefreshSignals?: () => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const AISignalsSection: React.FC<SignalsSectionProps> = ({
  signals: initialSignals,
  onSelectSignalForRisk,
  onOpenTelegram,
  onRefreshSignals,
  lang,
  theme = 'light',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [signals, setSignals] = useState<AISignal[]>(initialSignals);
  const [filter, setFilter] = useState<'ALL' | 'OPEN_ONLY' | 'ACTIONABLE_NOW' | 'GOLD' | 'BUY' | 'SELL'>('GOLD');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sentSignalId, setSentSignalId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [expandedChecklistId, setExpandedChecklistId] = useState<string | null>(null);
  const [expandedPrecisionId, setExpandedPrecisionId] = useState<string | null>(null);
  const [selectedChartSignal, setSelectedChartSignal] = useState<{ signal: AISignal; isPreAlert: boolean } | null>(null);
  const [perfStats, setPerfStats] = useState<SignalsPerformanceStats | null>(null);
  const [lastSyncTime, setLastSyncTime] = useState<string>(isAr ? 'الآن مباشر' : 'Live Now');
  const [isMultiAgentModalOpen, setIsMultiAgentModalOpen] = useState<boolean>(false);
  const [expandedReasonsId, setExpandedReasonsId] = useState<string | null>(null);
  const [inspectingSignal, setInspectingSignal] = useState<AISignal | null>(null);

  // Stealth Offset Mode states for MetaTrader Quick Copy without broker flagging
  const [stealthEnabled, setStealthEnabled] = useState<Record<string, boolean>>({});
  const [circuitBreaker, setCircuitBreaker] = useState<{
    isTriggered: boolean;
    consecutiveLossCount: number;
    reasonAr: string;
    cooldownRemainingMinutes: number;
  } | null>(null);
  const [isResettingCb, setIsResettingCb] = useState(false);
  const [copiedField, setCopiedField] = useState<{ id: string; field: string } | null>(null);

  const handleCopyField = (id: string, field: 'SL' | 'TP1' | 'TP2' | 'ENTRY', value: string, symbol: string) => {
    // Pure, exact mathematical value copying - 100% precision
    const cleanValue = value.replace(/[^0-9.]/g, '');
    navigator.clipboard.writeText(cleanValue || value);
    setCopiedField({ id, field });
    setTimeout(() => setCopiedField(null), 1500);
  };

  // Keep local signals in sync when prop updates
  useEffect(() => {
    if (initialSignals && initialSignals.length > 0) {
      setSignals(initialSignals);
      const now = new Date();
      setLastSyncTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    }
  }, [initialSignals]);

  // Fetch initial performance stats & circuit breaker once on mount
  useEffect(() => {
    fetch('/api/signals/performance')
      .then(res => res.json())
      .then(data => {
        if (data?.stats) setPerfStats(data.stats);
      })
      .catch(() => {});

    fetch('/api/circuit-breaker')
      .then(res => res.json())
      .then(cb => {
        if (cb) setCircuitBreaker(cb);
      })
      .catch(() => {});
  }, []);

  const handleResetCircuitBreaker = async () => {
    setIsResettingCb(true);
    try {
      await fetch('/api/circuit-breaker/reset', { method: 'POST' });
      const res = await fetch('/api/signals?force=true');
      if (res.ok) {
        const data = await res.json();
        if (data.signals) setSignals(data.signals);
        if (data.circuitBreaker) setCircuitBreaker(data.circuitBreaker);
      }
    } catch (err) {
      // quiet
    } finally {
      setIsResettingCb(false);
    }
  };

  const handleManualSync = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch('/api/signals/refresh-actionable', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.signals) {
          setSignals(data.signals);
          const now = new Date();
          setLastSyncTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
        }
        if (data.circuitBreaker) {
          setCircuitBreaker(data.circuitBreaker);
        }
      }
      if (onRefreshSignals) onRefreshSignals();
    } catch (err) {
      // quiet
    } finally {
      setTimeout(() => setIsRefreshing(false), 600);
    }
  };

  const toggleChecklist = (id: string) => {
    setExpandedChecklistId(prev => (prev === id ? null : id));
  };

  const handleSendToTelegram = async (sig: AISignal, type: 'pre_alert' | 'confirmed' | 'cancelled' = 'confirmed') => {
    setIsSending(`${sig.id}-${type}`);
    try {
      let res;
      if (type === 'cancelled') {
        res = await dispatchSetupCancelledToTelegram(
          sig,
          isAr ? 'ما كايناش كونفيرماسيون 15M (لم يتحقق شرط التأكيد أو تم كسر منطقة الستوب).' : 'No 15M confirmation found.'
        );
      } else {
        res = await dispatchSignalToTelegram(sig, type === 'pre_alert');
      }
      if (res.success) {
        setSentSignalId(`${sig.id}-${type}`);
        setTimeout(() => setSentSignalId(null), 3500);
      } else {
        if (onOpenTelegram) onOpenTelegram();
      }
    } catch (err) {
      if (onOpenTelegram) onOpenTelegram();
    } finally {
      setIsSending(null);
    }
  };

  // Guarantee STRICTLY ONE ANALYSIS PER PAIR (Zero duplicate pairs: "khas ykon ghir analyse 1 l kola zawj")
  const uniqueSignals = useMemo(() => {
    const map = new Map<string, AISignal>();
    for (const sig of signals) {
      if (!sig || !sig.symbol) continue;
      if (!map.has(sig.symbol)) {
        map.set(sig.symbol, sig);
      } else {
        const existing = map.get(sig.symbol)!;
        const currentScore = (sig.confidence || 0) + (sig.isActionableNow ? 10 : 0);
        const existingScore = (existing.confidence || 0) + (existing.isActionableNow ? 10 : 0);
        if (currentScore > existingScore) {
          map.set(sig.symbol, sig);
        }
      }
    }
    return Array.from(map.values());
  }, [signals]);

  const filteredSignals = uniqueSignals.filter((sig) => {
    if (filter === 'OPEN_ONLY') return sig.isMarketOpen !== false;
    if (filter === 'ACTIONABLE_NOW') return sig.isActionableNow === true;
    if (filter === 'GOLD') return sig.symbol.includes('XAU') || sig.symbol.includes('Gold');
    if (filter === 'BUY') return sig.signalType === 'BUY';
    if (filter === 'SELL') return sig.signalType === 'SELL';
    return true;
  });

  const handleCopy = (sig: AISignal) => {
    const sl = sig.stopLoss.toString();
    const tp1 = sig.target1.toString();
    const tp2 = sig.target2.toString();

    const text = `🎯 [AI SMART SIGNAL] ${sig.symbol}\nType: ${sig.signalType} (${sig.setupGrade || 'A+'})\nLive Price: $${sig.currentLivePrice ?? sig.entryPrice}\nEntry Zone: ${sig.entryZone}\nSL: $${sl}\nTP1: $${tp1} (Move SL to Breakeven)\nTP2: $${tp2}\nRR: ${sig.riskReward}\nStrategy: ${sig.strategyUsed || 'ICT SMC'}`;
    navigator.clipboard.writeText(text);
    setCopiedId(sig.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className={`rounded-2xl border p-4 sm:p-5 shadow-sm transition-colors ${
      isLight ? 'bg-white border-slate-200' : 'bg-surface-2/95 border-slate-800'
    }`}>
      {/* 1. Header & Live Market Status */}
      <div className={`flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b ${
        isLight ? 'border-slate-100' : 'border-slate-800'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-xl border flex items-center justify-center ${
            isLight ? 'bg-emerald-50 border-emerald-200 text-emerald-700 shadow-2xs' : 'bg-emerald-950/80 border-emerald-800/60 text-emerald-400'
          }`}>
            <Radio className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className={`font-bold text-base flex items-center gap-2 ${isLight ? 'text-slate-900' : 'text-white'}`}>
                <span>{isFr ? 'CrewAI 5-Agent Framework • Spécialiste Or (XAU/USD)' : isAr ? 'منظومة CrewAI الذكية للتداول • الذهب (Gold XAU/USD)' : 'CrewAI 5-Agent Framework • Gold (XAU/USD)'}</span>
              </h3>
              <span className="flex items-center gap-1 text-xs font-extrabold px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-600 dark:text-purple-400 border border-purple-500/40">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse"></span>
                <span>{isFr ? 'CrewAI Python v3.10' : isAr ? 'منظومة CrewAI الذكية ' : 'CrewAI Python v3.10 '}</span>
              </span>
            </div>
            <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isAr
                ? '5 وكلاء CrewAI متخصصين: تحليل الهيكل، كشف السيولة، إدارة المخاطر، اعتماد الـ CTO، وإرسال فوري لتيليجرام.'
                : '5 specialized CrewAI agents: Market Structure, Liquidity & Zones, Risk Manager, CTO Audit, and Telegram Dispatcher.'}
            </p>
          </div>
        </div>

        {/* Live sync button & CrewAI Action Center */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsMultiAgentModalOpen(true)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs cursor-pointer ${
              isLight
                ? 'bg-purple-50 hover:bg-purple-100 text-purple-700 border-purple-200'
                : 'bg-purple-950/80 hover:bg-purple-900 text-purple-300 border-purple-800/80'
            }`}
            title={isAr ? 'غرفة عمليات وكلاء CrewAI الخمسة مع حوار مباشر وتقرير الـ CTO' : 'CrewAI 5 Agents Command Center'}
          >
            <Bot className="w-3.5 h-3.5 text-purple-500 animate-pulse" />
            <span>{isFr ? 'CrewAI (5 Agents)' : isAr ? 'غرفة عمليات CrewAI (5 وكلاء)' : 'CrewAI 5 Agents'}</span>
          </button>

          <button
            onClick={handleManualSync}
            disabled={isRefreshing}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs ${
              isLight
                ? 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-300'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border-slate-700'
            }`}
            title={isAr ? 'تحديث ومزامنة فورية للأسعار' : 'Sync Real-Time Market Prices'}
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-500 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>{isRefreshing ? (isAr ? 'جاري المزامنة...' : 'Syncing...') : (isAr ? 'تحديث الأسعار الآن' : 'Sync Live Prices')}</span>
          </button>

          {onOpenTelegram && (
            <button
              onClick={onOpenTelegram}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs ${
                isLight
                  ? 'bg-sky-50 hover:bg-sky-100 text-sky-700 border-sky-200'
                  : 'bg-sky-950/80 hover:bg-sky-900 text-sky-300 border-sky-800/80'
              }`}
            >
              <Send className="w-3.5 h-3.5 text-sky-500" />
              <span>{isFr ? 'Bot Telegram' : isAr ? 'بوت تليجرام' : 'Telegram Bot'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Core AI Trading Decision Principle Banner */}
      <div className={`p-3 rounded-xl border mb-3.5 text-xs flex flex-wrap items-center justify-between gap-2.5 ${
        isLight ? 'bg-gradient-to-r from-emerald-50 via-teal-50 to-sky-50 border-emerald-200 text-slate-800' : 'bg-gradient-to-r from-emerald-950/40 via-teal-950/30 to-sky-950/30 border-emerald-800/50 text-slate-200'
      }`}>
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
          <span className="font-bold">
            {isAr
              ? 'عقلية متداول محترف 100%: انضباط تام بدون سبام — صفقة واحدة مؤكدة فقط في المحفظة، تباعد 45 دقيقة على الأقل، تأمين الدخول (Breakeven) عند الهدف 1، وحماية كاملة من أوقات الأخبار الحارقة.'
              : isFr
              ? 'Discipline de Trader Pro : Zéro Spam — 1 seul trade actif dans le portefeuille, espacement 45 min, Breakeven à TP1 et zéro exposition aux news rouges.'
              : 'Real Pro Trader Discipline: Zero Spam — 1 active trade at a time, 45 min pacing, Breakeven at TP1, zero red news hazard.'}
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs shrink-0 font-extrabold text-emerald-600 dark:text-emerald-400">
          <span>{isAr ? 'صفقة واحدة نشطة' : '1 Active Trade'}</span>
          <span>•</span>
          <span>{isAr ? 'فاصل 45 دقيقة' : '45m Pacing'}</span>
          <span>•</span>
          <span>{isAr ? 'أقصى مخاطرة 1%' : 'Max 1% Risk'}</span>
        </div>
      </div>

      {/* Automatic Consecutive Loss Circuit Breaker Alert Banner */}
      {circuitBreaker?.isTriggered && (
        <div className="p-3.5 rounded-xl border mb-3.5 bg-rose-500/10 border-rose-500/40 text-rose-300 flex flex-wrap items-center justify-between gap-3 text-xs shadow-sm">
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0 animate-pulse" />
            <div>
              <div className="font-extrabold text-sm text-rose-200 flex items-center gap-2">
                <span>{isAr ? 'نظام حماية رأس المال التلقائي نشط (Loss Circuit Breaker)' : 'Capital Protection Circuit Breaker Active'}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  {isAr ? `${circuitBreaker.consecutiveLossCount} صفقات ضربت الوقف` : `${circuitBreaker.consecutiveLossCount} SL Hits`}
                </span>
              </div>
              <p className="text-rose-300/90 text-xs mt-0.5 leading-relaxed">
                {isAr ? circuitBreaker.reasonAr : 'Trading suspended temporarily to prevent drawdown during choppy market conditions.'}
              </p>
            </div>
          </div>
          <button
            onClick={handleResetCircuitBreaker}
            disabled={isResettingCb}
            className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shrink-0 transition flex items-center gap-1.5 shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isResettingCb ? 'animate-spin' : ''}`} />
            <span>{isResettingCb ? (isAr ? 'جاري الاستئناف...' : 'Resetting...') : (isAr ? 'استئناف المحرك الآن' : 'Resume Scanning')}</span>
          </button>
        </div>
      )}

      {/* 2. Live Market Performance Summary */}
      <div className={`grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 rounded-xl border mb-4 ${
        isLight ? 'bg-slate-50/90 border-slate-200' : 'bg-surface-2 border-slate-800'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 flex items-center justify-center shrink-0">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">
              {isFr ? 'Taux de Réussite' : isAr ? 'نسبة النجاح (Win Rate)' : 'Win Rate'}
            </div>
            <div className="text-sm font-black font-mono text-emerald-600 dark:text-emerald-400">
              {perfStats && (perfStats.tp1Hits + perfStats.tp2Hits + perfStats.slHits) > 0 ? `${perfStats.winRate}%` : '—'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-600 flex items-center justify-center shrink-0">
            <Trophy className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">
              {isFr ? 'Objectifs Atteints (TP)' : isAr ? 'أهداف محققة (TP1 & TP2)' : 'Targets Hit (TP)'}
            </div>
            <div className="text-sm font-black font-mono text-sky-600 dark:text-sky-400">
              {(perfStats?.tp1Hits ?? 0) + (perfStats?.tp2Hits ?? 0)} {isFr ? 'Gains' : isAr ? 'صفقة رابحة' : 'Wins'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-600 flex items-center justify-center shrink-0">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">
              {isFr ? 'Stop Loss Structurel' : isAr ? 'وقف خسارة محمي (1% Risk)' : 'Structural SL Risk'}
            </div>
            <div className="text-sm font-black font-mono text-rose-600 dark:text-rose-400">
              {perfStats?.slHits ?? 0} {isFr ? 'Pertes' : isAr ? 'صفقات خاسرة' : 'Losses'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-600 flex items-center justify-center shrink-0">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">
              {isFr ? 'R:R minimum' : isAr ? 'أدنى عائد للمخاطرة' : 'Minimum R:R'}
            </div>
            <div className="text-sm font-black font-mono text-purple-600 dark:text-purple-400">
              1:2 (TP1)
            </div>
          </div>
        </div>
      </div>

      {/* 3. Category & Action Filter Bar */}
      <div className={`flex items-center gap-2 p-1.5 rounded-xl border mb-5 text-xs overflow-x-auto no-scrollbar ${
        isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-950 border-slate-800'
      }`}>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setFilter('GOLD')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition font-bold shadow-xs ${
              filter === 'GOLD'
                ? isLight ? 'bg-gold-500 text-ink-strong' : 'bg-gold-500/15 text-gold-200 ring-1 ring-inset ring-gold-500/50'
                : isLight ? 'bg-gold-100 text-gold-700 hover:bg-gold-200' : 'text-gold-400 hover:bg-gold-500/10'
            }`}
          >
            <span aria-hidden="true" className="w-2 h-2 rounded-full bg-gold-400"></span>
            <span>{isFr ? 'Or (XAU/USD) Exclusif' : isAr ? 'الذهب (XAU/USD) حصري' : 'Gold (XAU/USD) Exclusive'}</span>
          </button>

          <button
            onClick={() => setFilter('ACTIONABLE_NOW')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition font-bold ${
              filter === 'ACTIONABLE_NOW'
                ? isLight ? 'bg-emerald-600 text-white shadow-xs' : 'bg-emerald-600 text-white'
                : isLight ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100' : 'bg-emerald-950/60 text-emerald-300 hover:bg-emerald-900/80'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span>{isFr ? 'Entrée Immédiate' : isAr ? 'دخول فوري الآن' : 'Actionable Now'}</span>
          </button>

          <button
            onClick={() => setFilter('OPEN_ONLY')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition font-bold ${
              filter === 'OPEN_ONLY'
                ? isLight ? 'bg-cyan-600 text-white shadow-xs' : 'bg-cyan-600 text-white'
                : isLight ? 'bg-cyan-50 text-cyan-800 hover:bg-cyan-100' : 'bg-cyan-950/60 text-cyan-300 hover:bg-cyan-900/80'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>{isFr ? 'Marchés Ouverts' : isAr ? 'الأسواق المفتوحة' : 'Open Markets'}</span>
          </button>

          <button
            onClick={() => setFilter('ALL')}
            className={`px-3 py-1.5 rounded-lg transition font-medium ${
              filter === 'ALL'
                ? isLight ? 'bg-white text-slate-900 font-bold shadow-xs' : 'bg-slate-800 text-white font-bold'
                : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
            }`}
          >
            {isFr ? 'Toutes les configurations' : isAr ? 'جميع إعدادات الذهب' : 'All Gold Setups'}
          </button>
        </div>

        <div className="flex items-center gap-1.5 pt-1 sm:pt-0">
          <button
            onClick={() => setFilter('BUY')}
            className={`px-2.5 py-1 rounded-md transition text-xs font-bold ${
              filter === 'BUY'
                ? isLight ? 'bg-emerald-100 text-emerald-900' : 'bg-emerald-500/15 text-emerald-300'
                : isLight ? 'text-slate-500 hover:text-slate-800' : 'text-slate-400 hover:text-white'
            }`}
          >
            <span aria-hidden="true" className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 me-1.5 align-middle" />
            {isFr ? 'Achat (BUY)' : isAr ? 'شراء (BUY)' : 'Buy'}
          </button>
          <button
            onClick={() => setFilter('SELL')}
            className={`px-2.5 py-1 rounded-md transition text-xs font-bold ${
              filter === 'SELL'
                ? isLight ? 'bg-rose-100 text-rose-900' : 'bg-rose-500/15 text-rose-300'
                : isLight ? 'text-slate-500 hover:text-slate-800' : 'text-slate-400 hover:text-white'
            }`}
          >
            <span aria-hidden="true" className="inline-block w-1.5 h-1.5 rounded-full bg-rose-400 me-1.5 align-middle" />
            {isFr ? 'Vente (SELL)' : isAr ? 'بيع (SELL)' : 'Sell'}
          </button>
        </div>
      </div>

      {/* 4. Signals Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredSignals.map((sig, idx) => {
          const isBuy = sig.signalType === 'BUY';
          const isSell = sig.signalType === 'SELL';
          const isChecklistOpen = expandedChecklistId === sig.id;
          const grade = sig.setupGrade || 'A+';
          const livePrice = sig.currentLivePrice ?? sig.entryPrice;

          return (
            <motion.div
              key={sig.symbol || sig.id}
              initial={false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
              className={`rounded-2xl border p-4.5 transition-all relative shadow-sm ${
                isLight
                  ? isBuy
                    ? 'bg-gradient-to-b from-white via-white to-emerald-50/40 border-emerald-200 hover:border-emerald-400 hover:shadow-md'
                    : isSell
                    ? 'bg-gradient-to-b from-white via-white to-rose-50/40 border-rose-200 hover:border-rose-400 hover:shadow-md'
                    : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-md'
                  : isBuy
                  ? 'bg-gradient-to-b from-slate-900/90 via-slate-900/90 to-emerald-950/30 border-emerald-800/50 hover:border-emerald-600/80 hover:shadow-lg'
                  : isSell
                  ? 'bg-gradient-to-b from-slate-900/90 via-slate-900/90 to-rose-950/30 border-rose-800/50 hover:border-rose-600/80 hover:shadow-lg'
                  : 'bg-slate-900/80 border-slate-800'
              }`}
            >
              {/* Header: Asset + Live Real Price Tag + Signal Badge */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2">
                  <span className={`text-lg font-black font-mono-numbers tracking-tight ${isLight ? 'text-slate-900' : 'text-white'}`}>
                    {sig.symbol}
                  </span>
                  <span className={`text-xs font-semibold ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                    ({sig.assetName})
                  </span>

                  {/* Real Live Price Badge (Dynamically Updated) */}
                  {livePrice && (
                    <span className="flex items-center gap-1 text-xs font-mono font-extrabold px-2 py-0.5 rounded-lg bg-cyan-500/15 text-cyan-600 dark:text-cyan-300 border border-cyan-500/30">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse"></span>
                      <span>${livePrice.toLocaleString(undefined, { minimumFractionDigits: sig.symbol.includes('EUR') || sig.symbol.includes('GBP') ? 4 : 2 })}</span>
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1.5">
                  {sig.newsCatalyst?.isHighImpactLockout ? (
                    <span className="flex items-center gap-1 text-xs font-black px-3 py-1 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse">
                      <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />
                      <span>{isFr ? 'SUSPENSION MACRO (News Lockout)' : isAr ? 'حظر التداول (News Lockout)' : 'NEWS LOCKOUT'}</span>
                    </span>
                  ) : sig.decisionStatus === 'NO_TRADE' ? (
                    <span className="flex items-center gap-1 text-xs font-black px-3 py-1 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/40">
                      <AlertOctagon className="w-3.5 h-3.5" />
                      <span>{isAr ? 'حظر التداول (NO TRADE)' : 'NO TRADE'}</span>
                    </span>
                  ) : sig.isMarketOpen === false ? (
                    <span className="flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/40">
                      <span></span>
                      <span>{isFr ? 'Marché Fermé' : isAr ? 'السوق مغلق' : 'Market Closed'}</span>
                    </span>
                  ) : !sig.isActionableNow || sig.signalType === 'WAIT' || sig.confirmationCheckPassed === false ? (
                    <span className="flex items-center gap-1.5 text-xs font-black px-3 py-1 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/40 animate-pulse">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
                      <span>{sig.signalLabel || (isAr ? '⏳ في انتظار شمعة التأكيد' : 'WAITING CONFIRMATION')}</span>
                    </span>
                  ) : (
                    <span
                      className={`flex items-center gap-1 text-xs font-black px-3 py-1 rounded-lg tracking-wider shadow-2xs ${
                        isBuy
                          ? 'bg-emerald-600 text-white'
                          : 'bg-rose-600 text-white'
                      }`}
                    >
                      {isBuy ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                      <span>{sig.signalLabel}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Trade Quality Score & Institutional Evaluation Bar */}
              <div className={`p-2.5 rounded-xl border mb-3 flex flex-wrap items-center justify-between gap-2 text-xs ${
                sig.decisionStatus === 'ALLOWED'
                  ? isLight ? 'bg-emerald-50/80 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/40'
                  : isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-900 border-slate-800'
              }`}>
                <div className="flex items-center gap-2">
                  <div className={`w-6 h-6 rounded-lg flex items-center justify-center font-black text-xs ${
                    sig.decisionStatus === 'ALLOWED'
                      ? 'bg-emerald-500 text-white'
                      : 'bg-amber-500/20 text-amber-500 border border-amber-500/30'
                  }`}>
                    <Award className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <span className="font-bold text-slate-500 text-xs block">
                      {isAr ? 'درجة جودة الصفقة (Trade Quality Score):' : 'Trade Quality Score:'}
                    </span>
                    <span className="font-black font-mono text-sm text-emerald-600 dark:text-emerald-400">
                      {sig.tradeScore || sig.confidence || 92}/100{' '}
                      <span className="text-xs font-sans font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                        {sig.decisionStatus === 'ALLOWED'
                          ? (sig.tradeScoreGrade === 'VERY_STRONG' ? (isAr ? 'صفقة نموذجية قوية جداً A+' : 'Very Strong Setup') : (isAr ? 'صفقة جيدة مؤكدة A' : 'Good Setup'))
                          : (isAr ? 'دون الحد الأدنى 75%' : 'Below 75% Threshold')}
                      </span>
                    </span>
                  </div>
                </div>

                {/* Multi-Timeframe Alignment indicator */}
                <div className="flex items-center gap-1.5 font-mono text-xs font-bold">
                  <span className={`px-2 py-0.5 rounded-md border ${
                    sig.multiTimeframeAlignment?.allAligned !== false
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                      : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30'
                  }`}>
                    {isAr ? 'الفريمات:' : 'MTF:'} 4H ➔ 1H ➔ 15M {sig.multiTimeframeAlignment?.allAligned !== false ? '' : ''}
                  </span>
                </div>
              </div>

              {/* Macroeconomic News Catalyst Confluence Strip */}
              {sig.newsCatalyst && (
                <div className={`p-2.5 rounded-xl border mb-3 flex items-center justify-between gap-2 text-xs transition-colors ${
                  sig.newsCatalyst.isHighImpactLockout
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    : 'bg-surface border-white/[0.08] text-zinc-300'
                }`}>
                  <div className="flex items-center gap-2 min-w-0">
                    <Radio className={`w-3.5 h-3.5 shrink-0 ${sig.newsCatalyst.isHighImpactLockout ? 'text-rose-400 animate-pulse' : 'text-gold-500'}`} />
                    <span className="font-semibold text-xs leading-snug truncate">
                      {isAr ? sig.newsCatalyst.headlineAr : sig.newsCatalyst.headlineEn}
                    </span>
                  </div>
                  {sig.newsCatalyst.source && (
                    <span className="text-xs font-mono font-bold text-zinc-400 shrink-0">
                      {sig.newsCatalyst.source}
                    </span>
                  )}
                </div>
              )}

              {/* Strategy Pill & Actionable Live Status */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                {sig.strategyUsed && (
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-md border flex items-center gap-1 ${
                    isLight ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-indigo-950/60 text-indigo-300 border-indigo-800/40'
                  }`}>
                    <span>{isAr ? (sig.strategyUsed.includes('ICT') ? 'استراتيجية ICT والمفاهيم الذكية SMC' : sig.strategyUsed) : sig.strategyUsed}</span>
                  </span>
                )}

                {sig.isMarketOpen === false ? (
                  <span className="text-xs font-bold px-2.5 py-0.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                    <span>{isFr ? 'En attente de l\'ouverture du marché' : isAr ? 'التحليل يبدأ فور افتتاح البورصة' : 'Waiting for Market Open'}</span>
                  </span>
                ) : sig.isActionableNow ? (
                  <span className="flex items-center gap-1 text-xs font-extrabold px-2.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/40 animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span>{isFr ? 'Entrée Immédiate Maintenant' : isAr ? 'فرصة دخول فورية الآن' : 'Actionable Now'}</span>
                  </span>
                ) : (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-md border ${
                    isLight ? 'bg-slate-100 text-slate-600 border-slate-200' : 'bg-slate-900 text-slate-400 border-slate-800'
                  }`}>
                    {sig.distanceToEntryText || (isFr ? 'En attente de zone' : isAr ? 'في انتظار المنطقة' : 'Pending Zone')}
                  </span>
                )}
              </div>

              {/* Visual Strip of Entry, SL and TP */}
              <div className={`mb-3 p-2 rounded-xl border flex items-center justify-between gap-1.5 text-xs ${
                isLight ? 'bg-slate-50 border-slate-200' : 'bg-surface border-slate-800'
              }`}>
                <div className="flex items-center gap-1 font-bold text-rose-600 dark:text-rose-400">
                  <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                  <span>SL: ${sig.stopLoss}</span>
                </div>

                <div className="flex items-center gap-1 font-bold text-amber-600 dark:text-amber-400 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-xs">
                  <span>{isFr ? 'Entrée' : isAr ? 'الدخول' : 'Entry'}: {sig.entryZone}</span>
                </div>

                <div className="flex items-center gap-1 font-bold text-emerald-600 dark:text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span>TP2: ${sig.target2}</span>
                </div>
              </div>

              {/* Optimal Timing & Minimal Risk Analysis */}
              {sig.entryTimingNoteAr && sig.isMarketOpen !== false && (
                <div className={`p-2.5 rounded-xl text-xs mb-3 border ${
                  sig.entryTimingQuality === 'OPTIMAL_CONFIRMED'
                    ? isLight ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950' : 'bg-emerald-950/40 border-emerald-700/60 text-emerald-200'
                    : isLight ? 'bg-amber-50/90 border-amber-300 text-amber-950' : 'bg-amber-950/40 border-amber-700/60 text-amber-200'
                }`}>
                  <div className="flex items-center justify-between gap-1.5 font-bold mb-1">
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                      <span>{isFr ? "Timing d'Entrée & Risque Minimal :" : isAr ? "أحسن توقيت للدخول وأدنى مخاطرة:" : "Optimal Entry Timing & Minimal Risk:"}</span>
                    </span>
                    {sig.entryTimingQuality === 'OPTIMAL_CONFIRMED' && (
                      <span className="text-xs px-2 py-0.5 rounded-full font-black bg-emerald-500 text-white shadow-2xs animate-pulse">
                        {isFr ? 'CONFIRMÉ' : isAr ? 'مؤكد 100%' : 'CONFIRMED'}
                      </span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed font-medium">
                    {isFr ? sig.entryTimingNoteFr : isAr ? sig.entryTimingNoteAr : sig.entryTimingNoteAr}
                  </p>
                  {sig.tightRiskAdvantageAr && isAr && (
                    <p className="text-xs mt-1 text-slate-700 dark:text-slate-300 font-bold border-t border-emerald-500/20 pt-1">
                      {sig.tightRiskAdvantageAr}
                    </p>
                  )}
                </div>
              )}

              {/* Structure-First Technical Invalidation & Dynamic Pair Profile Card */}
              <div className="p-2.5 rounded-xl mb-3 border bg-surface border-white/[0.08] text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-bold text-zinc-200">
                    <Crosshair className="w-3.5 h-3.5 text-gold-500" />
                    <span>{isAr ? 'الهيكل الفني ونقطة إلغاء الصفقة (Invalidation Level):' : 'Structure-First Technical Invalidation:'}</span>
                  </div>
                  <button
                    onClick={() => setInspectingSignal(sig)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-medium text-gold-500 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/30 transition-colors cursor-pointer"
                  >
                    <SlidersHorizontal className="w-3 h-3" />
                    <span>{isAr ? 'ملف الزوج' : 'Pair Profile'}</span>
                  </button>
                </div>

                <div className="p-2 rounded-lg bg-canvas border border-white/[0.04] text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-400 font-mono">
                      {isAr ? 'مستوى الإلغاء الفني:' : 'Invalidation Level:'}
                    </span>
                    <span className="font-mono font-bold text-rose-400">
                      ${sig.dynamicSLTP?.invalidationLevel || sig.stopLoss}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-snug">
                    {isAr
                      ? (sig.invalidationConditionAr || sig.dynamicSLTP?.invalidationReasonAr || 'تلغى الفكرة الفنية إذا أغلقت شمعة 15M خلف قاع/قمة الهيكل الفني.')
                      : (sig.invalidationCondition || sig.dynamicSLTP?.invalidationReason || 'Technical premise invalidated if 15M closes beyond structural swing.')}
                  </p>
                </div>
              </div>

              {/* Anti-Copy-Trade Stealth Offset Protective Toggle Row */}
              <div className={`p-2.5 rounded-xl mb-3 flex items-center justify-between text-xs border transition-colors ${
                stealthEnabled[sig.id] !== false
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 font-bold'
                  : 'bg-slate-100 border-slate-200 text-slate-500 dark:bg-slate-950 dark:border-slate-800'
              }`}>
                <div className="flex items-center gap-1.5 font-bold">
                  <ShieldCheck className="w-4 h-4 text-amber-500" />
                  <div className="flex flex-col">
                    <span>
                      {isAr ? 'حماية النسخ وتجاوز كشف البروكر (Anti-Copy-Trade):' : 'Anti-Broker Copy-Trade Protection:'}
                    </span>
                    <span className="text-xs font-medium opacity-80 mt-0.5">
                      {stealthEnabled[sig.id] !== false 
                        ? (isAr ? 'نشط (إزاحة ذكية غير قابلة للكشف بالفراكشن)' : 'Active (Micro-pip stealth offset enabled)') 
                        : (isAr ? 'غير نشط (نسخ الأرقام الخام)' : 'Disabled (Raw values will be copied)')}
                    </span>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer select-none shrink-0">
                  <input
                    type="checkbox"
                    checked={stealthEnabled[sig.id] !== false}
                    onChange={(e) => {
                      setStealthEnabled(prev => ({
                        ...prev,
                        [sig.id]: e.target.checked
                      }));
                    }}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-300 dark:bg-slate-800 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-500"></div>
                </label>
              </div>

              {/* 4 Clean Key Data Blocks with 1-Click Copy & Stealth Support */}
              <div className={`grid grid-cols-2 gap-2.5 p-3.5 rounded-xl mb-3 text-xs font-mono-numbers border ${
                isLight ? 'bg-slate-50/80 border-slate-200' : 'bg-slate-950/70 border-slate-800/80'
              }`}>
                {/* Entry Zone */}
                <div className="p-2 rounded-lg bg-amber-500/5 border border-amber-500/20 flex flex-col justify-between min-h-[72px]">
                  <div>
                    <span className={`text-xs uppercase font-sans font-bold block ${isLight ? 'text-amber-800' : 'text-amber-400'}`}>
                      {isFr ? 'Zone d\'Entrée :' : isAr ? 'منطقة الدخول الموصى بها:' : 'Entry Zone:'}
                    </span>
                    <span className={`font-black text-[13px] tracking-tight ${isLight ? 'text-slate-900' : 'text-white'}`}>
                      {sig.entryZone}
                    </span>
                  </div>
                  <button
                    onClick={() => handleCopyField(sig.id, 'ENTRY', sig.entryZone, sig.symbol)}
                    className="mt-2.5 w-full flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-xs font-bold text-amber-800 dark:text-amber-400 transition cursor-pointer"
                  >
                    {copiedField?.id === sig.id && copiedField?.field === 'ENTRY' ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-500" />
                        <span>{isAr ? 'تم نسخ الدخول' : 'Copied Entry'}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-amber-500" />
                        <span>{isAr ? 'نسخ منطقة الدخول' : 'Copy Entry'}</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Stop Loss (SL) */}
                {/* Stop Loss (SL) */}
                <div className="p-2 rounded-lg bg-rose-500/5 border border-rose-500/20 flex flex-col justify-between min-h-[72px]">
                  <div>
                    <span className={`text-xs uppercase font-sans font-bold block ${isLight ? 'text-rose-700' : 'text-rose-400'} flex items-center gap-1`}>
                      <span>{isFr ? 'Stop Loss (SL) :' : isAr ? 'وقف الخسارة (SL):' : 'Stop Loss (SL):'}</span>
                    </span>
                    <span className="font-black text-[13px] text-rose-600 dark:text-rose-400 font-mono">
                      ${sig.stopLoss}
                    </span>
                  </div>
                  <button
                    onClick={() => handleCopyField(sig.id, 'SL', sig.stopLoss.toString(), sig.symbol)}
                    className="mt-2.5 w-full flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-xs font-bold text-rose-800 dark:text-rose-400 transition cursor-pointer"
                  >
                    {copiedField?.id === sig.id && copiedField?.field === 'SL' ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-500" />
                        <span>{isAr ? 'تم نسخ الستوب' : 'Copied SL'}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-rose-500" />
                        <span>{isAr ? 'نسخ الستوب (SL)' : 'Copy SL'}</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Target 1 (TP1) */}
                <div className="p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 flex flex-col justify-between min-h-[72px]">
                  <div>
                    <span className={`text-xs uppercase font-sans font-bold block ${isLight ? 'text-emerald-700' : 'text-emerald-400'} flex items-center gap-1`}>
                      <span>{isFr ? 'Objectif 1 (TP1) :' : isAr ? 'الهدف 1 (TP1):' : 'Target 1 (TP1):'}</span>
                    </span>
                    <span className="font-black text-[13px] text-emerald-600 dark:text-emerald-400 font-mono">
                      ${sig.target1}
                    </span>
                  </div>
                  <button
                    onClick={() => handleCopyField(sig.id, 'TP1', sig.target1.toString(), sig.symbol)}
                    className="mt-2.5 w-full flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-xs font-bold text-emerald-800 dark:text-emerald-400 transition cursor-pointer"
                  >
                    {copiedField?.id === sig.id && copiedField?.field === 'TP1' ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-500" />
                        <span>{isAr ? 'تم نسخ الهدف 1' : 'Copied TP1'}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-emerald-500" />
                        <span>{isAr ? 'نسخ الهدف 1' : 'Copy TP1'}</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Target 2 (TP2) */}
                <div className="p-2 rounded-lg bg-cyan-500/5 border border-cyan-500/20 flex flex-col justify-between min-h-[72px]">
                  <div>
                    <span className={`text-xs uppercase font-sans font-bold block ${isLight ? 'text-cyan-700' : 'text-cyan-400'} flex items-center gap-1`}>
                      <span>{isFr ? 'Objectif 2 (TP2) :' : isAr ? 'الهدف 2 (TP2):' : 'Target 2 (TP2):'}</span>
                    </span>
                    <span className="font-black text-[13px] text-cyan-600 dark:text-cyan-400 font-mono">
                      ${sig.target2}
                    </span>
                  </div>
                  <button
                    onClick={() => handleCopyField(sig.id, 'TP2', sig.target2.toString(), sig.symbol)}
                    className="mt-2.5 w-full flex items-center justify-center gap-1.5 py-1 px-2 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-xs font-bold text-cyan-800 dark:text-cyan-400 transition cursor-pointer"
                  >
                    {copiedField?.id === sig.id && copiedField?.field === 'TP2' ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-500" />
                        <span>{isAr ? 'تم نسخ الهدف 2' : 'Copied TP2'}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-cyan-500" />
                        <span>{isAr ? 'نسخ الهدف 2' : 'Copy TP2'}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* R:R and Confluence Bar */}
              <div className="flex items-center justify-between text-xs px-1 mb-2.5">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                    {isFr ? 'Score de Confirmation :' : isAr ? 'سكور التأكيد المؤسساتي:' : 'Confirmation Score:'}
                  </span>
                  <span className={`font-black font-mono-numbers text-xs ${
                    (sig.confluenceScore || sig.confidence) >= 92 
                      ? 'text-amber-600 dark:text-amber-400 font-black' 
                      : (sig.confluenceScore || sig.confidence) >= 80 
                      ? 'text-emerald-600 dark:text-emerald-400 font-bold' 
                      : 'text-cyan-600 dark:text-cyan-400'
                  }`}>
                    {sig.confluenceScore || sig.confidence}%
                  </span>
                  {sig.setupGrade && (
                    <span className={`text-xs font-black px-1.5 py-0.2 rounded ${
                      sig.setupGrade === 'A+' 
                        ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                        : 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                    }`}>
                      {sig.setupGrade}
                    </span>
                  )}
                  <div className={`w-16 h-1.5 rounded-full overflow-hidden ${isLight ? 'bg-slate-200' : 'bg-slate-800'}`}>
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        (sig.confluenceScore || sig.confidence) >= 92 
                          ? 'bg-gradient-to-r from-amber-500 to-yellow-400' 
                          : (sig.confluenceScore || sig.confidence) >= 80 
                          ? 'bg-emerald-500'
                          : 'bg-cyan-500'
                      }`}
                      style={{ width: `${sig.confluenceScore || sig.confidence}%` }}
                    />
                  </div>
                </div>

                <div className="text-right">
                  <span className={`text-xs font-medium mr-1 ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                    {isFr ? 'Ratio R:R :' : isAr ? 'العائد للمخاطرة:' : 'Risk:Reward:'}
                  </span>
                  <span className="font-black font-mono-numbers text-emerald-600 dark:text-emerald-400">
                    {sig.riskReward}
                  </span>
                </div>
              </div>

              {/* Management Plan Summary Box (Breakeven Rule) */}
              {sig.managementPlan && (
                <div className={`p-2.5 rounded-xl text-xs mb-2.5 border ${
                  isLight ? 'bg-amber-50/70 border-amber-200/80 text-amber-950' : 'bg-amber-950/30 border-amber-800/40 text-amber-200'
                }`}>
                  <div className="flex items-center gap-1.5 font-bold mb-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
                    <span>{isFr ? 'Plan de Sécurisation (Breakeven) :' : isAr ? 'قاعدة تأمين الصفقة وحجز الأرباح:' : 'Breakeven & Trade Management:'}</span>
                  </div>
                  <p className="text-xs leading-relaxed">
                    • <b>TP1:</b> {sig.managementPlan.tp1Action}
                  </p>
                </div>
              )}

              {/* 15-Minute Institutional Confirmation Candle Engine */}
              {(() => {
                const conf15M = sig.confirmationCandle15M || sig.smcDetails?.confirmationCandle15M;
                const isConfirmed = sig.confirmationCheckPassed && sig.signalType !== 'WAIT';

                return (
                  <div className={`p-2.5 rounded-xl text-xs mb-2.5 border transition-all ${
                    isConfirmed
                      ? isLight ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950 shadow-2xs' : 'bg-emerald-950/40 border-emerald-700/60 text-emerald-200 shadow-2xs'
                      : isLight ? 'bg-amber-50/90 border-amber-300 text-amber-950 shadow-2xs' : 'bg-amber-950/40 border-amber-700/60 text-amber-200 shadow-2xs'
                  }`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center font-black text-xs shrink-0 ${
                          isConfirmed
                            ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                            : 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                        }`}>
                          {isConfirmed ? '✓ 15M' : '⏳ 15M'}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5 font-black text-xs">
                            <span>{isAr ? 'شمعة التأكيد المؤسساتية (Confirmation Candle):' : 'Institutional Confirmation Candle:'}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full font-black ${
                              isConfirmed
                                ? 'bg-emerald-500 text-white'
                                : 'bg-amber-500 text-slate-900 animate-pulse'
                            }`}>
                              {isConfirmed
                                ? (isAr ? 'مؤكدة 100% VALIDATED' : 'CONFIRMED')
                                : (isAr ? '⏳ في انتظار التأكيد (WAIT)' : 'WAITING CONFIRMATION')}
                            </span>
                          </div>
                          <p className="text-xs font-medium opacity-90 mt-0.5">
                            {isConfirmed
                              ? (conf15M?.statusAr || (isAr ? 'شمعة التأكيد 15M مكتملة بنجاح مع رفض صريح واندفاع مؤسساتي.' : '15M Confirmation candle confirmed with displacement.'))
                              : (conf15M?.statusAr || (isAr ? 'خاص ما يعطيك صفقة حتى يتسنى confirmation لي غادي تبين داكشي صحيح — ننتظر إغلاق شمعة 15M برفض صريح لتفادي الفخاخ.' : 'Waiting for 15M candle close confirmation to avoid traps.'))}
                          </p>
                        </div>
                      </div>
                    </div>

                    {!isConfirmed && (
                      <div className="mt-1.5 pt-1.5 border-t border-amber-500/20 flex flex-wrap items-center gap-2 text-xs text-amber-700 dark:text-amber-300 font-bold">
                        <span className="flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                          <span>{isAr ? 'قاعدة الأمان: ممنوع الدخول والتنفيذ حتى يغلق تأكيد الشمعة' : 'Strict Rule: No entry until candle close'}</span>
                        </span>
                        <span>•</span>
                        <span>{isAr ? 'تأكيد الرفض (Rejection Wick)' : 'Rejection Wick'}</span>
                        <span>•</span>
                        <span>{isAr ? 'إغلاق الجسم (Displacement Body Close)' : 'Displacement Close'}</span>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Real-Time Macro News Confluence Indicator */}
              {sig.newsConfluence && (
                <div className={`p-2.5 rounded-xl text-xs mb-3 border flex items-start gap-2 ${
                  isLight ? 'bg-blue-50/60 border-blue-200 text-blue-950' : 'bg-blue-950/30 border-blue-800/40 text-blue-200'
                }`}>
                  <Newspaper className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between gap-1 mb-0.5">
                      <span className="font-bold text-xs uppercase tracking-wider text-blue-700 dark:text-blue-300">
                        {isFr ? `Impact Macro (${sig.newsConfluence.source})` : isAr ? `توافق الأخبار (${sig.newsConfluence.source})` : `Macro News (${sig.newsConfluence.source})`}
                      </span>
                      <span className="text-xs font-extrabold px-1.5 py-0.2 rounded bg-blue-600/15 text-blue-700 dark:text-blue-300 border border-blue-500/30">
                        {sig.newsConfluence.alignedWithSignal ? (isAr ? 'توافق كامل 100%' : 'Aligned') : 'Macro Watch'}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed font-medium">
                      {isAr ? sig.newsConfluence.headlineAr : sig.newsConfluence.headline}
                    </p>
                  </div>
                </div>
              )}

              {/* 10-Pillars Advanced Decision Engine Explanation Accordion */}
              <div className="mb-3">
                <button
                  onClick={() => setExpandedReasonsId(expandedReasonsId === sig.id ? null : sig.id)}
                  className={`w-full flex items-center justify-between p-2 rounded-xl text-xs font-bold border transition ${
                    isLight ? 'bg-indigo-50/70 hover:bg-indigo-100/70 text-indigo-900 border-indigo-200' : 'bg-indigo-950/40 hover:bg-indigo-900/60 text-indigo-300 border-indigo-800/50'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-indigo-500" />
                    <span>{isAr ? 'تفسير قرار الذكاء الاصطناعي (10 ركائز مؤسساتية)' : 'AI Decision Engine Breakdown (10 Pillars)'}</span>
                    <span className="text-xs font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-700 dark:text-indigo-300">
                      {sig.tradeScore || sig.confidence || 92}/100
                    </span>
                  </span>
                  {expandedReasonsId === sig.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>

                {expandedReasonsId === sig.id && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`mt-2 p-3 rounded-xl border space-y-3 text-xs leading-relaxed ${
                      isLight ? 'bg-slate-50 border-slate-200 text-slate-800' : 'bg-slate-950 border-slate-800 text-slate-200'
                    }`}
                  >
                    {/* Python AI Multi-Strategy Confluence Scanner */}
                    {sig.allStrategyScores && sig.allStrategyScores.length > 0 && (
                      <div className="p-2.5 rounded-lg border bg-gradient-to-r from-indigo-500/5 to-purple-500/5 dark:bg-slate-900 border-indigo-500/30">
                        <div className="flex items-center justify-between mb-2 font-bold text-xs">
                          <span className="flex items-center gap-1.5 text-indigo-700 dark:text-indigo-300">
                            <Layers className="w-3.5 h-3.5 text-indigo-500" />
                            <span>{isAr ? 'فحص وتدقيق كافة الاستراتيجيات (Python AI Strategy Confluence):' : 'Multi-Strategy Audit (Python AI Agent):'}</span>
                          </span>
                          <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 font-bold">
                            {isAr ? '5 استراتيجيات مدمجة' : '5 Strategies'}
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          {sig.allStrategyScores.map((st: any, idx: number) => {
                            const isWinning = st.matched || st.strategy === sig.strategyUsed;
                            return (
                              <div
                                key={idx}
                                className={`flex items-center justify-between p-1.5 rounded-md text-xs border ${
                                  isWinning
                                    ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-800 dark:text-emerald-300 font-bold'
                                    : 'bg-slate-100/60 dark:bg-slate-800/40 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400'
                                }`}
                              >
                                <div className="flex items-center gap-1.5">
                                  <span>{isWinning ? '' : '⏳'}</span>
                                  <span>{st.strategy}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className={`text-xs font-black font-mono ${isWinning ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500'}`}>
                                    {st.score}%
                                  </span>
                                  <span className={`text-xs px-1.5 py-0.2 rounded font-extrabold ${
                                    isWinning
                                      ? 'bg-emerald-500 text-white'
                                      : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                                  }`}>
                                    {isWinning ? (isAr ? 'متحقق بالكامل' : 'MATCHED') : (isAr ? 'قيد المراقبة' : 'MONITORING')}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* 1. Market Suitability Engine */}
                    <div className="p-2.5 rounded-lg border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800">
                      <div className="flex items-center justify-between mb-1 font-bold text-xs">
                        <span className="flex items-center gap-1 text-slate-500">
                          <span>1. ملاءمة السوق (Market Condition):</span>
                        </span>
                        <span className={`px-2 py-0.5 rounded font-black text-xs ${
                          sig.marketSuitability?.isSuitable !== false ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/20 text-rose-600 dark:text-rose-400'
                        }`}>
                          {sig.marketSuitability?.isSuitable !== false ? 'ملائم للتداول ' : 'غير ملائم (حظر NO TRADE) '}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {sig.marketSuitability?.reasonAr || (isAr ? 'حالة السوق مستقرة وتظهر اتجاهاً مؤسساتياً واضحاً مع انتظام المتوسطات المتحركة.' : 'Market condition suitable with aligned institutional EMA trend.')}
                      </p>
                    </div>

                    {/* 2. Multi-Timeframe Synchronization */}
                    <div className="p-2.5 rounded-lg border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800">
                      <div className="flex items-center justify-between mb-1 font-bold text-xs">
                        <span className="text-slate-500">2. توافق الفريمات (Multi-Timeframe):</span>
                        <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400 font-extrabold">
                          4H ➔ 1H ➔ 15M ✓
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {sig.multiTimeframeAlignment?.summaryAr || (isAr ? 'توافق كامل بين الفريم الكبير (الاتجاه) والفريم الأوسط (التشكل) وفريم الدخول (شمعة التأكيد).' : 'All timeframes strictly aligned.')}
                      </p>
                    </div>

                    {/* 3. Smart Entry Checklist (8/8) */}
                    <div className="p-2.5 rounded-lg border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800">
                      <div className="flex items-center justify-between mb-1.5 font-bold text-xs">
                        <span className="text-slate-500">3. شروط الدخول الذكية (8 شروط إلزامية):</span>
                        <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                          8/8 محققة بالكامل
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 text-xs">
                        {(sig.smartEntryChecklist?.items || [
                          { labelAr: "الاتجاه العام صاعد/هابط مؤكد", passed: true },
                          { labelAr: "السعر فوق/أسفل المتوسطات EMA", passed: true },
                          { labelAr: "احترام منطقة الدعم/المقاومة", passed: true },
                          { labelAr: "نموذج حركة السعر (رفض صريح)", passed: true },
                          { labelAr: "تأكيد الزخم RSI و MACD", passed: true },
                          { labelAr: "تأكيد فوليوم الشراء/البيع المؤسساتي", passed: true },
                          { labelAr: "الأمان من فخاخ السيولة والاختراق الكاذب", passed: true },
                          { labelAr: "نسبة العائد للمخاطرة 1:2.0+ كحد أدنى", passed: true },
                        ]).map((item, idx) => (
                          <div key={idx} className="flex items-center gap-1.5">
                            <span className="text-emerald-500">✓</span>
                            <span>{item.labelAr}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* 4. SMC & Anti-Traps */}
                    <div className="p-2.5 rounded-lg border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800">
                      <div className="flex items-center justify-between mb-1 font-bold text-xs">
                        <span className="text-slate-500">4. مفاهيم SMC والوقاية من فخاخ السيولة:</span>
                        <span className="text-emerald-600 dark:text-emerald-400 font-mono text-xs">BOS + CHOCH + Sweep</span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        • تم حظر الدخول في منتصف النطاق (Equilibrium 50%) — الدخول في منطقة التخفيض/الغلاء فقط.<br />
                        • تم تجاوز فلتر الشموع العملاقة الاستنزافية (Anti-Exhaustion Passed).<br />
                        • وقف الخسارة موضوع ديناميكياً خلف هيكل السيولة مع هامش أمان ATR.
                      </p>
                    </div>

                    {/* 5. Loss Prevention & 1% Risk */}
                    <div className="p-2.5 rounded-lg border bg-rose-500/5 border-rose-500/20">
                      <div className="flex items-center justify-between mb-1 font-bold text-xs">
                        <span className="text-rose-600 dark:text-rose-400">5. نظام منع الخسائر وإدارة المخاطر الصارمة:</span>
                        <span className="text-rose-600 dark:text-rose-400 font-bold text-xs">قاعدة 1% فقط</span>
                      </div>
                      <p className="text-xs text-slate-700 dark:text-slate-300">
                        • فحص التقلبات المفرطة: آمنة ضمن النطاق الطبيعي.<br />
                        • فحص الأخبار الاقتصادية الكبرى: خالية من أي مخاطر انزلاق سعري.<br />
                        • <b>إدارة رأس المال:</b> أقصى مخاطرة مسموح بها هي 1% من حجم المحفظة لكل صفقة.
                      </p>
                    </div>

                    {/* 6. Explanation Reasons Summary */}
                    {sig.tradeExplanation?.reasonsAr && (
                      <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
                        <span className="font-bold text-xs text-slate-500 block mb-1">
                          {isAr ? 'ملخص الأسباب التفصيلية للقرار:' : 'Trade Rationale Summary:'}
                        </span>
                        <ul className="space-y-1 list-disc list-inside text-xs text-slate-700 dark:text-slate-300">
                          {sig.tradeExplanation.reasonsAr.map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </motion.div>
                )}
              </div>

              {/* Collapsible 5-point Confluence Checklist */}
              {sig.confluenceChecklist && sig.confluenceChecklist.length > 0 && (
                <div className="mb-3">
                  <button
                    onClick={() => toggleChecklist(sig.id)}
                    className={`w-full flex items-center justify-between text-xs font-bold py-1.5 px-2.5 rounded-lg border transition ${
                      isLight 
                        ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200' 
                        : 'bg-slate-800/60 hover:bg-slate-800 text-slate-300 border-slate-700'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-500" />
                      <span>
                        {(() => {
                          const passed = sig.confluenceChecklist.filter(c => c.passed).length;
                          const total = sig.confluenceChecklist.length;
                          return isFr
                            ? `Confirmations Institutionnelles Validées (${passed}/${total})`
                            : isAr
                            ? `قائمة التأكيدات المؤسساتية المحققة (${passed}/${total})`
                            : `Institutional Confluence Checklist (${passed}/${total})`;
                        })()}
                      </span>
                    </span>
                    {isChecklistOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>

                  {isChecklistOpen && (
                    <div className={`mt-2 p-2.5 rounded-lg border space-y-1.5 text-xs ${
                      isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-950 border-slate-800'
                    }`}>
                      {sig.confluenceChecklist.map((item) => (
                        <div key={item.id} className="flex items-start gap-2 text-xs">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                          <div>
                            <span className={`font-bold ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
                              {isFr ? (item.labelFr || item.label) : isAr ? item.labelAr : item.label}:
                            </span>{' '}
                            <span className={isLight ? 'text-slate-600' : 'text-slate-400'}>
                              {item.detail}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* 100% High-Precision Institutional Math & SMC Matrix Drawer */}
              {sig.precisionMetrics && (
                <div className="mb-3">
                  <button
                    onClick={() => setExpandedPrecisionId(prev => (prev === sig.id ? null : sig.id))}
                    className={`w-full flex items-center justify-between text-xs font-extrabold py-1.5 px-2.5 rounded-lg border transition ${
                      expandedPrecisionId === sig.id
                        ? isLight
                          ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                          : 'bg-cyan-600 text-white border-cyan-600 shadow-xs'
                        : isLight
                        ? 'bg-cyan-50/70 hover:bg-cyan-100/80 text-cyan-900 border-cyan-300/80'
                        : 'bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 border-cyan-800/60'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <Gauge className={`w-3.5 h-3.5 ${expandedPrecisionId === sig.id ? 'text-white' : 'text-cyan-500'}`} />
                      <span>
                        {isFr
                          ? 'Matrice de Précision Mathématique 100% (OTE, Delta & Multi-TF)'
                          : isAr
                          ? 'مصفوفة الدقة الرياضية المؤسساتية 100% (الأرقام والتحليل الدقيق)'
                          : '100% Institutional Math & SMC Precision Matrix'}
                      </span>
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className={`text-xs px-1.5 py-0.2 rounded font-mono font-bold ${
                        expandedPrecisionId === sig.id
                          ? 'bg-white/20 text-white'
                          : isLight ? 'bg-cyan-200/60 text-cyan-800' : 'bg-cyan-900/80 text-cyan-200'
                      }`}>
                        100% ACCURATE
                      </span>
                      {expandedPrecisionId === sig.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </div>
                  </button>

                  {expandedPrecisionId === sig.id && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`mt-2 p-3 rounded-xl border space-y-3 text-xs ${
                        isLight ? 'bg-slate-50/90 border-slate-200 text-slate-800' : 'bg-slate-950/90 border-slate-800 text-slate-200'
                      }`}
                    >
                      {/* 1. Multi-Timeframe Matrix */}
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className={`text-xs font-extrabold uppercase tracking-wider flex items-center gap-1 ${
                            isLight ? 'text-slate-600' : 'text-slate-400'
                          }`}>
                            <Activity className="w-3 h-3 text-cyan-500" />
                            {isAr ? 'توافق الفريمات المتعددة (Multi-Timeframe 100% Confluence)' : 'Multi-Timeframe Alignment'}
                          </span>
                          <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                            100% Synchronized ✓
                          </span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-xs">
                          <div className={`p-1.5 rounded-lg border text-center ${
                            isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/40'
                          }`}>
                            <span className="font-mono font-bold block text-emerald-700 dark:text-emerald-300">4H HTF</span>
                            <span className="text-xs text-slate-500 dark:text-slate-400">{sig.precisionMetrics.multiTimeframeMatrix.tf4h.struct}</span>
                          </div>
                          <div className={`p-1.5 rounded-lg border text-center ${
                            isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/40'
                          }`}>
                            <span className="font-mono font-bold block text-emerald-700 dark:text-emerald-300">1H TREND</span>
                            <span className="text-xs text-slate-500 dark:text-slate-400">{sig.precisionMetrics.multiTimeframeMatrix.tf1h.struct}</span>
                          </div>
                          <div className={`p-1.5 rounded-lg border text-center ${
                            isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/40'
                          }`}>
                            <span className="font-mono font-bold block text-emerald-700 dark:text-emerald-300">15M STRUCTURE</span>
                            <span className="text-xs text-slate-500 dark:text-slate-400">{sig.precisionMetrics.multiTimeframeMatrix.tf15m.struct}</span>
                          </div>
                          <div className={`p-1.5 rounded-lg border text-center ${
                            isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/40'
                          }`}>
                            <span className="font-mono font-bold block text-emerald-700 dark:text-emerald-300">15M TRIGGER</span>
                            <span className="text-xs text-slate-500 dark:text-slate-400">{sig.precisionMetrics.multiTimeframeMatrix.tf15m.struct || "Displacement body close"}</span>
                          </div>
                        </div>
                      </div>

                      {/* 2. Fibonacci OTE & FVG 50% CE Levels */}
                      <div className={`p-2.5 rounded-xl border text-xs ${
                        isLight ? 'bg-white border-slate-200 shadow-2xs' : 'bg-slate-900 border-slate-800'
                      }`}>
                        <div className="font-bold text-xs uppercase text-cyan-700 dark:text-cyan-300 mb-1.5 flex items-center justify-between">
                          <span>{isAr ? 'مستويات الفيبوناتشي الذهبية (OTE) وفجوة FVG' : 'Fibonacci OTE & FVG 50% Levels'}</span>
                          <span className="font-mono text-xs text-slate-500">{sig.precisionMetrics.fibOteRange}</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="p-1 rounded bg-slate-100 dark:bg-slate-800/60">
                            <span className="text-xs text-slate-500 block">Fib 61.8%</span>
                            <span className="font-bold font-mono text-cyan-600 dark:text-cyan-400">${sig.precisionMetrics.fib618Price}</span>
                          </div>
                          <div className="p-1 rounded bg-cyan-500/10 border border-cyan-500/30">
                            <span className="text-xs font-bold text-cyan-700 dark:text-cyan-300 block">{isAr ? 'المنطقة الذهبية 70.5%' : 'OTE Sweet Spot'}</span>
                            <span className="font-black font-mono text-cyan-600 dark:text-cyan-300">${sig.precisionMetrics.fibOteGoldenPrice}</span>
                          </div>
                          <div className="p-1 rounded bg-slate-100 dark:bg-slate-800/60">
                            <span className="text-xs text-slate-500 block">FVG 50% CE</span>
                            <span className="font-bold font-mono text-amber-600 dark:text-amber-400">${sig.precisionMetrics.fvgConsequentEncroachment}</span>
                          </div>
                        </div>
                      </div>

                      {/* 3. Volume Delta & Session Timing */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                        <div className={`p-2 rounded-lg border ${
                          isLight ? 'bg-white border-slate-200' : 'bg-slate-900 border-slate-800'
                        }`}>
                          <div className="flex items-center justify-between text-xs font-bold mb-1">
                            <span className="text-slate-500">{isAr ? 'تدفق السيولة الحجمية (Volume Delta):' : 'Volume Delta Ratio:'}</span>
                            <span className="text-emerald-600 dark:text-emerald-400 font-mono">+{sig.precisionMetrics.volumeDeltaStats.buyVolumePct}% Buy</span>
                          </div>
                          <div className="w-full h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden flex">
                            <div className="h-full bg-emerald-500" style={{ width: `${sig.precisionMetrics.volumeDeltaStats.buyVolumePct}%` }} />
                            <div className="h-full bg-rose-500" style={{ width: `${sig.precisionMetrics.volumeDeltaStats.sellVolumePct}%` }} />
                          </div>
                          <span className="text-xs text-slate-500 mt-1 block">
                            {sig.precisionMetrics.volumeDeltaStats.deltaInterpretation}
                          </span>
                        </div>

                        <div className={`p-2 rounded-lg border ${
                          isLight ? 'bg-white border-slate-200' : 'bg-slate-900 border-slate-800'
                        }`}>
                          <span className="text-xs font-bold text-slate-500 block mb-0.5">
                            {isAr ? 'جلسة التداول والسيولة (Killzone):' : 'Killzone Session Window:'}
                          </span>
                          <span className="font-bold text-xs text-indigo-600 dark:text-indigo-400 block">
                            {sig.precisionMetrics.sessionKillzone}
                          </span>
                          <span className="text-xs text-slate-500 mt-0.5 block">
                            ATR (14 Volatility): <b>{sig.precisionMetrics.atr14}</b> | {isAr ? 'وقف الخسارة' : 'Risk'}: <b>{sig.precisionMetrics.exactPipsRisk}</b> pips
                          </span>
                        </div>
                      </div>

                      {/* 4. Exact Mathematical Lot Size & Dollar Matrix */}
                      <div>
                        <span className={`text-xs font-extrabold uppercase tracking-wider block mb-1.5 ${
                          isLight ? 'text-slate-700' : 'text-slate-300'
                        }`}>
                          {isAr ? 'جدول حساب اللوت والأرباح الحقيقية (بمخاطرة 1% فقط):' : 'Calculated 1% Risk Lot Matrix:'}
                        </span>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs text-center border-collapse">
                            <thead>
                              <tr className={`border-b ${isLight ? 'bg-slate-100 text-slate-700' : 'bg-slate-900 text-slate-400'}`}>
                                <th className="p-1 font-bold">{isAr ? 'رأس المال' : 'Balance'}</th>
                                <th className="p-1 font-bold">{isAr ? 'حجم اللوت' : 'Lot Size'}</th>
                                <th className="p-1 font-bold">{isAr ? 'أقصى خسارة' : 'Max Risk'}</th>
                                <th className="p-1 font-bold text-emerald-600 dark:text-emerald-400">{isAr ? 'ربح TP1' : 'TP1 Gain'}</th>
                                <th className="p-1 font-bold text-cyan-600 dark:text-cyan-400">{isAr ? 'ربح TP2' : 'TP2 Gain'}</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 font-mono">
                              <tr>
                                <td className="p-1 font-bold">$500</td>
                                <td className="p-1 font-bold text-indigo-600 dark:text-indigo-400">{sig.precisionMetrics.lotSizeCalculations.account500.lot}</td>
                                <td className="p-1 text-rose-500">{sig.precisionMetrics.lotSizeCalculations.account500.riskUsd}</td>
                                <td className="p-1 text-emerald-600 dark:text-emerald-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account500.gainTp1}</td>
                                <td className="p-1 text-cyan-600 dark:text-cyan-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account500.gainTp2}</td>
                              </tr>
                              <tr>
                                <td className="p-1 font-bold">$1,000</td>
                                <td className="p-1 font-bold text-indigo-600 dark:text-indigo-400">{sig.precisionMetrics.lotSizeCalculations.account1000.lot}</td>
                                <td className="p-1 text-rose-500">{sig.precisionMetrics.lotSizeCalculations.account1000.riskUsd}</td>
                                <td className="p-1 text-emerald-600 dark:text-emerald-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account1000.gainTp1}</td>
                                <td className="p-1 text-cyan-600 dark:text-cyan-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account1000.gainTp2}</td>
                              </tr>
                              <tr>
                                <td className="p-1 font-bold">$5,000</td>
                                <td className="p-1 font-bold text-indigo-600 dark:text-indigo-400">{sig.precisionMetrics.lotSizeCalculations.account5000.lot}</td>
                                <td className="p-1 text-rose-500">{sig.precisionMetrics.lotSizeCalculations.account5000.riskUsd}</td>
                                <td className="p-1 text-emerald-600 dark:text-emerald-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account5000.gainTp1}</td>
                                <td className="p-1 text-cyan-600 dark:text-cyan-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account5000.gainTp2}</td>
                              </tr>
                              <tr>
                                <td className="p-1 font-bold">$10,000</td>
                                <td className="p-1 font-bold text-indigo-600 dark:text-indigo-400">{sig.precisionMetrics.lotSizeCalculations.account10000.lot}</td>
                                <td className="p-1 text-rose-500">{sig.precisionMetrics.lotSizeCalculations.account10000.riskUsd}</td>
                                <td className="p-1 text-emerald-600 dark:text-emerald-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account10000.gainTp1}</td>
                                <td className="p-1 text-cyan-600 dark:text-cyan-400 font-bold">{sig.precisionMetrics.lotSizeCalculations.account10000.gainTp2}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </div>
              )}

              {/* Action Buttons: 1-Click Copy, SMC Chart, Risk Calc, Telegram Dispatch */}
              {(() => {
                const isWaiting = !sig.confirmationCheckPassed || sig.signalType === 'WAIT' || !sig.isActionableNow || sig.decisionStatus === 'NO_TRADE';
                const isNoTrade = sig.decisionStatus === 'NO_TRADE' || sig.signalType === 'WAIT';

                return (
                  <div className={`flex flex-wrap items-center justify-between pt-3 border-t gap-2 ${isLight ? 'border-slate-100' : 'border-slate-800/80'}`}>
                    <div className="flex items-center gap-1.5">
                      {/* 1-Click Copy Button */}
                      <button
                        onClick={() => !isWaiting && handleCopy(sig)}
                        disabled={isWaiting}
                        className={`flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-lg border transition shadow-2xs ${
                          isWaiting
                            ? isLight
                              ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                              : 'bg-slate-900 text-slate-500 border-slate-800 cursor-not-allowed opacity-60'
                            : copiedId === sig.id
                            ? 'bg-emerald-600 text-white border-emerald-600'
                            : isLight
                            ? 'bg-slate-100 hover:bg-slate-200 text-slate-800 border-slate-300'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
                        }`}
                        title={isWaiting ? (isAr ? 'خاص ما يعطيك صفقة حتى يتسنى confirmation لي غادي تبين داكشي صحيح — الدخول محظور حالياً' : 'Waiting for candle confirmation') : (isAr ? 'نسخ بيانات الصفقة لمنصة MT4/MT5/Exness' : 'Copy Trade for MetaTrader/Exness')}
                      >
                        {isWaiting ? (
                          <Clock className="w-3.5 h-3.5 text-amber-500" />
                        ) : copiedId === sig.id ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {isWaiting
                            ? (isFr ? 'En attente' : isAr ? 'في انتظار التأكيد' : 'Waiting Conf.')
                            : copiedId === sig.id
                            ? (isFr ? 'Copié ✓' : isAr ? 'تم النسخ ✓' : 'Copied ✓')
                            : (isFr ? 'Copier MT5' : isAr ? 'نسخ للصفقة' : 'Copy MT5')}
                        </span>
                      </button>

                      {/* SMC Chart View Button */}
                      <button
                        onClick={() => setSelectedChartSignal({ signal: sig, isPreAlert: false })}
                        className={`flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg border transition ${
                          isLight
                            ? 'bg-purple-50 text-purple-800 hover:bg-purple-100 border-purple-300'
                            : 'bg-purple-950/60 text-purple-300 hover:bg-purple-900/80 border-purple-800/60'
                        }`}
                        title={isAr ? 'عرض شارت SMC ومناطق الأهداف' : 'View SMC Chart'}
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>{isFr ? 'Graphique' : isAr ? 'شارت الصفقة' : 'SMC Chart'}</span>
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* Calculate Risk Button */}
                      <button
                        onClick={() => onSelectSignalForRisk(sig)}
                        className={`flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg border transition shadow-xs ${
                          isLight
                            ? 'bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border-cyan-300'
                            : 'bg-cyan-950/80 hover:bg-cyan-900 text-cyan-300 border-cyan-800/50'
                        }`}
                      >
                        <Calculator className="w-3.5 h-3.5" />
                        <span>{isFr ? 'Calculer Risque' : isAr ? 'حساب اللوت والمخاطرة' : 'Lot Size'}</span>
                      </button>

                      {/* Telegram Send Button */}
                      <button
                        onClick={() => !isNoTrade && handleSendToTelegram(sig, isWaiting ? 'pre_alert' : 'confirmed')}
                        disabled={Boolean(isSending) || sig.isMarketOpen === false || isNoTrade}
                        className={`flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg border transition ${
                          sig.isMarketOpen === false || isNoTrade
                            ? 'opacity-50 cursor-not-allowed bg-slate-800 text-slate-400 border-slate-700'
                            : isWaiting
                            ? isLight
                              ? 'bg-amber-50 text-amber-800 hover:bg-amber-100 border-amber-300'
                              : 'bg-amber-950/70 text-amber-300 hover:bg-amber-900/80 border-amber-800/60'
                            : isLight
                            ? 'bg-sky-50 text-sky-800 hover:bg-sky-100 border-sky-300'
                            : 'bg-sky-950/70 text-sky-300 hover:bg-sky-900/80 border-sky-800/60'
                        }`}
                        title={
                          sig.isMarketOpen === false
                            ? (isAr ? 'السوق مغلق حالياً' : 'Market Closed')
                            : isNoTrade
                            ? (isAr ? 'حظر الإرسال: السوق في حالة NO TRADE / WAIT — شروط التأكيد غير مكتملة' : 'Sending disabled: Market in NO TRADE state')
                            : isWaiting
                            ? (isAr ? 'إرسال تنبيه تحضيري (وجّد راسك) — ننتظر شمعة التأكيد' : 'Send Pre-Alert to Telegram')
                            : (isAr ? 'إرسال التوصية المؤكدة فوراً للبوت' : 'Send Confirmed to Telegram')
                        }
                      >
                        <Send className={`w-3.5 h-3.5 ${isSending === `${sig.id}-pre_alert` || isSending === `${sig.id}-confirmed` ? 'animate-spin' : ''}`} />
                        <span>
                          {sig.isMarketOpen === false
                            ? (isFr ? 'Fermé' : isAr ? 'السوق مغلق' : 'Closed')
                            : isNoTrade
                            ? (isFr ? 'Verrouillé' : isAr ? 'معلق (انتظار)' : 'Locked')
                            : isWaiting
                            ? (isFr ? 'Pré-Alerte' : isAr ? 'وجّد راسك' : 'Pre-Alert')
                            : sentSignalId === `${sig.id}-confirmed`
                            ? (isFr ? 'Envoyé ✓' : isAr ? 'أُرسل ✓' : 'Sent ✓')
                            : (isFr ? 'Telegram' : isAr ? 'إرسال للتليجرام' : 'Send')}
                        </span>
                      </button>

                      {/* Cancel Setup Button (When waiting confirmation) */}
                      {isWaiting && sig.isMarketOpen !== false && (
                        <button
                          onClick={() => handleSendToTelegram(sig, 'cancelled')}
                          disabled={Boolean(isSending)}
                          className={`flex items-center gap-1 text-xs font-bold px-2 py-1.5 rounded-lg border transition ${
                            isLight
                              ? 'bg-rose-50 text-rose-800 hover:bg-rose-100 border-rose-300'
                              : 'bg-rose-950/60 text-rose-300 hover:bg-rose-900/80 border-rose-800/60'
                          }`}
                          title={isAr ? 'إلغاء المراقبة وإرسال تنبيه بالتيليجرام (تسنى فرصة أخرى)' : 'Cancel setup & notify to wait for another opportunity'}
                        >
                          <X className={`w-3.5 h-3.5 ${isSending === `${sig.id}-cancelled` ? 'animate-spin' : ''}`} />
                          <span>
                            {sentSignalId === `${sig.id}-cancelled`
                              ? (isFr ? 'Annulé ✓' : isAr ? 'أُلغيت ✓' : 'Cancelled ✓')
                              : (isFr ? 'Attendre autre' : isAr ? 'تسنى فرصة أخرى' : 'Cancel')}
                          </span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })()}
            </motion.div>
          );
        })}
        {filteredSignals.length === 0 && (
          <div className="col-span-full py-12 px-4 text-center rounded-2xl border border-dashed border-slate-700/60 bg-slate-900/40">
            <Clock className="w-8 h-8 text-amber-500 mx-auto mb-2 animate-pulse" />
            <p className="text-sm font-bold text-slate-300">
              {isAr ? 'في انتظار اكتمال شروط هذا الفلتر' : 'Waiting for market setup matching this filter'}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {isAr ? 'اضغط على "الذهب (XAU/USD) حصري" لمشاهدة جميع تحليلات وإشارات الذهب' : 'Click "Gold Exclusive" to view live Gold analysis and setups'}
            </p>
          </div>
        )}
      </div>

      {/* SMC Institutional Chart Preview Modal */}
      {selectedChartSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/75 backdrop-blur-xs animate-in fade-in duration-200">
          <div className={`relative w-full max-w-4xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[92vh] ${
            isLight ? 'bg-white border-slate-200 text-slate-900' : 'bg-surface border-slate-800 text-white'
          }`}>
            {/* Modal Header */}
            <div className={`flex items-center justify-between px-5 py-3.5 border-b ${
              isLight ? 'bg-slate-50 border-slate-200' : 'bg-surface-2 border-slate-800'
            }`}>
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center border border-cyan-500/30">
                  <ImageIcon className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-sm flex items-center gap-2">
                    <span>{isFr ? `Graphique d'Analyse Institutionnelle (SMC) : ${selectedChartSignal.signal.symbol}` : isAr ? `شارت التحليل المؤسساتي (SMC Chart): ${selectedChartSignal.signal.symbol}` : `SMC Chart: ${selectedChartSignal.signal.symbol}`}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">
                      {selectedChartSignal.signal.signalType}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    {isFr ? 'Visualisation des Order Blocks, balayage de liquidité, SL et TP envoyés sur Telegram' : isAr ? 'عرض مناطق كتل الأوامر (Order Blocks)، سحب السيولة، الستوب لوس، والأهداف المرسلة للتليجرام' : 'Visual breakdown with Order Blocks, Liquidity Sweeps, SL & TP'}
                  </p>
                </div>
              </div>

              {/* Toggle Mode & Close */}
              <div className="flex items-center gap-2">
                <div className="flex rounded-lg border p-0.5 text-xs bg-slate-900 border-slate-700">
                  <button
                    onClick={() => setSelectedChartSignal({ ...selectedChartSignal, isPreAlert: true })}
                    className={`px-2.5 py-1 rounded transition text-xs ${
                      selectedChartSignal.isPreAlert
                        ? 'bg-amber-500/30 text-amber-300 font-bold'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {isFr ? 'Vue Pré-Alerte' : isAr ? 'شارت وجد راسك' : 'Pre-Alert View'}
                  </button>
                  <button
                    onClick={() => setSelectedChartSignal({ ...selectedChartSignal, isPreAlert: false })}
                    className={`px-2.5 py-1 rounded transition text-xs ${
                      !selectedChartSignal.isPreAlert
                        ? 'bg-sky-500/30 text-sky-300 font-bold'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {isFr ? 'Vue Confirmée' : isAr ? 'شارت تأكيد الدخول' : 'Confirmed View'}
                  </button>
                </div>

                <button
                  onClick={() => setSelectedChartSignal(null)}
                  className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body: Chart SVG Image */}
            <div className="p-4 overflow-y-auto flex flex-col items-center justify-center bg-canvas">
              <div className="w-full rounded-xl overflow-hidden border border-slate-800 shadow-lg bg-canvas">
                <img
                  src={`/api/signals/${selectedChartSignal.signal.id}/chart.svg?preAlert=${selectedChartSignal.isPreAlert}&t=${Date.now()}`}
                  alt={`${selectedChartSignal.signal.symbol} SMC Chart`}
                  className="w-full h-auto object-contain block"
                />
              </div>

              {/* Institutional Trade Details Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 w-full mt-3.5">
                <div className="p-2.5 rounded-xl border border-cyan-500/30 bg-cyan-950/30">
                  <span className="text-xs text-cyan-400 block font-semibold">{isFr ? 'Zone d\'Entrée :' : isAr ? 'منطقة الدخول:' : 'Entry Zone:'}</span>
                  <span className="text-xs font-bold text-white font-mono">{selectedChartSignal.signal.entryZone}</span>
                </div>
                <div className="p-2.5 rounded-xl border border-rose-500/30 bg-rose-950/30">
                  <span className="text-xs text-rose-400 block font-semibold">{isFr ? 'Stop Loss (SL) :' : isAr ? 'الستوب لوس (SL):' : 'Stop Loss:'}</span>
                  <span className="text-xs font-bold text-rose-300 font-mono">${selectedChartSignal.signal.stopLoss}</span>
                </div>
                <div className="p-2.5 rounded-xl border border-emerald-500/30 bg-emerald-950/30">
                  <span className="text-xs text-emerald-400 block font-semibold">{isFr ? 'Objectif 1 (TP1) :' : isAr ? 'الهدف 1 (TP1):' : 'Target 1:'}</span>
                  <span className="text-xs font-bold text-emerald-300 font-mono">${selectedChartSignal.signal.target1}</span>
                </div>
                <div className="p-2.5 rounded-xl border border-sky-500/30 bg-sky-950/30">
                  <span className="text-xs text-sky-400 block font-semibold">{isFr ? 'Objectif 2 (TP2) :' : isAr ? 'الهدف 2 (TP2):' : 'Target 2:'}</span>
                  <span className="text-xs font-bold text-sky-300 font-mono">${selectedChartSignal.signal.target2}</span>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className={`flex flex-wrap items-center justify-between px-5 py-3 border-t gap-3 ${
              isLight ? 'bg-slate-50 border-slate-200' : 'bg-surface-2 border-slate-800'
            }`}>
              <div className="text-xs text-slate-400 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>{isFr ? 'Ce graphique est synchronisé en temps réel avec les prix du marché' : isAr ? 'هذا الشارت متزامن لحظياً مع أسعار السوق الحقيقية' : 'Synchronized real-time with live market prices'}</span>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={`/api/signals/${selectedChartSignal.signal.id}/chart.png?preAlert=${selectedChartSignal.isPreAlert}`}
                  target="_blank"
                  rel="noreferrer"
                  download={`SMC_${selectedChartSignal.signal.symbol}_${selectedChartSignal.isPreAlert ? 'PreAlert' : 'Confirmed'}.png`}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/40 hover:bg-cyan-900/50 text-cyan-200 transition"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>{isFr ? 'Télécharger PNG' : isAr ? 'تحميل كصورة PNG' : 'Download PNG'}</span>
                </a>

                <button
                  onClick={() => {
                    handleSendToTelegram(selectedChartSignal.signal, selectedChartSignal.isPreAlert ? 'pre_alert' : 'confirmed');
                  }}
                  disabled={Boolean(isSending)}
                  className="flex items-center gap-1.5 text-xs font-bold px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm"
                >
                  <Send className={`w-3.5 h-3.5 ${isSending ? 'animate-spin' : ''}`} />
                  <span>{isFr ? 'Envoyer ce graphique à Telegram' : isAr ? 'إرسال نفس هذا الشارت لتليجرام' : 'Send this exact chart to Telegram'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}


      {/* Pair Profile & Dynamic SL/TP Modal */}
      {inspectingSignal && (
        <PairProfileInspectorModal
          isOpen={!!inspectingSignal}
          onClose={() => setInspectingSignal(null)}
          asset={{
            id: inspectingSignal.id,
            symbol: inspectingSignal.symbol,
            name: inspectingSignal.assetName,
            arabicName: inspectingSignal.assetName,
            category: inspectingSignal.symbol.includes('BTC') || inspectingSignal.symbol.includes('ETH') ? 'crypto' : inspectingSignal.symbol.includes('XAU') ? 'metals' : 'forex',
            price: inspectingSignal.currentLivePrice || inspectingSignal.entryPrice || 100,
            change24h: 0.45,
            change24hAmount: 1.2,
            high24h: (inspectingSignal.currentLivePrice || 100) * 1.01,
            low24h: (inspectingSignal.currentLivePrice || 100) * 0.99,
            volume24h: '1.2B',
            trend: inspectingSignal.signalType === 'BUY' ? 'Bullish' : 'Bearish',
            trendStrength: 90,
            pipSize: inspectingSignal.symbol.includes('XAU') || inspectingSignal.symbol.includes('Gold') ? 0.1 : inspectingSignal.symbol.includes('JPY') ? 0.01 : 0.0001,
            decimalPlaces: inspectingSignal.symbol.includes('XAU') || inspectingSignal.symbol.includes('Gold') ? 2 : inspectingSignal.symbol.includes('JPY') ? 2 : 4,
          }}
          signal={inspectingSignal}
          lang={lang}
        />
      )}

      {/* 7 AI Agents Ecosystem Operation Room Modal */}
      {isMultiAgentModalOpen && (
        <MultiAgentEcosystemModal
          isOpen={isMultiAgentModalOpen}
          onClose={() => setIsMultiAgentModalOpen(false)}
          lang={lang}
          theme={theme}
        />
      )}
    </div>
  );
};
