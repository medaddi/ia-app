import React, { useState, useEffect } from 'react';
import { 
  Radar, 
  Radio, 
  Zap, 
  Crosshair, 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  ShieldCheck, 
  Eye, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  ChevronRight,
  Sparkles,
  Layers,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { Language, OmniRadarAssetStatus, OmniRadarState } from '../types';

interface MultiMarketRadarMatrixProps {
  lang: Language;
  theme: 'light' | 'dark';
  onSelectAsset?: (symbol: string) => void;
  selectedSymbol?: string;
}

export const MultiMarketRadarMatrix: React.FC<MultiMarketRadarMatrixProps> = ({
  lang,
  theme,
  onSelectAsset,
  selectedSymbol = 'XAU/USD'
}) => {
  const [radarData, setRadarData] = useState<OmniRadarState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isToggling, setIsToggling] = useState(false);
  const [isTriggeringScan, setIsTriggeringScan] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const fetchRadarData = async () => {
    try {
      const res = await fetch('/api/radar/matrix');
      if (res.ok) {
        const data = await res.json();
        setRadarData(data);
        setLastUpdated(new Date());
      }
    } catch (err) {
      console.error('Error fetching radar matrix:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRadarData();
    // Poll radar status every 6 seconds to reflect parallel real-time scanning
    const interval = setInterval(fetchRadarData, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleOmniRadar = async () => {
    if (!radarData || isToggling) return;
    const newEnabled = !radarData.omniRadarEnabled;
    setIsToggling(true);
    try {
      const res = await fetch('/api/radar/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled })
      });
      if (res.ok) {
        setRadarData(prev => prev ? { ...prev, omniRadarEnabled: newEnabled } : null);
        fetchRadarData();
      }
    } catch (err) {
      console.error('Error toggling omni radar:', err);
    } finally {
      setIsToggling(false);
    }
  };

  const handleManualScan = async () => {
    setIsTriggeringScan(true);
    try {
      await fetch('/api/scanner/trigger-now', { method: 'POST' });
      await fetchRadarData();
    } catch (err) {
      console.error('Error triggering manual scan:', err);
    } finally {
      setIsTriggeringScan(false);
    }
  };

  const getStatusBadge = (status: OmniRadarAssetStatus['radarStatus']) => {
    switch (status) {
      case 'A_PLUS_OPPORTUNITY':
        return {
          bg: isLight ? 'bg-emerald-50 text-emerald-700 border-emerald-300' : 'bg-emerald-950/50 text-emerald-300 border-emerald-600',
          dot: 'bg-emerald-500 animate-pulse',
          icon: Zap,
          label: isFr ? 'Opportunité A+ Prête' : isAr ? 'فرصة A+ مؤكدة' : 'A+ Confirmed Trade'
        };
      case 'IN_ENTRY_ZONE':
        return {
          bg: isLight ? 'bg-amber-50 text-amber-700 border-amber-300' : 'bg-amber-950/50 text-amber-300 border-amber-600',
          dot: 'bg-amber-500',
          icon: Crosshair,
          label: isFr ? 'Zone Sniper en Approche' : isAr ? 'في منطقة القناص' : 'In Entry Zone'
        };
      case 'SCANNING_LIQUIDITY':
        return {
          bg: isLight ? 'bg-sky-50 text-sky-700 border-sky-200' : 'bg-sky-950/40 text-sky-300 border-sky-800',
          dot: 'bg-sky-400',
          icon: Radio,
          label: isFr ? 'Scan Liquidité & CHoCH' : isAr ? 'مسح السيولة وCHoCH' : 'Scanning Liquidity'
        };
      case 'WAITING_STRUCTURE':
        return {
          bg: isLight ? 'bg-slate-100 text-slate-600 border-slate-200' : 'bg-slate-800/60 text-slate-300 border-slate-700',
          dot: 'bg-slate-400',
          icon: Clock,
          label: isFr ? 'Veille Structure' : isAr ? 'مراقبة الهيكل' : 'Watching Structure'
        };
      case 'MARKET_CLOSED':
      default:
        return {
          bg: isLight ? 'bg-stone-100 text-stone-500 border-stone-200' : 'bg-surface-2 text-stone-500 border-stone-800',
          dot: 'bg-stone-600',
          icon: Clock,
          label: isFr ? 'Marché Fermé' : isAr ? 'السوق مغلق' : 'Market Closed'
        };
    }
  };

  const assets = radarData?.assets || [];
  const opportunitiesCount = assets.filter(a => a.radarStatus === 'A_PLUS_OPPORTUNITY').length;
  const inZoneCount = assets.filter(a => a.radarStatus === 'IN_ENTRY_ZONE').length;

  return (
    <div 
      className={`rounded-2xl border transition-all duration-300 overflow-hidden shadow-lg ${
        isLight 
          ? 'bg-gradient-to-b from-paper to-white border-paper-line-2' 
          : 'bg-gradient-to-b from-surface-2 to-surface border-line'
      }`}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      {/* Top Banner / Omni-Radar Control Bar */}
      <div className={`p-4 sm:p-5 border-b flex flex-col md:flex-row md:items-center justify-between gap-4 ${
        isLight ? 'bg-white/80 border-paper-line-2' : 'bg-surface-2/90 border-line'
      }`}>
        <div className="flex items-start sm:items-center gap-3.5">
          <div className="relative p-2.5 rounded-2xl bg-gradient-to-br from-gold-500 to-gold-700 text-black shadow-md flex items-center justify-center shrink-0">
            <Radar className={`w-6 h-6 text-black ${radarData?.omniRadarEnabled ? 'animate-spin' : ''}`} style={{ animationDuration: '8s' }} />
            {radarData?.omniRadarEnabled && (
              <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-white dark:border-line animate-pulse" />
            )}
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className={`text-base sm:text-lg font-black tracking-tight ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                {isFr 
                  ? 'Radar de Liquidité de l\'Or 360° en Temps Réel (XAU/USD)' 
                  : isAr 
                  ? 'رادار سيولة الذهب المؤسساتي (XAU/USD)' 
                  : 'Gold Institutional Liquidity Radar'}
              </h3>
              <span className={`text-xs font-black px-2 py-0.5 rounded-full border ${
                radarData?.omniRadarEnabled
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-slate-500/15 text-slate-500 border-slate-500/30'
              }`}>
                {radarData?.omniRadarEnabled 
                  ? (isFr ? `OR ACTIF (${assets.length} Actif)` : isAr ? `مسح الذهب مستمر (${assets.length} سوق)` : `GOLD ACTIVE (${assets.length} Market)`)
                  : (isFr ? 'MODE FOCUS' : isAr ? 'وضع التركيز' : 'SINGLE FOCUS')}
              </span>
            </div>
            <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isFr
                ? 'Surveillance milliseconde continue de la liquidité de l\'Or (Spot XAU/USD) : détection des Sweeps, Order Blocks et FVG avec performance maximale.'
                : isAr
                ? 'مراقبة بالغة الدقة لسيولة الذهب الفوري (Spot XAU/USD) : اقتناص سحب السيولة، فجوات FVG، وبلوكات الأوامر بأعلى أداء ممكن دون أي تشتيت!'
                : 'Continuous monitoring of Gold liquidity (Spot XAU/USD): Sweeps, FVG, and Order Blocks with maximum dedicated performance.'}
            </p>
          </div>
        </div>

        {/* Right Action Controls: Toggle Button + Manual Scan */}
        <div className="flex items-center gap-2.5 shrink-0 self-end md:self-center">
          <button
            onClick={handleManualScan}
            disabled={isTriggeringScan}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer ${
              isLight 
                ? 'bg-white hover:bg-slate-100 border-paper-line-2 text-slate-700' 
                : 'bg-surface-3 hover:bg-surface-3 border-line text-slate-200'
            }`}
            title={isFr ? 'Forcer un scan de tous les marchés' : isAr ? 'إجراء مسح فوري لجميع الأسواق' : 'Trigger Full Scan'}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isTriggeringScan ? 'animate-spin text-gold-500' : ''}`} />
            <span className="hidden sm:inline">
              {isTriggeringScan 
                ? (isFr ? 'Scan...' : isAr ? 'جاري المسح...' : 'Scanning...') 
                : (isFr ? 'Scan Immédiat' : isAr ? 'مسح فوري' : 'Deep Scan')}
            </span>
          </button>

          {/* Master Omni-Radar Toggle Button */}
          <button
            onClick={handleToggleOmniRadar}
            disabled={isToggling}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-black transition cursor-pointer shadow-sm ${
              radarData?.omniRadarEnabled
                ? 'bg-gradient-to-r from-gold-500 to-gold-500 hover:brightness-105 text-ink-strong'
                : isLight
                ? 'bg-slate-200 hover:bg-slate-300 text-slate-800'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
            }`}
          >
            <Radio className={`w-4 h-4 ${radarData?.omniRadarEnabled ? 'text-black animate-pulse' : ''}`} />
            <span>
              {isToggling
                ? (isFr ? 'Changement...' : isAr ? 'جاري التبديل...' : 'Updating...')
                : radarData?.omniRadarEnabled
                ? (isFr ? 'Omni-Radar : Activé' : isAr ? 'الرادار الشامل: مُفعّل' : 'Omni-Radar: ON')
                : (isFr ? 'Omni-Radar : Désactivé' : isAr ? 'الرادار الشامل: مُعطّل' : 'Omni-Radar: OFF')}
            </span>
          </button>
        </div>
      </div>

      {/* Quick Summary Pill Bar */}
      <div className={`px-4 sm:px-5 py-2.5 border-b flex flex-wrap items-center justify-between gap-3 text-xs ${
        isLight ? 'bg-paper/60 border-paper-line-2' : 'bg-surface/80 border-line'
      }`}>
        <div className="flex flex-wrap items-center gap-3 sm:gap-6 font-mono-numbers">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className={isLight ? 'text-slate-600' : 'text-slate-400'}>
              {isFr ? 'Marchés Actifs :' : isAr ? 'الأسواق تحت المراقبة :' : 'Active Markets:'}
            </span>
            <span className="font-black text-gold-700 dark:text-gold-400">
              {radarData?.activeMarketsCount || 8}/{radarData?.totalMarketsMonitored || 8}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-500" />
            <span className={isLight ? 'text-slate-600' : 'text-slate-400'}>
              {isFr ? 'Opportunités A+ Détectées :' : isAr ? 'صفقات A+ مؤكدة :' : 'A+ Setups:'}
            </span>
            <span className={`font-black ${opportunitiesCount > 0 ? 'text-emerald-500 animate-pulse' : ''}`}>
              {opportunitiesCount}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Crosshair className="w-3.5 h-3.5 text-sky-500" />
            <span className={isLight ? 'text-slate-600' : 'text-slate-400'}>
              {isFr ? 'En Zone d\'Entrée :' : isAr ? 'في منطقة القناص :' : 'In Sweet Spot:'}
            </span>
            <span className="font-black text-sky-500">{inZoneCount}</span>
          </div>
        </div>

        <div className={`text-xs font-mono-numbers ${isLight ? 'text-slate-400' : 'text-slate-500'}`}>
          {isFr ? 'Fréquence : 10s • MAJ : ' : isAr ? 'تحديث تلقائي كل 10ث • آخر فحص: ' : 'Loop: 10s • Updated: '}
          {lastUpdated.toLocaleTimeString(isAr ? 'ar-EG' : 'en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>

      {/* Main Asset Grid */}
      <div className="p-4 sm:p-5">
        {isLoading && !radarData ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5 py-6">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <div 
                key={n} 
                className={`h-36 rounded-2xl animate-pulse border ${
                  isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-800/40 border-slate-700/50'
                }`} 
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {assets.map((item) => {
              const badge = getStatusBadge(item.radarStatus);
              const BadgeIcon = badge.icon;
              const isSelected = selectedSymbol === item.symbol;
              const isBullish = item.change24h >= 0;

              return (
                <div
                  key={item.symbol}
                  onClick={() => onSelectAsset && onSelectAsset(item.symbol)}
                  className={`group relative rounded-2xl p-4 border transition-all duration-200 flex flex-col justify-between cursor-pointer ${
                    isSelected
                      ? isLight
                        ? 'bg-paper border-gold-500 ring-2 ring-gold-500/30 shadow-md'
                        : 'bg-surface-3 border-gold-500 ring-2 ring-gold-500/30 shadow-md'
                      : isLight
                      ? 'bg-white hover:bg-paper border-paper-line-2 hover:border-paper-line-2'
                      : 'bg-surface-2 hover:bg-surface-3 border-line hover:border-line-2'
                  }`}
                >
                  {/* Card Header: Symbol, Name, Price & 24h Change */}
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className={`font-black text-sm tracking-tight ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                            {item.symbol}
                          </span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-bold uppercase ${
                            item.category === 'metals'
                              ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                              : item.category === 'crypto'
                              ? 'bg-purple-500/15 text-purple-600 dark:text-purple-400'
                              : item.category === 'forex'
                              ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                              : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                          }`}>
                            {item.category}
                          </span>
                        </div>
                        <span className={`text-xs block truncate ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                          {isAr ? item.arabicName : item.name}
                        </span>
                      </div>

                      {/* Live Price & Change */}
                      <div className="text-right font-mono-numbers">
                        <div className={`text-xs font-black ${isLight ? 'text-slate-900' : 'text-white'}`}>
                          ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                        </div>
                        <div className={`text-xs font-bold flex items-center justify-end gap-0.5 ${
                          isBullish ? 'text-emerald-500' : 'text-rose-500'
                        }`}>
                          {isBullish ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                          <span>{item.change24h > 0 ? `+${item.change24h.toFixed(2)}` : item.change24h.toFixed(2)}%</span>
                        </div>
                      </div>
                    </div>

                    {/* Radar Status Badge */}
                    <div className="mb-2.5">
                      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs font-bold border w-full justify-between ${badge.bg}`}>
                        <div className="flex items-center gap-1.5 truncate">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${badge.dot}`} />
                          <span className="truncate">{badge.label}</span>
                        </div>
                        <BadgeIcon className="w-3.5 h-3.5 shrink-0 opacity-80" />
                      </div>
                    </div>

                    {/* Killzone and Phase Details */}
                    <div className="space-y-1 mb-3">
                      <div className="flex items-center justify-between text-xs">
                        <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>
                          {isFr ? 'Killzone :' : isAr ? 'الجلسة المؤسساتية :' : 'Killzone:'}
                        </span>
                        <span className={`font-bold ${item.isKillzoneActive ? 'text-gold-700 dark:text-gold-400' : 'text-slate-400'}`}>
                          {item.killzoneNameAr || (isFr ? 'Session Standard' : 'جلسة عادية')}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>
                          {isFr ? 'Score Confluence :' : isAr ? 'قوة التوافق (Win %):' : 'Confluence:'}
                        </span>
                        <span className="font-mono-numbers font-black text-emerald-500">
                          {item.confluenceScore}% ({item.estimatedWinRate})
                        </span>
                      </div>

                      {/* Actionable Signal Snapshot if available */}
                      {item.radarStatus === 'A_PLUS_OPPORTUNITY' && item.entryZone && (
                        <div className={`p-2 rounded-xl border mt-1.5 text-xs ${
                          isLight ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900' : 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                        }`}>
                          <div className="flex items-center justify-between font-black">
                            <span className="flex items-center gap-1">
                              <Zap className="w-3 h-3 text-amber-500" />
                              {item.suggestedAction === 'BUY' ? (isAr ? 'شراء فوري' : 'BUY NOW') : (isAr ? 'بيع فوري' : 'SELL NOW')}
                            </span>
                            <span className="font-mono-numbers">R:R {item.riskReward}</span>
                          </div>
                          <div className="text-xs mt-0.5 truncate font-mono-numbers">
                            {isAr ? 'الدخول :' : 'Zone:'} {item.entryZone}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card Footer: Quick Focus Button */}
                  <div className="pt-2 border-t flex items-center justify-between text-xs border-slate-200/60 dark:border-slate-800/80">
                    <span className={`truncate text-xs ${isLight ? 'text-slate-400' : 'text-slate-500'}`}>
                      {isAr ? item.currentPhaseAr : item.currentPhaseFr}
                    </span>
                    <div className="flex items-center gap-1 font-bold text-gold-700 dark:text-gold-400 group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5 transition-transform shrink-0">
                      <span>{isFr ? 'Analyser' : isAr ? 'فتح الشارت' : 'Chart'}</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Explanatory Footer Bar for User Peace of Mind */}
      <div className={`p-3.5 sm:p-4 border-t flex items-center gap-3 text-xs leading-relaxed ${
        isLight ? 'bg-paper border-paper-line-2 text-slate-600' : 'bg-surface-2 border-line text-slate-300'
      }`}>
        <ShieldCheck className="w-5 h-5 text-gold-500 shrink-0" />
        <div>
          <span className={`font-black ${isLight ? 'text-slate-900' : 'text-white'}`}>
            {isFr 
              ? 'Principe de Sélection Institutionnelle :' 
              : isAr 
              ? 'كيف يضمن الرادار الشامل أعلى نسبة نجاح للصفقات؟' 
              : 'Omni-Radar Edge & Institutional Accuracy:'}
          </span>{' '}
          {isFr
            ? 'Le radar analyse en continu l\'action des prix du Gold (XAU/USD) sur toutes les sessions clés (Asie, Londres, New York). Il détecte les sweeps institutionnels et les déséquilibres FVG avec un taux de réussite optimal.'
            : isAr
            ? 'يقوم هذا الرادار بمسح متواصل لحركة الذهب الفوري (XAU/USD) عبر جلسات التداول العالمية (آسيا، لندن، ونيويورك) لرصد سحب السيولة البنكية وفجوات FVG بدقة متناهية.'
            : 'The radar continuously evaluates Gold (XAU/USD) across Asian, London, and NY sessions, catching institutional sweeps and FVGs at optimal execution timing.'}
        </div>
      </div>
    </div>
  );
};
