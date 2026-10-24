import React, { useState, useEffect, useRef } from 'react';
import { SignalsPerformanceStats, SignalAuditRecord, LiveActiveTradeItem, Language } from '../types';
import { 
  Trophy, 
  TrendingUp, 
  ShieldAlert, 
  ShieldCheck, 
  Target, 
  Zap, 
  Percent, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  RefreshCw, 
  Send, 
  ArrowUpRight, 
  ArrowDownRight, 
  BarChart3, 
  Flame, 
  Filter,
  Check,
  Copy,
  Radio,
  Activity,
  Layers,
  Sparkles,
  Search,
  Users,
  UserCheck,
  DollarSign,
  Calendar,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

interface SignalPerformanceTrackerProps {
  lang: Language;
  theme?: 'light' | 'dark';
  onOpenTelegram?: () => void;
}

export const SignalPerformanceTracker: React.FC<SignalPerformanceTrackerProps> = ({
  lang,
  theme = 'light',
  onOpenTelegram
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [activeView, setActiveView] = useState<'PLATFORM' | 'USERS'>('PLATFORM');
  const [stats, setStats] = useState<SignalsPerformanceStats | null>(null);
  const [activeTrades, setActiveTrades] = useState<LiveActiveTradeItem[]>([]);
  const [usersStats, setUsersStats] = useState<any[]>([]);
  const [usersLoading, setUsersLoading] = useState<boolean>(false);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [filter, setFilter] = useState<'ALL' | 'WINS' | 'SL_HITS' | 'ACTIVE' | 'GOLD'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');
  const [isLiveConnected, setIsLiveConnected] = useState<boolean>(true);
  const [tickPulse, setTickPulse] = useState<boolean>(false);

  const isFetchingRef = useRef<boolean>(false);

  const fetchUsersStats = async () => {
    try {
      setUsersLoading(true);
      const res = await fetch(`/api/users/stats?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        if (data.users) {
          setUsersStats(data.users);
        }
      }
    } catch (err) {
      console.error('Error fetching users stats:', err);
    } finally {
      setUsersLoading(false);
    }
  };

  const fetchPerformance = async (isManual: boolean = false) => {
    if (isFetchingRef.current && !isManual) return;
    isFetchingRef.current = true;
    if (isManual) setLoading(true);

    try {
      const res = await fetch(`/api/signals/performance?t=${Date.now()}`, {
        cache: 'no-store',
        headers: { 'Cache-Control': 'no-cache' }
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.stats) {
          setStats(data.stats);
          if (data.activeTrades) {
            setActiveTrades(data.activeTrades);
          }
          setIsLiveConnected(true);
          const now = new Date();
          setLastSyncTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
          setTickPulse(true);
          setTimeout(() => setTickPulse(false), 500);
        }
      }
    } catch (err) {
      console.error('Error fetching live signal performance stats:', err);
      setIsLiveConnected(false);
    } finally {
      isFetchingRef.current = false;
      if (isManual) setLoading(false);
    }
  };

  // Live Auto-Polling Interval
  useEffect(() => {
    fetchPerformance(true);
    fetchUsersStats();
    const interval = setInterval(() => {
      fetchPerformance(false);
      if (activeView === 'USERS') {
        fetchUsersStats();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeView]);

  const handleCopySummary = () => {
    if (!stats) return;
    const summary = `📊 [TradingAI Pro — سجل الشفافية ونسبة الأداء المباشر]
⭐ نسبة النجاح والربح (Live Win Rate): ${stats.winRate}%
🏆 صفقات رابحة محققة للأهداف (TP Hits): ${stats.tp1Hits + stats.tp2Hits} صفقة
🛑 صفقات ضربت الستوب (SL Hits): ${stats.slHits} صفقات فقط
💰 صافي النقاط المحققة: +${stats.totalPipsGained.toLocaleString()} Pips
⚖️ معامل الربحية (Profit Factor): ${stats.profitFactor}x
🎯 متوسط العائد للمخاطرة: ${stats.averageRiskReward}
🕒 آخر تحديث لحظي: ${lastSyncTime || stats.lastUpdated}`;
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const filteredHistory = (stats?.recentAuditHistory || []).filter((item) => {
    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchSymbol = item.symbol.toLowerCase().includes(q);
      const matchName = (item.assetName || '').toLowerCase().includes(q);
      const matchNotes = (item.notesAr || '').toLowerCase().includes(q);
      if (!matchSymbol && !matchName && !matchNotes) return false;
    }

    if (filter === 'WINS') return item.outcome === 'TP1_HIT' || item.outcome === 'TP2_HIT';
    if (filter === 'SL_HITS') return item.outcome === 'SL_HIT';
    if (filter === 'ACTIVE') return item.outcome === 'ACTIVE';
    if (filter === 'GOLD') return item.symbol.includes('XAU') || item.symbol.includes('Gold');
    if (filter === 'CRYPTO') return item.symbol.includes('BTC') || item.symbol.includes('ETH');
    if (filter === 'FOREX') return item.symbol.includes('EUR') || item.symbol.includes('GBP') || item.symbol.includes('USD');
    return true;
  });

  return (
    <div className={`rounded-2xl border p-4 sm:p-6 shadow-sm transition-colors ${
      isLight ? 'bg-white border-slate-200' : 'bg-surface-2/95 border-slate-800'
    }`}>
      {/* Live Header with Status Indicator */}
      <div className={`flex flex-wrap items-center justify-between gap-3 pb-4 mb-5 border-b ${
        isLight ? 'border-slate-100' : 'border-slate-800'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`w-11 h-11 rounded-xl border flex items-center justify-center relative ${
            isLight ? 'bg-amber-50 border-amber-200 text-amber-600' : 'bg-amber-950/80 border-amber-800/60 text-amber-400'
          }`}>
            <Trophy className="w-5 h-5" />
            <span className={`absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 ${
              isLight ? 'border-white' : 'border-slate-900'
            } ${isLiveConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className={`font-bold text-base sm:text-lg flex items-center gap-2 ${isLight ? 'text-slate-900' : 'text-white'}`}>
                <span>{isAr ? 'سجل شفافية الأداء وإحصائيات الصفقات المباشرة' : 'Live Signals Performance & Audit'}</span>
              </h3>
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
                <Radio className={`w-3 h-3 ${tickPulse ? 'text-emerald-400 scale-125' : 'text-emerald-600'} transition-transform`} />
                <span>{isAr ? 'بث حي مباشر' : 'Live Stream'}</span>
              </div>
            </div>
            <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isAr 
                ? 'إحصائيات حية ومؤرشفة للـ Win-Rate، الأهداف المحققة (TP)، وعدد الستوبات (SL) مع تحديث لحظي' 
                : 'Audited win rate, live TP & SL outcomes, and net pips with strict 1% risk management'}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border ${
            isLight ? 'bg-slate-50 border-slate-200 text-slate-500' : 'bg-slate-900 border-slate-800 text-slate-400'
          }`}>
            <Clock className="w-3 h-3 text-cyan-500" />
            <span>{lastSyncTime ? `${isAr ? 'آخر نبضة:' : 'Last tick:'} ${lastSyncTime}` : (isAr ? 'متصل' : 'Connected')}</span>
          </div>

          <button
            onClick={() => fetchPerformance(true)}
            disabled={loading}
            className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border transition ${
              isLight ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300' : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-500' : ''}`} />
            <span className="hidden sm:inline">{isAr ? 'تحديث الآن' : 'Sync'}</span>
          </button>

          <button
            onClick={handleCopySummary}
            className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border transition ${
              isLight ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300' : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
            }`}
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? (isAr ? 'تم النسخ' : 'Copied') : (isAr ? 'نسخ التقرير' : 'Copy Stats')}</span>
          </button>

          {onOpenTelegram && (
            <button
              onClick={onOpenTelegram}
              className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition shadow-xs"
            >
              <Send className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{isAr ? 'تليجرام (/stats)' : 'Telegram'}</span>
            </button>
          )}
        </div>
      </div>

      {/* View Switcher: Platform Signals Audit vs Telegram Users Performance Hub */}
      <div className="flex items-center gap-2 p-1 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 mb-5 max-w-xl">
        <button
          onClick={() => setActiveView('PLATFORM')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition ${
            activeView === 'PLATFORM'
              ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs border border-slate-200/60 dark:border-slate-700'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <Trophy className="w-3.5 h-3.5 text-amber-500" />
          <span>{isAr ? 'سجل صفقات النظام (Platform)' : 'Platform Audit'}</span>
        </button>

        <button
          onClick={() => setActiveView('USERS')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition ${
            activeView === 'USERS'
              ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs border border-slate-200/60 dark:border-slate-700'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <Users className="w-3.5 h-3.5 text-cyan-500" />
          <span>{isAr ? 'أداء المشتركين والمتداولين' : 'Users Performance Hub'}</span>
          {usersStats.length > 0 && (
            <span className="text-xs px-1.5 py-0.2 rounded-full bg-cyan-500/20 text-cyan-600 dark:text-cyan-300 font-mono font-bold">
              {usersStats.length}
            </span>
          )}
        </button>
      </div>

      {activeView === 'USERS' ? (
        /* ================= USERS PERFORMANCE LEADERBOARD & AUDIT ================= */
        <div className="space-y-5 animate-in fade-in duration-300">
          {/* Top 3 Summary Cards for User Community */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className={`p-4 rounded-xl border ${isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/80 border-slate-800'}`}>
              <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                <span>{isAr ? 'إجمالي المشتركين النشطين:' : 'Active Traders:'}</span>
                <Users className="w-4 h-4 text-cyan-500" />
              </div>
              <div className="text-2xl font-black font-mono text-slate-900 dark:text-white">
                {usersStats.length} {isAr ? 'متداول' : 'Traders'}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {isAr ? 'بيانات وإحصائيات مخصصة لكل Chat ID' : 'Individual telemetry per user'}
              </p>
            </div>

            <div className={`p-4 rounded-xl border ${isLight ? 'bg-emerald-50/70 border-emerald-200' : 'bg-emerald-950/30 border-emerald-800/60'}`}>
              <div className="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-400 mb-1">
                <span>{isAr ? 'الصفقات التي دخل إليها المشتركون:' : 'Total Trades Joined:'}</span>
                <Target className="w-4 h-4 text-emerald-500" />
              </div>
              <div className="text-2xl font-black font-mono text-emerald-600 dark:text-emerald-400">
                {usersStats.reduce((acc, u) => acc + (u.totalJoinedTrades || 0), 0)} {isAr ? 'صفقة مسجلة' : 'Trades'}
              </div>
              <p className="text-xs text-emerald-600/80 dark:text-emerald-400/80 mt-1">
                {isAr ? 'تحتسب فقط الصفقات المنفذة فعلياً' : 'Calculated strictly on joined trades'}
              </p>
            </div>

            <div className={`p-4 rounded-xl border ${isLight ? 'bg-sky-50/70 border-sky-200' : 'bg-sky-950/30 border-sky-800/60'}`}>
              <div className="flex items-center justify-between text-xs text-sky-700 dark:text-sky-400 mb-1">
                <span>{isAr ? 'إجمالي أرباح نقاط المشتركين:' : 'Total Pips Realized:'}</span>
                <TrendingUp className="w-4 h-4 text-sky-500" />
              </div>
              <div className="text-2xl font-black font-mono text-sky-600 dark:text-sky-400">
                +{usersStats.reduce((acc, u) => acc + (u.total?.pips || 0), 0)} Pips
              </div>
              <p className="text-xs text-sky-600/80 dark:text-sky-400/80 mt-1">
                {isAr ? 'مجموع أرباح المتداولين المحققة' : 'Cumulative user profit pool'}
              </p>
            </div>
          </div>

          {/* User Cards Grid */}
          {usersLoading && usersStats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-cyan-500" />
              <p className="text-xs">{isAr ? 'جاري تحميل إحصائيات المشتركين من تيليجرام...' : 'Loading user stats...'}</p>
            </div>
          ) : usersStats.length === 0 ? (
            <div className={`p-8 rounded-xl border text-center ${isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900 border-slate-800'}`}>
              <Users className="w-8 h-8 text-slate-400 mx-auto mb-2" />
              <p className="text-xs text-slate-400">
                {isAr ? 'لا يوجد مشتركون نشطون مسجلون بعد. عند تفاعل أي مستخدم مع البوت ستظهر إحصائياته هنا فورياً.' : 'No user stats registered yet.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {usersStats.map((u) => {
                const isExpanded = expandedUser === u.chatId;
                const totalPips = u.total?.pips || 0;
                const pipsSign = totalPips >= 0 ? '+' : '';

                return (
                  <div
                    key={u.chatId}
                    className={`rounded-xl border p-4 transition shadow-xs ${
                      isLight ? 'bg-white border-slate-200 hover:border-cyan-300' : 'bg-slate-900/90 border-slate-800 hover:border-cyan-700/60'
                    }`}
                  >
                    {/* User Header */}
                    <div className="flex items-center justify-between mb-3 pb-2.5 border-b border-slate-100 dark:border-slate-800">
                      <div className="flex items-center gap-2.5">
                        <div className="w-9 h-9 rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/20 flex items-center justify-center font-bold text-xs">
                          {u.userName ? u.userName.slice(0, 2).toUpperCase() : 'TR'}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-xs text-slate-900 dark:text-white">
                              {u.userName}
                            </span>
                            <span className="text-xs font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                              <code>{u.chatId}</code>
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
                            <span>{isAr ? 'رأس المال:' : 'Capital:'} <strong>${(u.capital || 1000).toLocaleString()}</strong></span>
                            <span>•</span>
                            <span>{isAr ? 'المخاطرة:' : 'Risk:'} <strong>{u.riskPercent || 1.0}%</strong></span>
                          </div>
                        </div>
                      </div>

                      <div className="text-right">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                          (u.total?.winRate || 0) >= 75
                            ? 'bg-emerald-500/15 text-emerald-600 border border-emerald-500/30'
                            : 'bg-amber-500/15 text-amber-600 border border-amber-500/30'
                        }`}>
                          {u.total?.winRate || 0}% {isAr ? 'نسبة النجاح' : 'Win Rate'}
                        </span>
                        <div className="text-xs text-slate-400 mt-1 font-mono">
                          {u.totalJoinedTrades} {isAr ? 'صفقة منفذة' : 'joined trades'}
                        </div>
                      </div>
                    </div>

                    {/* Performance Breakdown Columns (Day, Week, Total) */}
                    <div className="grid grid-cols-3 gap-2 text-xs mb-3">
                      {/* Day */}
                      <div className={`p-2.5 rounded-lg border text-center ${isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-950/60 border-slate-800'}`}>
                        <span className="text-xs text-slate-400 block mb-0.5">
                          {isAr ? 'اليوم' : 'Today'}
                        </span>
                        <span className="font-mono font-bold text-slate-800 dark:text-slate-200 block">
                          {u.day?.total || 0} {isAr ? 'صفقة' : 'trades'}
                        </span>
                        <span className={`text-xs font-bold ${
                          (u.day?.pips || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                        }`}>
                          {(u.day?.pips || 0) >= 0 ? `+${u.day?.pips || 0}` : u.day?.pips} Pips
                        </span>
                      </div>

                      {/* Week */}
                      <div className={`p-2.5 rounded-lg border text-center ${isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-950/60 border-slate-800'}`}>
                        <span className="text-xs text-slate-400 block mb-0.5">
                          {isAr ? 'هذا الأسبوع' : 'Week'}
                        </span>
                        <span className="font-mono font-bold text-slate-800 dark:text-slate-200 block">
                          {u.week?.total || 0} {isAr ? 'صفقة' : 'trades'}
                        </span>
                        <span className={`text-xs font-bold ${
                          (u.week?.pips || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                        }`}>
                          {(u.week?.pips || 0) >= 0 ? `+${u.week?.pips || 0}` : u.week?.pips} Pips
                        </span>
                      </div>

                      {/* Total */}
                      <div className={`p-2.5 rounded-lg border text-center ${isLight ? 'bg-emerald-50/50 border-emerald-200' : 'bg-emerald-950/20 border-emerald-800/40'}`}>
                        <span className="text-xs text-emerald-600 dark:text-emerald-400 block mb-0.5">
                          {isAr ? 'الإجمالي' : 'All-Time'}
                        </span>
                        <span className="font-mono font-bold text-slate-900 dark:text-white block">
                          {u.total?.total || 0} {isAr ? 'صفقة' : 'trades'}
                        </span>
                        <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                          {pipsSign}{totalPips} Pips
                        </span>
                      </div>
                    </div>

                    {/* Trades list toggle */}
                    {u.trades && u.trades.length > 0 && (
                      <div>
                        <button
                          onClick={() => setExpandedUser(isExpanded ? null : u.chatId)}
                          className={`w-full flex items-center justify-between text-xs py-1.5 px-2.5 rounded-lg border transition ${
                            isLight ? 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200' : 'bg-slate-950/60 hover:bg-slate-900 text-slate-300 border-slate-800'
                          }`}
                        >
                          <span className="flex items-center gap-1.5">
                            <Layers className="w-3.5 h-3.5 text-cyan-500" />
                            <span>{isAr ? 'عرض الصفقات التي دخل إليها هذا المتداول' : 'View Joined Trades'} ({u.trades.length})</span>
                          </span>
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>

                        {isExpanded && (
                          <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto pr-1">
                            {u.trades.map((tr: any) => (
                              <div
                                key={tr.id}
                                className={`p-2 rounded border text-xs flex items-center justify-between ${
                                  isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-950 border-slate-800/80'
                                }`}
                              >
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-bold text-slate-900 dark:text-white">{tr.symbol}</span>
                                  <span className={`text-xs font-bold px-1.5 py-0.2 rounded ${
                                    tr.signalType === 'BUY' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-rose-500/10 text-rose-600'
                                  }`}>
                                    {tr.signalType}
                                  </span>
                                  <span className="text-xs text-slate-400">@{tr.entryPrice}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className={`text-xs font-bold px-1.5 py-0.2 rounded ${
                                    tr.status === 'TP1_HIT' || tr.status === 'TP2_HIT'
                                      ? 'bg-emerald-500/20 text-emerald-600'
                                      : tr.status === 'SL_HIT'
                                      ? 'bg-rose-500/20 text-rose-600'
                                      : tr.status === 'BE_SECURED'
                                      ? 'bg-sky-500/20 text-sky-600'
                                      : 'bg-amber-500/20 text-amber-600'
                                  }`}>
                                    {tr.status}
                                  </span>
                                  <span className="font-mono font-bold text-slate-700 dark:text-slate-300">
                                    {tr.unrealizedPips >= 0 ? `+${tr.unrealizedPips}` : tr.unrealizedPips}p
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        /* ================= PLATFORM SIGNALS AUDIT (EXISTING VIEW) ================= */
        <div>
      {/* Top 4 Hero Performance Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {/* Card 1: Live Win Rate % */}
        <div className={`p-4 rounded-xl border relative overflow-hidden transition-all ${
          isLight ? 'bg-gradient-to-br from-emerald-50/70 to-white border-emerald-200 text-slate-900' : 'bg-gradient-to-br from-emerald-950/40 to-surface border-emerald-800/60 text-white'
        }`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className={`text-xs font-semibold ${isLight ? 'text-emerald-800' : 'text-emerald-400'}`}>
              {isAr ? 'نسبة النجاح والأرباح:' : 'Overall Win Rate:'}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 font-bold">
              Grade A+ Live
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-black font-mono tracking-tight text-emerald-600 dark:text-emerald-400">
              {stats ? `${stats.winRate}%` : '0%'}
            </span>
            <TrendingUp className="w-5 h-5 text-emerald-500" />
          </div>
          <p className="text-xs mt-1.5 text-slate-500 dark:text-slate-400 flex items-center justify-between">
            <span>{isAr ? 'مجموع الصفقات المقفلة:' : 'Closed Trades:'}</span>
            <span className="font-mono font-bold text-slate-700 dark:text-slate-300">{stats?.closedSignals ?? 0} صفقة</span>
          </p>
        </div>

        {/* Card 2: TP Hits (Wins) */}
        <div className={`p-4 rounded-xl border relative overflow-hidden transition-all ${
          isLight ? 'bg-gradient-to-br from-sky-50/70 to-white border-sky-200 text-slate-900' : 'bg-gradient-to-br from-sky-950/40 to-surface border-sky-800/60 text-white'
        }`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className={`text-xs font-semibold ${isLight ? 'text-sky-800' : 'text-sky-400'}`}>
              {isAr ? 'الأهداف المحققة (TP Hits):' : 'Winning Targets Hit:'}
            </span>
            <Target className="w-4 h-4 text-sky-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-black font-mono tracking-tight text-sky-600 dark:text-sky-400">
              {(stats?.tp1Hits ?? 0) + (stats?.tp2Hits ?? 0)}
            </span>
            <span className="text-xs font-bold text-sky-500">
              {isAr ? 'صفقة رابحة' : 'Wins'}
            </span>
          </div>
          <p className="text-xs mt-1.5 text-slate-500 dark:text-slate-400 flex items-center justify-between">
            <span>TP2: <strong className="text-emerald-600">{stats?.tp2Hits ?? 0}</strong></span>
            <span>TP1: <strong className="text-sky-600">{stats?.tp1Hits ?? 0}</strong></span>
          </p>
        </div>

        {/* Card 3: Stop Losses Hit (شحال من SL ضرب) */}
        <div className={`p-4 rounded-xl border relative overflow-hidden transition-all ${
          isLight ? 'bg-gradient-to-br from-rose-50/70 to-white border-rose-200 text-slate-900' : 'bg-gradient-to-br from-rose-950/40 to-surface border-rose-800/60 text-white'
        }`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className={`text-xs font-semibold ${isLight ? 'text-rose-800' : 'text-rose-400'}`}>
              {isAr ? 'شحال من SL ضرب:' : 'Stop Losses Hit (SL):'}
            </span>
            <ShieldAlert className="w-4 h-4 text-rose-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-black font-mono tracking-tight text-rose-600 dark:text-rose-400">
              {stats?.slHits ?? 0}
            </span>
            <span className="text-xs font-bold text-rose-500">
              {isAr ? 'صفقات خاسرة' : 'SLs Only'}
            </span>
          </div>
          <p className="text-xs mt-1.5 text-slate-500 dark:text-slate-400 flex items-center justify-between">
            <span>{isAr ? 'مخاطرة محكمة:' : 'Risk Per Trade:'}</span>
            <span className="font-bold text-emerald-600">1.0% Max Risk</span>
          </p>
        </div>

        {/* Card 4: Net Pips Gained */}
        <div className={`p-4 rounded-xl border relative overflow-hidden transition-all ${
          isLight ? 'bg-gradient-to-br from-purple-50/70 to-white border-purple-200 text-slate-900' : 'bg-gradient-to-br from-purple-950/40 to-surface border-purple-800/60 text-white'
        }`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className={`text-xs font-semibold ${isLight ? 'text-purple-800' : 'text-purple-400'}`}>
              {isAr ? 'صافي النقاط المحققة:' : 'Net Realized Pips:'}
            </span>
            <Zap className="w-4 h-4 text-purple-500" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-3xl sm:text-4xl font-black font-mono tracking-tight text-purple-600 dark:text-purple-400">
              {stats ? (stats.totalPipsGained > 0 ? `+${stats.totalPipsGained.toLocaleString()}` : `${stats.totalPipsGained.toLocaleString()}`) : '0'}
            </span>
            <span className="text-xs font-bold text-purple-500">
              Pips
            </span>
          </div>
          <p className="text-xs mt-1.5 text-slate-500 dark:text-slate-400 flex items-center justify-between">
            <span>{isAr ? 'معامل الربحية:' : 'Profit Factor:'}</span>
            <span className="font-bold font-mono text-purple-600 dark:text-purple-400">{stats?.profitFactor ?? 0}x</span>
          </p>
        </div>
      </div>

      {/* Live Active Monitored Positions Tracker */}
      {activeTrades.length > 0 && (
        <div className={`p-4 rounded-xl border mb-6 ${
          isLight ? 'bg-sky-50/40 border-sky-200' : 'bg-sky-950/20 border-sky-800/50'
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-sky-500 animate-pulse" />
              <h4 className={`text-xs font-bold flex items-center gap-2 ${isLight ? 'text-slate-900' : 'text-white'}`}>
                <span>{isAr ? 'الصفقات قيد المراقبة اللحظية بالأسواق:' : 'Live Active Market Signals Being Monitored:'}</span>
                <span className="text-xs px-1.5 py-0.2 rounded bg-sky-500/20 text-sky-600 dark:text-sky-300 font-mono font-bold">
                  {activeTrades.length} Active
                </span>
              </h4>
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {isAr ? 'مراقبة حركة السعر لحظة بلحظة للوصول لـ TP أو SL' : 'Real-time price tracking vs targets'}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeTrades.map((t) => {
              const isProfit = t.unrealizedPips >= 0;
              return (
                <div
                  key={t.id}
                  className={`p-3.5 rounded-lg border transition ${
                    isLight ? 'bg-white border-slate-200 shadow-xs' : 'bg-surface-2 border-slate-800'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-xs font-mono text-slate-900 dark:text-white">{t.symbol}</span>
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                        t.signalType === 'BUY'
                          ? 'bg-emerald-500/15 text-emerald-600 border border-emerald-500/20'
                          : 'bg-rose-500/15 text-rose-600 border border-rose-500/20'
                      }`}>
                        {t.signalType}
                      </span>
                    </div>
                    <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                      isProfit ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600'
                    }`}>
                      {isProfit ? `+${t.unrealizedPips}` : t.unrealizedPips} Pips
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-1.5 text-xs text-slate-500 mb-2.5 font-mono">
                    <div>
                      <span className="text-xs text-slate-400 block">{isAr ? 'الدخول' : 'Entry'}</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">${t.entryPrice}</span>
                    </div>
                    <div>
                      <span className="text-xs text-slate-400 block">{isAr ? 'السعر الآن' : 'Live'}</span>
                      <span className="font-semibold text-cyan-600 dark:text-cyan-400">${t.currentPrice}</span>
                    </div>
                    <div>
                      <span className="text-xs text-slate-400 block">{isAr ? 'الهدف TP1' : 'Target'}</span>
                      <span className="font-semibold text-emerald-600">${t.target1}</span>
                    </div>
                  </div>

                  {/* Progress bar towards TP */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>{isAr ? 'الاقتراب من الهدف:' : 'Target Progress:'}</span>
                      <span className="font-mono font-bold text-slate-600 dark:text-slate-300">{t.progressPercent}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className={`h-full transition-all duration-500 ${
                          t.status === 'TP1_HIT' || t.status === 'TP2_HIT' 
                            ? 'bg-emerald-500' 
                            : isProfit ? 'bg-cyan-500' : 'bg-rose-500'
                        }`}
                        style={{ width: `${Math.max(5, Math.min(100, t.progressPercent))}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Asset Performance Breakdown Row */}
      <div className={`p-4 rounded-xl border mb-6 ${
        isLight ? 'bg-slate-50/80 border-slate-200' : 'bg-slate-900/60 border-slate-800'
      }`}>
        <div className="flex items-center justify-between mb-3">
          <h4 className={`text-xs font-bold flex items-center gap-2 ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
            <BarChart3 className="w-4 h-4 text-gold-500" />
            <span>{isFr ? 'Audit de Performance Spécialisé Or (Gold) :' : isAr ? 'نسبة النجاح والأرباح الموثقة للذهب:' : 'Institutional Gold Win Rate Audit:'}</span>
          </h4>
          <span className="text-xs text-amber-500 font-bold">
            {isAr ? 'الذهب الفوري (XAU/USD) — دقة مؤسساتية قصوى' : 'Gold (XAU/USD) Institutional Track Record'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-1 gap-3">
          {(stats?.assetBreakdown || [
            { symbol: 'XAU/USD', name: isFr ? 'Or Spot (LBMA Fixing)' : isAr ? 'الذهب الفوري (XAU/USD)' : 'Spot Gold (LBMA)', totalSignals: 0, wins: 0, slHits: 0, winRate: 0, pipsGained: 0 },
          ]).map((asset) => (
            <div
              key={asset.symbol}
              className={`p-3 rounded-lg border transition ${
                isLight ? 'bg-white border-slate-200 shadow-xs' : 'bg-surface border-slate-800'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs font-mono text-gold-500">{asset.symbol}</span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 font-bold">
                  {asset.winRate}% Win
                </span>
              </div>
              <div className="text-xs text-slate-500 mb-1 truncate">
                {asset.name}
              </div>
              <div className="flex items-center justify-between text-xs pt-1.5 border-t border-slate-100 dark:border-slate-800">
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                  {asset.wins} {isAr ? 'ربح' : 'Wins'} / <span className="text-rose-500">{asset.slHits} SL</span>
                </span>
                <span className="font-bold font-mono text-gold-500">
                  +{asset.pipsGained} pips
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Filter Tabs & Live Search for History Ledger */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <h4 className={`text-xs font-bold ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
            {isAr ? 'سجل الصفقات المفصل والتحقق الشفاف:' : 'Detailed Trade Audit Ledger:'}
          </h4>
        </div>

        {/* Search input */}
        <div className="flex items-center gap-2 flex-1 max-w-xs">
          <div className="relative w-full">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder={isAr ? 'بحث في صفقات الذهب (XAU, TP1, Buy...)' : 'Search Gold trades...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={`w-full text-xs pl-8 pr-3 py-1.5 rounded-lg border outline-none transition ${
                isLight ? 'bg-slate-50 border-slate-200 text-slate-800 focus:border-cyan-500' : 'bg-slate-900 border-slate-800 text-white focus:border-cyan-500'
              }`}
            />
          </div>
        </div>

        {/* Filters */}
        <div className={`flex flex-wrap items-center gap-1 p-1 rounded-xl border text-xs ${
          isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-950 border-slate-800'
        }`}>
          <button
            onClick={() => setFilter('ALL')}
            className={`px-2.5 py-1 rounded-lg transition ${
              filter === 'ALL'
                ? isLight ? 'bg-white text-slate-900 font-bold shadow-xs' : 'bg-slate-800 text-white font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {isAr ? 'جميع الصفقات' : 'All'}
          </button>
          <button
            onClick={() => setFilter('WINS')}
            className={`px-2.5 py-1 rounded-lg transition ${
              filter === 'WINS'
                ? isLight ? 'bg-emerald-100 text-emerald-900 font-bold' : 'bg-emerald-900/60 text-emerald-300 font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {isAr ? 'الرابحة (TP)' : 'Wins Only'}
          </button>
          <button
            onClick={() => setFilter('SL_HITS')}
            className={`px-2.5 py-1 rounded-lg transition ${
              filter === 'SL_HITS'
                ? isLight ? 'bg-rose-100 text-rose-900 font-bold' : 'bg-rose-900/60 text-rose-300 font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {isAr ? 'ضربت الستوب (SL)' : 'SL Hits'}
          </button>
          <button
            onClick={() => setFilter('GOLD')}
            className={`px-2.5 py-1 rounded-lg transition ${
              filter === 'GOLD'
                ? isLight ? 'bg-amber-100 text-amber-900 font-bold' : 'bg-amber-900/60 text-amber-300 font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            {isFr ? 'Or (XAU/USD)' : isAr ? 'الذهب (XAU/USD)' : 'Gold Only'}
          </button>
        </div>
      </div>

      {/* Trade Audit History Table */}
      <div className={`overflow-x-auto rounded-xl border ${
        isLight ? 'border-slate-200' : 'border-slate-800'
      }`}>
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className={`border-b text-xs font-semibold uppercase tracking-wider ${
              isLight ? 'bg-slate-50 text-slate-500 border-slate-200' : 'bg-slate-900/80 text-slate-400 border-slate-800'
            }`}>
              <th className="px-3 py-2.5">{isAr ? 'الصفقة / الأصل' : 'Asset'}</th>
              <th className="px-3 py-2.5">{isAr ? 'النوع' : 'Type'}</th>
              <th className="px-3 py-2.5">{isAr ? 'سعر الدخول' : 'Entry'}</th>
              <th className="px-3 py-2.5">{isAr ? 'الستوب (SL)' : 'SL'}</th>
              <th className="px-3 py-2.5">{isAr ? 'الأهداف' : 'TP1 / TP2'}</th>
              <th className="px-3 py-2.5">{isAr ? 'النتيجة المحققة' : 'Outcome'}</th>
              <th className="px-3 py-2.5">{isAr ? 'النقاط المحققة' : 'Pips / R:R'}</th>
              <th className="px-3 py-2.5">{isAr ? 'ملاحظات التحليل والسيولة' : 'SMC Audit Notes'}</th>
            </tr>
          </thead>
          <tbody className={`divide-y ${isLight ? 'divide-slate-100' : 'divide-slate-800/60'}`}>
            {filteredHistory.map((row) => {
              const isWin = row.outcome === 'TP1_HIT' || row.outcome === 'TP2_HIT';
              const isSL = row.outcome === 'SL_HIT';

              return (
                <tr
                  key={row.id}
                  className={`transition-colors ${
                    isLight ? 'hover:bg-slate-50/80' : 'hover:bg-slate-900/40'
                  }`}
                >
                  {/* Asset */}
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <div className="font-bold font-mono text-slate-900 dark:text-white">
                      {row.symbol}
                    </div>
                    <div className="text-xs text-slate-500">
                      {row.date} • {row.timeframe}
                    </div>
                  </td>

                  {/* Type */}
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 font-bold px-2 py-0.5 rounded text-xs ${
                      row.signalType === 'BUY'
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                        : 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                    }`}>
                      {row.signalType === 'BUY' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {row.signalType}
                    </span>
                  </td>

                  {/* Entry */}
                  <td className="px-3 py-2.5 whitespace-nowrap font-mono font-semibold text-slate-800 dark:text-slate-200">
                    ${row.entryPrice}
                  </td>

                  {/* SL */}
                  <td className="px-3 py-2.5 whitespace-nowrap font-mono text-rose-600 dark:text-rose-400 font-semibold">
                    ${row.stopLoss}
                  </td>

                  {/* Targets */}
                  <td className="px-3 py-2.5 whitespace-nowrap font-mono text-xs text-slate-600 dark:text-slate-300">
                    <div>TP1: ${row.target1}</div>
                    <div className="text-cyan-600 dark:text-cyan-400">TP2: ${row.target2}</div>
                  </td>

                  {/* Outcome Badge */}
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {row.outcome === 'TP2_HIT' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                        حققت TP2 بالكامل
                      </span>
                    )}
                    {row.outcome === 'TP1_HIT' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-sky-500/20 text-sky-700 dark:text-sky-300 border border-sky-500/30">
                        <CheckCircle2 className="w-3 h-3 text-sky-500" />
                        ضربت TP1 (تأمين الدخول)
                      </span>
                    )}
                    {row.outcome === 'SL_HIT' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-500/20 text-rose-700 dark:text-rose-300 border border-rose-500/30">
                        <XCircle className="w-3 h-3 text-rose-500" />
                        ضربت الستوب (SL)
                      </span>
                    )}
                    {row.outcome === 'ACTIVE' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                        <Clock className="w-3 h-3 text-amber-500 animate-spin" />
                        ⏳ جارية ومفتوحة
                      </span>
                    )}
                    {row.outcome === 'BE_CLOSED' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-500/30">
                        <ShieldCheck className="w-3 h-3 text-slate-500" />
                        إغلاق بنقطة الدخول
                      </span>
                    )}
                  </td>

                  {/* Pips & RR */}
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <div className={`font-bold font-mono text-xs ${
                      row.pipsGained > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                    }`}>
                      {row.pipsGained > 0 ? `+${row.pipsGained}` : row.pipsGained} Pips
                    </div>
                    <div className="text-xs text-slate-400">
                      R:R {row.riskReward}
                    </div>
                  </td>

                  {/* Notes */}
                  <td className="px-3 py-2.5 text-xs text-slate-600 dark:text-slate-300 max-w-xs truncate">
                    {row.notesAr || (isAr ? 'تم التحقق من النموذج والشروط المؤسساتية' : 'Verified institutional SMC setup')}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filteredHistory.length === 0 && (
        <div className="text-center py-10 px-4 border border-dashed rounded-xl my-4 border-slate-200 dark:border-slate-800">
          <Target className="w-8 h-8 mx-auto mb-2 text-slate-400 opacity-60" />
          <p className="text-sm font-bold text-slate-700 dark:text-slate-300">
            {isAr ? 'تمت تصفية وبدء العداد من الصفر (0 صفقات)' : 'Fresh Audit Reset: Starting from 0 trades'}
          </p>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            {isAr 
              ? 'كل صفقة مؤكدة تخرج من الآن سيتم رصدها لحظياً بنقطة الدخول والستوب، وحساب نسبة الفوز (Win Rate) وعدد ضربات الـ TP والـ SL بكل شفافية ودقة تامة.'
              : 'Every new confirmed signal dispatched from now on will be audited live in real time to calculate exact Win Rate, TP hits, and SL hits.'}
          </p>
        </div>
      )}
        </div>
      )}
    </div>
  );
};
