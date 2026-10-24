import React, { useState } from 'react';
import { MarketAsset, TechnicalIndicators, Language, AISignal } from '../types';
import {
  Brain,
  TrendingUp,
  TrendingDown,
  Target,
  Shield,
  Gauge,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Zap,
  XCircle,
  AlertOctagon,
  Scale,
  Sparkles,
  Activity,
  ArrowRightLeft,
  ChevronDown,
  ChevronUp,
  Info,
  Crosshair,
  Clock,
  SlidersHorizontal,
  BarChart3,
  ShieldCheck,
  ShieldAlert
} from 'lucide-react';
import { buildDynamicPairProfile, detectMarketStructureAndRegime, calculateStructureFirstSLTP } from '../services/pairProfileEngine';

interface TechnicalPanelProps {
  asset: MarketAsset;
  indicators: TechnicalIndicators | null;
  signal?: AISignal | null;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const TechnicalAnalysisPanel: React.FC<TechnicalPanelProps> = ({
  asset,
  indicators,
  signal,
  lang,
  theme = 'light',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [activeTab, setActiveTab] = useState<'silverBullet' | 'diagnostic' | 'indicators' | 'pairProfile'>('silverBullet');
  const [showDetailedRejectionRules, setShowDetailedRejectionRules] = useState<boolean>(true);

  if (!asset || !indicators) {
    return (
      <div className={`rounded-2xl border p-6 flex items-center justify-center transition-colors ${
        isLight ? 'bg-white border-paper-line-2 text-slate-500' : 'bg-surface-2 border-line text-slate-400'
      }`}>
        <span>{isFr ? 'Chargement du moteur technique...' : isAr ? 'جاري تشغيل محرك تفكيك السيولة...' : 'Loading Liquidity Dissection Engine...'}</span>
      </div>
    );
  }

  const isUptrend = asset.trend === 'Bullish';

  // -------------------------------------------------------------------------
  // CONFLUENCE DIAGNOSTICS & TRADE SCORE COMPUTATION
  // -------------------------------------------------------------------------
  // Evaluate CHoCH, Order Block, and Liquidity Sweep confirmations
  const chochConfirmed = signal?.smcEngine?.chochConfirmed ?? (indicators.structureBreak?.includes('CHoCH') || indicators.marketStructure !== 'Sideways');
  const obConfirmed = signal?.smcEngine
    ? (signal.smcEngine.avoidMiddleOfRangePassed && signal.smcEngine.avoidHugeCandlePassed)
    : (indicators.smc?.orderBlock ? true : (asset.trendStrength > 45));
  const sweepConfirmed = signal?.smcEngine
    ? (signal.smcEngine.liquiditySweepConfirmed && signal.smcEngine.avoidLiquidityTrapPassed)
    : (indicators.support > 0 && asset.trendStrength > 50);
  const mtfConfirmed = signal?.multiTimeframeAlignment?.allAligned ?? (asset.trendStrength >= 60);

  // Points calculation matching the 10-pillar Decision Engine:
  // CHoCH: 30 pts | OB: 35 pts | Liquidity Sweep: 25 pts | MTF/Trend: 10 pts
  const chochPoints = chochConfirmed ? 30 : 0;
  const obPoints = obConfirmed ? 35 : 0;
  const sweepPoints = sweepConfirmed ? 25 : 0;
  const mtfPoints = mtfConfirmed ? 10 : 0;

  const calculatedConfluenceScore = chochPoints + obPoints + sweepPoints + mtfPoints;

  // Use the engine's internal Trade Score if available, otherwise calculated confluence
  const tradeScore = signal?.tradeScore ?? (signal?.confidence ? Math.min(signal.confidence, calculatedConfluenceScore) : calculatedConfluenceScore);
  const isTradeAllowed = (signal?.decisionStatus === 'ALLOWED') || (!signal && tradeScore >= 75);
  const isRejected = !isTradeAllowed;

  // Rejection reasons list
  const rejectionReasons: { titleAr: string; titleEn: string; descAr: string; descEn: string; code: string }[] = [];

  if (!chochConfirmed) {
    rejectionReasons.push({
      code: 'CHOCH_MISSING',
      titleAr: 'غياب تغير الهيكل (CHoCH Unconfirmed)',
      titleEn: 'Change of Character (CHoCH) Unconfirmed',
      descAr: 'لم يحدث كسر صريح للهيكل المعاكس بشمعة زخم واضحة (Displacement Body Close). الدخول يعتبر مخاطرة مبكرة ضد التدفق المؤسساتي.',
      descEn: 'No clear displacement body close confirming a shift in market character. Entering now risks trading against dominant institutional flow.'
    });
  }

  if (!obConfirmed) {
    rejectionReasons.push({
      code: 'OB_EQUILIBRIUM_TRAP',
      titleAr: 'السعر في منتصف النطاق (Equilibrium 50% Trap)',
      titleEn: 'Order Block Not Mitigated / Mid-Range Equilibrium',
      descAr: 'السعر يتداول بالقرب من منطقة التوازن 50% بعيداً عن كتل الأوامر المؤسساتية المخفضة (Discount/Premium OB). صفر ميزة إحصائية وتذبذب عشوائي.',
      descEn: 'Price is hovering in the 50% equilibrium chop, far from fresh institutional discount or premium order blocks. Statistical edge is zero.'
    });
  }

  if (!sweepConfirmed) {
    rejectionReasons.push({
      code: 'SWEEP_MISSING',
      titleAr: 'غياب سحب السيولة (Liquidity Sweep Incomplete)',
      titleEn: 'Liquidity Sweep Incomplete (Retail Trap Warning)',
      descAr: 'لم يتم سحب سيولة القيعان/القمم السابقة (SSL/BSL). الشراء أو البيع هنا يجعل المتداول وقوداً لخروج الحيتان قبل الانعكاس الحقيقي.',
      descEn: 'Key liquidity pools (Equal Highs/Lows) have not been swept. Entering without prior sweep turns retail traders into exit liquidity.'
    });
  }

  if (signal?.marketSuitability?.isSuitable === false) {
    rejectionReasons.push({
      code: 'CHOPPY_MARKET',
      titleAr: 'تذبذب وضغط المتوسطات (Sideways Chop / Compression)',
      titleEn: 'Market Unsuitable for Trading (EMA Compression)',
      descAr: signal.marketSuitability.reasonAr || 'السوق يمر بمرحلة تذبذب عرضي وانضغاط للمتوسطات المتحركة. حظر التداول لحماية رأس المال.',
      descEn: signal.marketSuitability.reasonEn || 'Market is in sideways range-bound chop with EMA compression. Capital preservation mode active.'
    });
  }

  // If score is low but no specific item was flagged, add threshold rule
  if (rejectionReasons.length === 0 && tradeScore < 75) {
    rejectionReasons.push({
      code: 'THRESHOLD_UNMET',
      titleAr: 'الدرجة دون الحد الأدنى المؤسساتي (Score < 75%)',
      titleEn: 'Trade Score Below Minimum Institutional Threshold',
      descAr: `حصل النموذج على ${tradeScore}/100 بينما الحد الأدنى الصارم المطلوب لفتح أي صفقة هو 75%. مبدأ النظام: تفضيل عدم التداول (NO TRADE) على الصفقات الضعيفة.`,
      descEn: `Current setup scored ${tradeScore}/100, which is below the mandatory 75% threshold. Institutional principle: Prefer NO TRADE over subpar setups.`
    });
  }

  return (
    <div className={`rounded-2xl border p-5 shadow-sm transition-colors ${
      isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
    }`}>
      {/* 1. Header with Mode Selector */}
      <div className={`flex flex-wrap items-center justify-between pb-4 mb-4 border-b gap-3 ${
        isLight ? 'border-paper-line-2' : 'border-line'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shadow-xs ${
            isTradeAllowed
              ? isLight ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-emerald-950/60 border-emerald-800 text-emerald-400'
              : isLight ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-amber-950/60 border-amber-800 text-amber-400'
          }`}>
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className={`font-bold text-sm flex items-center gap-2 ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                <span>{isFr ? 'Dissection SMC & Score Interne' : isAr ? 'تشخيص مفاهيم الأموال الذكية ومؤشر Trade Score' : 'SMC Confluence Diagnostics & Trade Score'}</span>
              </h3>
              <span className={`text-xs font-extrabold px-2 py-0.5 rounded border uppercase tracking-wider ${
                isTradeAllowed
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30'
              }`}>
                {isTradeAllowed
                  ? (isAr ? 'صفقة مستوفية للشروط ✓' : 'Setup Approved ✓')
                  : (isAr ? 'حظر التداول (NO TRADE) ' : 'Trade Rejected (NO TRADE) ')}
              </span>
            </div>
            <p className={`text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isFr
                ? `Analyse de confluence CHoCH, Order Block & Balayage de Liquidité pour ${asset.symbol}`
                : isAr
                ? `تحليل توافق الـ CHoCH، كتل الأوامر (OB)، وسحب السيولة لزوج ${asset.symbol}`
                : `Calculated confluence of CHoCH, OB, and liquidity sweep for ${asset.symbol}`}
            </p>
          </div>
        </div>

        {/* View Mode Toggle Buttons */}
        <div className={`flex items-center p-1 rounded-xl border text-xs font-bold max-w-full overflow-x-auto no-scrollbar gap-1 ${
          isLight ? 'bg-slate-100 border-slate-200' : 'bg-slate-900 border-slate-800'
        }`}>
          <button
            onClick={() => setActiveTab('silverBullet')}
            className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shrink-0 ${
              activeTab === 'silverBullet'
                ? isLight ? 'bg-amber-100 text-amber-900 shadow-xs' : 'bg-gold-500 text-black font-extrabold shadow-xs'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Sparkles className={`w-3.5 h-3.5 ${activeTab === 'silverBullet' ? 'text-black' : 'text-gold-500'}`} />
            <span>{isAr ? 'استراتيجية NY Silver Bullet' : 'NY Silver Bullet v2.0'}</span>
          </button>
          <button
            onClick={() => setActiveTab('diagnostic')}
            className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shrink-0 ${
              activeTab === 'diagnostic'
                ? isLight ? 'bg-white text-slate-900 shadow-xs' : 'bg-slate-800 text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Gauge className="w-3.5 h-3.5 text-cyan-500" />
            <span>{isAr ? 'تشخيص الـ Trade Score' : 'Diagnostic Score'}</span>
          </button>
          <button
            onClick={() => setActiveTab('indicators')}
            className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shrink-0 ${
              activeTab === 'indicators'
                ? isLight ? 'bg-white text-slate-900 shadow-xs' : 'bg-slate-800 text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-amber-500" />
            <span>{isAr ? 'المؤشرات الفنية الكلاسيكية' : 'Technical Indicators'}</span>
          </button>
          <button
            onClick={() => setActiveTab('pairProfile')}
            className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shrink-0 ${
              activeTab === 'pairProfile'
                ? isLight ? 'bg-white text-slate-900 shadow-xs' : 'bg-slate-800 text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Crosshair className="w-3.5 h-3.5 text-gold-500" />
            <span>{isAr ? 'ملف الزوج والستوب الهيكلي' : 'Pair Profile & Dynamic SL'}</span>
          </button>
        </div>
      </div>

      {/* 1. NEW YORK SILVER BULLET STRATEGY ENGINE TAB */}
      {activeTab === 'silverBullet' && (
        <div className="space-y-5">
          {/* Executive Header Banner */}
          <div className="p-5 rounded-2xl border border-gold-500/35 bg-gradient-to-r from-gold-500/10 via-surface to-surface-2 shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="font-mono text-xs font-black uppercase tracking-wider text-gold-500">
                    EXCLUSIVE ENGINE · v2.0.0-ny-silver-bullet
                  </span>
                </div>
                <h3 className="text-lg sm:text-xl font-black text-white tracking-tight">
                  {isFr ? 'Le New York Silver Bullet : M15 Préparation & M5 Exécution' : isAr ? 'استراتيجية New York Silver Bullet : تحضير M15 وتنفيذ M5' : 'The New York Silver Bullet: M15 Prep & M5 Execution'}
                </h3>
                <p className="text-xs text-zinc-300 max-w-2xl leading-relaxed">
                  {isAr
                    ? 'المحرك الكمي الحصري المعتمد للذهب الفوري XAU/USD. يعمل بدقة خلال نافذة نيويورك (14:00 - 15:00 GMT / 10:00 - 11:00 EST). يعتمد على سحب سيولة آسيا ولندن، وكسر هيكل MSS باندفاع حقيقي، ودخول بأمر معلق عند منتصف الفجوة 50% CE.'
                    : 'The single institutional engine calibrated strictly for Spot Gold (XAU/USD). Operates within the New York Killzone (14:00-15:00 GMT). Triggers on Asian/London liquidity sweeps, energetic displacement MSS, and 50% CE limit entry.'}
                </p>
              </div>

              <div className="shrink-0 flex sm:flex-col gap-2 font-mono text-xs text-right">
                <div className="px-3 py-1.5 rounded-lg bg-black/40 border border-zinc-800">
                  <span className="text-xs text-zinc-500 block">INSTRUMENT</span>
                  <span className="font-bold text-gold-500">PURE SPOT XAU/USD</span>
                </div>
                <div className="px-3 py-1.5 rounded-lg bg-black/40 border border-zinc-800">
                  <span className="text-xs text-zinc-500 block">KILLZONE</span>
                  <span className="font-bold text-emerald-400">14:00 - 15:00 GMT</span>
                </div>
              </div>
            </div>
          </div>

          {/* 4 Execution Steps Detailed */}
          <div className="space-y-3">
            <h4 className="text-xs font-extrabold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <Layers className="w-4 h-4 text-gold-500" />
              <span>{isAr ? 'مراحل التنفيذ الميكانيكية الأربع (4 Execution Steps)' : 'The 4 Sequential Execution Steps'}</span>
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gold-500 font-mono">PHASE 1: PRE-14:00 GMT</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">AUTOMATIC</span>
                </div>
                <h5 className="text-sm font-bold text-white">
                  {isAr ? 'رسم مستويات سيولة M15' : 'M15 Session Liquidity Mapping'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr 
                    ? 'رسم قمة وقاع جلسة آسيا (00:00 - 08:00 GMT)، جلسة لندن (08:00 - 13:55 GMT)، والقمم السابقة كنقاط استهداف لاصطياد أوامر الوقف.'
                    : 'Maps Asian High/Low (00:00-08:00 GMT) and London High/Low (08:00-13:55 GMT) as primary liquidity raid pools.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-1">
                  Target Pools: Asian High/Low, London High/Low, Session Extremes
                </div>
              </div>

              <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gold-500 font-mono">PHASE 2: 14:00 - 15:00 GMT</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-400">KILLZONE</span>
                </div>
                <h5 className="text-sm font-bold text-white">
                  {isAr ? 'سحب السيولة والارتداد على M5' : 'M5 Liquidity Sweep & Rejection'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr
                    ? 'اختراق السعر لقاع أو قمة الجلسة ثم الإغلاق السريع داخل النطاق أو تكوين ذيل رفض قطعي خلال نافذة الـ 60 دقيقة.'
                    : 'Price pierces M15 BSL or SSL and decisively closes back inside or creates an immediate rejection wick inside the window.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-1">
                  Conditions: Wick raid &gt; 0 pips, Close inside within 60 mins
                </div>
              </div>

              <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gold-500 font-mono">PHASE 3: M5 MSS</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400">DISPLACEMENT</span>
                </div>
                <h5 className="text-sm font-bold text-white">
                  {isAr ? 'كسر الهيكل والاندفاع الحقيقي' : 'Energetic Displacement & Structure Shift'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr
                    ? 'إغلاق شمعة اندفاع تتجاوز آخر قمة/قاع متأرجح. يشترط جسم شمعة > 65% من المدى الإجمالي ومدى يفوق 1.3x من ATR(14).'
                    : 'Energetic candle body close beyond recent swing structure. Requires Candle Body &gt; 65% and Range &gt; 1.3x ATR(14).'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-1">
                  Displacement Math: Body &gt; 65%, Range &gt; 1.3x ATR(14)
                </div>
              </div>

              <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gold-500 font-mono">PHASE 4: EXECUTION</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">LIMIT ORDER</span>
                </div>
                <h5 className="text-sm font-bold text-white">
                  {isAr ? 'فجوة FVG وأمر معلق 50% CE' : 'Unmitigated FVG & 50% CE Limit Entry'}
                </h5>
                <p className="text-xs text-zinc-300 leading-relaxed">
                  {isAr
                    ? 'تأكيد فجوة 3 شموع غير ملموسة. وضع أمر معلق Limit عند الحافة أو 50% Consequent Encroachment مع ستوب هيكلي + 0.5 ATR وعائد >= 1:2.'
                    : 'Identifies unmitigated 3-candle FVG. Places Limit Order at FVG proximal edge or 50% CE. SL at sweep extreme + 0.5x ATR buffer.'}
                </p>
                <div className="text-xs font-mono text-zinc-400 pt-1">
                  Risk Math: SL = Sweep Extreme &plusmn; 0.5x ATR, Net R:R &ge; 1:2.0
                </div>
              </div>
            </div>
          </div>

          {/* The 3 Strict Mechanical Rejection Guards */}
          <div className="p-4 rounded-xl border border-rose-900/30 bg-rose-950/15 space-y-3">
            <h4 className="text-xs font-extrabold uppercase tracking-wider text-rose-400 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-500" />
              <span>{isAr ? 'فلاتر الرفض القطعية الثلاثة (3 Strict Rejection Guards)' : 'The 3 Strict Mechanical Rejection Guards (Auto NO_TRADE)'}</span>
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-zinc-900/90 border border-rose-900/40 space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-rose-400 font-mono">1. TIME WINDOW</span>
                  <span className="text-xs px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300">14:00 - 15:00 GMT</span>
                </div>
                <p className="text-xs text-zinc-300 leading-normal">
                  {isAr ? 'رفض أي فرصة خارج فترة 14:00 - 15:00 GMT منعاً للتداول العشوائي خارج سيولة نيويورك.' : 'Evaluations outside 14:00-15:00 GMT automatically rejected.'}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-zinc-900/90 border border-amber-900/40 space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-amber-400 font-mono">2. WEAK DISPLACEMENT</span>
                  <span className="text-xs px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300">BODY &le; 65%</span>
                </div>
                <p className="text-xs text-zinc-300 leading-normal">
                  {isAr ? 'استبعاد أي شمعة كسر ضعيفة الزخم يكون جسمها <= 65% أو مداها <= 1.3x ATR14.' : 'Rejects breakout candles with body <= 65% or range <= 1.3x ATR14.'}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-zinc-900/90 border border-purple-900/40 space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-purple-400 font-mono">3. NEWS WHIPSAW</span>
                  <span className="text-xs px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300">&gt; 3.5x ATR ANOMALY</span>
                </div>
                <p className="text-xs text-zinc-300 leading-normal">
                  {isAr ? 'حظر الصفقات أثناء الذبذبة العنيفة المصاحبة لبيانات CPI أو NFP أو قرارات الفائدة FOMC.' : 'Anomaly check blocks volatile spikes > 3.5x ATR during CPI, NFP, and FOMC.'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. DIAGNOSTIC VIEW TAB */}
      {activeTab === 'diagnostic' && (
        <div className="space-y-4">
          {/* Main Trade Score Banner with Confluence Gauge */}
          <div className={`p-4 rounded-2xl border transition-all ${
            isTradeAllowed
              ? isLight ? 'bg-gradient-to-r from-emerald-50/70 to-teal-50/50 border-emerald-200' : 'bg-gradient-to-r from-emerald-950/40 to-teal-950/30 border-emerald-800/50'
              : isLight ? 'bg-gradient-to-r from-amber-50/80 via-rose-50/30 to-amber-50/60 border-amber-200' : 'bg-gradient-to-r from-amber-950/40 via-rose-950/20 to-amber-950/30 border-amber-800/50'
          }`}>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center font-black border shadow-xs ${
                  isTradeAllowed
                    ? 'bg-emerald-500 text-white border-emerald-600'
                    : 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/40'
                }`}>
                  <span className="text-base leading-none font-mono-numbers">{tradeScore}</span>
                  <span className="text-xs opacity-80 uppercase tracking-tighter">/ 100</span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-wider font-extrabold text-slate-500 dark:text-slate-400">
                      {isAr ? 'الدرجة المؤسساتية الداخلية (Internal Trade Score):' : 'Internal Trade Score:'}
                    </span>
                    <span className={`text-xs font-black px-2 py-0.5 rounded-full ${
                      isTradeAllowed
                        ? 'bg-emerald-500 text-white'
                        : 'bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/30'
                    }`}>
                      {tradeScore >= 90
                        ? (isAr ? 'A+ نموذج استثنائي' : 'A+ Exceptional')
                        : tradeScore >= 75
                        ? (isAr ? 'A صفقة مؤكدة' : 'A Validated')
                        : (isAr ? 'مرفوضة (دون عتبة 75%)' : 'Rejected (< 75% Threshold)')}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 mt-0.5">
                    {isTradeAllowed
                      ? (isAr ? 'النموذج اجتاز كافة شروط الأموال الذكية SMC الثلاثة بنجاح.' : 'Setup has satisfied all 3 core SMC confluence requirements.')
                      : (isAr ? 'تم رفض فتح الصفقة لحماية رأس المال نظراً لعدم اكتمال التوافق الهيكلي.' : 'Trade rejected by decision engine to preserve capital due to incomplete confluence.')}
                  </p>
                </div>
              </div>

              {/* Threshold indicator */}
              <div className="text-right font-mono text-xs">
                <span className="text-xs text-slate-500 block uppercase">{isAr ? 'عتبة القبول الصارمة' : 'Pass Threshold'}</span>
                <span className="font-extrabold text-slate-700 dark:text-slate-300">
                  75 / 100 <span className="text-xs text-emerald-600 font-sans font-bold">({isAr ? 'مطلوب كحد أدنى' : 'Min Required'})</span>
                </span>
              </div>
            </div>

            {/* Visual Confluence Progress Bar */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-bold text-slate-600 dark:text-slate-400">
                <span className="flex items-center gap-1">
                  <span>{isAr ? 'ميزان التوافق التراكمي (Calculated Confluence):' : 'Calculated Confluence Balance:'}</span>
                </span>
                <span className="font-mono">{tradeScore}%</span>
              </div>
              <div className="w-full h-3 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex relative">
                {/* 75% Threshold Line Marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-rose-500 z-10"
                  style={{ left: '75%' }}
                  title="75% Min Pass Threshold"
                />

                {/* CHoCH bar */}
                <div
                  className={`h-full transition-all duration-500 ${chochConfirmed ? 'bg-cyan-500' : 'bg-slate-300 dark:bg-slate-700'}`}
                  style={{ width: `${chochPoints}%` }}
                  title={`CHoCH: ${chochPoints}/30 pts`}
                />
                {/* OB bar */}
                <div
                  className={`h-full transition-all duration-500 ${obConfirmed ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-700'}`}
                  style={{ width: `${obPoints}%` }}
                  title={`Order Block: ${obPoints}/35 pts`}
                />
                {/* Sweep bar */}
                <div
                  className={`h-full transition-all duration-500 ${sweepConfirmed ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'}`}
                  style={{ width: `${sweepPoints}%` }}
                  title={`Liquidity Sweep: ${sweepPoints}/25 pts`}
                />
                {/* MTF bar */}
                <div
                  className={`h-full transition-all duration-500 ${mtfConfirmed ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-700'}`}
                  style={{ width: `${mtfPoints}%` }}
                  title={`MTF & Trend: ${mtfPoints}/10 pts`}
                />
              </div>

              {/* Legend for Progress Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-slate-500 dark:text-slate-400">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
                  <span>CHoCH ({chochPoints}/30)</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                  <span>Order Block ({obPoints}/35)</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span>Liquidity Sweep ({sweepPoints}/25)</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  <span>MTF ({mtfPoints}/10)</span>
                </span>
              </div>
            </div>
          </div>

          {/* 3. Triad of SMC Confirmations: CHoCH, OB, and Liquidity Sweep */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* 1. CHoCH Card */}
            <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
              chochConfirmed
                ? isLight ? 'bg-cyan-50/50 border-cyan-200' : 'bg-cyan-950/20 border-cyan-800/40'
                : isLight ? 'bg-rose-50/60 border-rose-200' : 'bg-rose-950/20 border-rose-800/40'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-cyan-600 dark:text-cyan-400">
                    <ArrowRightLeft className="w-3.5 h-3.5" />
                    <span>1. CHoCH Confirmation</span>
                  </span>
                  <span className={`text-xs font-black px-2 py-0.5 rounded-md flex items-center gap-1 ${
                    chochConfirmed
                      ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30'
                  }`}>
                    {chochConfirmed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    <span>{chochConfirmed ? (isAr ? 'مؤكد (+30)' : 'CONFIRMED (+30)') : (isAr ? 'غير مكتمل (0)' : 'FAILED (0)')}</span>
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                  {isAr ? 'تغير في الشخصية السعرية (Shift in Structure)' : 'Change of Character Shift'}
                </div>
                <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                  {chochConfirmed
                    ? (isAr ? 'تم كسر القمة/القاع الهيكلي بشمعة إغلاق صريحة مع زخم مؤسساتي عالي.' : 'Structural break confirmed with high displacement volume closing outside range.')
                    : (isAr ? 'لا يوجد كسر صريح للهيكل المعاكس؛ حركة السعر الحالية مجرد تذبذب داخلي (Internal Range).' : 'No valid displacement break across opposing structure; current move is merely internal range.')}
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-slate-200 dark:border-slate-800 text-xs flex items-center justify-between text-slate-500">
                <span>{isAr ? 'الفريم المقاس:' : 'Timeframe:'} 15M / 1H</span>
                <span className="font-mono font-bold">{indicators.structureBreak || 'CHoCH + BOS'}</span>
              </div>
            </div>

            {/* 2. Order Block (OB) Card */}
            <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
              obConfirmed
                ? isLight ? 'bg-indigo-50/50 border-indigo-200' : 'bg-indigo-950/20 border-indigo-800/40'
                : isLight ? 'bg-rose-50/60 border-rose-200' : 'bg-rose-950/20 border-rose-800/40'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400">
                    <Layers className="w-3.5 h-3.5" />
                    <span>2. Order Block (OB)</span>
                  </span>
                  <span className={`text-xs font-black px-2 py-0.5 rounded-md flex items-center gap-1 ${
                    obConfirmed
                      ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30'
                  }`}>
                    {obConfirmed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    <span>{obConfirmed ? (isAr ? 'مؤكد (+35)' : 'CONFIRMED (+35)') : (isAr ? 'فخ توازن (0)' : 'FAILED (0)')}</span>
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                  {isAr ? 'كتلة الأوامر المؤسساتية واختبار المنطقة' : 'Institutional Block & Mitigation'}
                </div>
                <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                  {obConfirmed
                    ? (isAr ? 'السعر يتداول داخل كتلة أوامر مخفضة (Discount) أو مرتفعة (Premium) وتفادى منتصف النطاق.' : 'Price resides strictly in discount/premium institutional block, safely outside 50% equilibrium.')
                    : (isAr ? 'السعر عالق في منتصف النطاق (Equilibrium 50%) — ممنوع الدخول في مناطق التذبذب.' : 'Price is stuck near 50% equilibrium range; high risk of whipsaw with zero statistical edge.')}
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-slate-200 dark:border-slate-800 text-xs flex items-center justify-between text-slate-500">
                <span>{isAr ? 'المنطقة:' : 'Zone:'}</span>
                <span className="font-mono font-bold truncate max-w-[150px]">
                  {signal?.smcEngine?.institutionalZone || (indicators.smc?.orderBlock ? `${indicators.smc.orderBlock.type} 4H` : `$${indicators.support.toFixed(asset.decimalPlaces)} Demand`)}
                </span>
              </div>
            </div>

            {/* 3. Liquidity Sweep Card */}
            <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
              sweepConfirmed
                ? isLight ? 'bg-emerald-50/50 border-emerald-200' : 'bg-emerald-950/20 border-emerald-800/40'
                : isLight ? 'bg-rose-50/60 border-rose-200' : 'bg-rose-950/20 border-rose-800/40'
            }`}>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                    <Target className="w-3.5 h-3.5" />
                    <span>3. Liquidity Sweep</span>
                  </span>
                  <span className={`text-xs font-black px-2 py-0.5 rounded-md flex items-center gap-1 ${
                    sweepConfirmed
                      ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30'
                  }`}>
                    {sweepConfirmed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    <span>{sweepConfirmed ? (isAr ? 'مؤكد (+25)' : 'CONFIRMED (+25)') : (isAr ? 'غير مسحوب (0)' : 'FAILED (0)')}</span>
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                  {isAr ? 'سحب سيولة القيعان/القمم (SSL/BSL)' : 'Liquidity Pool Sweep & Trap Filter'}
                </div>
                <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                  {sweepConfirmed
                    ? (isAr ? 'تم سحب سيولة المتداولين الأفراد بنجاح وابتلاع أوامر الوقف قبل إعطاء إشارة الدخول.' : 'Retail stop-loss pools swept clean; institutional order flow confirmed with no immediate trap.')
                    : (isAr ? 'السيولة الكبرى لم تُسحب بعد — خطر استهداف صانع السوق لوقف الخسارة قبل التحرك.' : 'Liquidity pool above/below remains unswept; entering now exposes trade to institutional stop-hunts.')}
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-slate-200 dark:border-slate-800 text-xs flex items-center justify-between text-slate-500">
                <span>{isAr ? 'حوض السيولة:' : 'Pool:'}</span>
                <span className="font-mono font-bold">{isUptrend ? 'SSL Asian Low Swept' : 'BSL Asian High Swept'}</span>
              </div>
            </div>
          </div>

          {/* 4. REJECTION DIAGNOSTIC BOX: Shows why the trade was rejected */}
          {isRejected && (
            <div className={`p-4 rounded-2xl border transition-all ${
              isLight ? 'bg-amber-50/90 border-amber-300 text-amber-950' : 'bg-amber-950/40 border-amber-700/70 text-amber-200'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <AlertOctagon className="w-5 h-5 text-rose-500 shrink-0 animate-pulse" />
                  <span className="font-bold text-sm">
                    {isFr
                      ? 'Diagnostic de Rejet du Signal : Pourquoi ce trade est bloqué ?'
                      : isAr
                      ? 'تشخيص أسباب حظر الصفقة: لماذا تم رفض التداول في هذا الزوج؟'
                      : 'Trade Rejection Diagnostics: Why was this trade rejected?'}
                  </span>
                </div>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-700 dark:text-rose-300 border border-rose-500/30">
                  {tradeScore} / 100 ({isAr ? 'أقل من 75%' : 'Below 75%'})
                </span>
              </div>

              <p className="text-xs mb-3 font-medium opacity-90 leading-relaxed">
                {isAr
                  ? 'محرك القرارات المؤسساتي مبني على مبدأ صارم: "تفضيل عدم التداول (NO TRADE) على الدخول في صفقات ضعيفة". تم حظر هذه الفرصة للأسباب الفنية التالية:'
                  : 'The institutional decision engine enforces a strict principle: "Prefer NO TRADE over bad trades". This setup was flagged and rejected due to:'}
              </p>

              {/* Rejection Reasons List */}
              <div className="space-y-2">
                {rejectionReasons.map((reason, idx) => (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-xl border flex items-start gap-2.5 text-xs ${
                      isLight ? 'bg-white/80 border-amber-200/80 shadow-2xs' : 'bg-slate-900/80 border-amber-800/40'
                    }`}
                  >
                    <div className="w-5 h-5 rounded-full bg-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0 font-bold text-xs mt-0.5">
                      ✕
                    </div>
                    <div className="flex-1">
                      <div className="font-bold text-slate-900 dark:text-white flex items-center justify-between">
                        <span>{isAr ? reason.titleAr : reason.titleEn}</span>
                        <span className="text-xs font-mono text-rose-600 dark:text-rose-400 font-extrabold uppercase">
                          {reason.code}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-300 mt-0.5 leading-relaxed">
                        {isAr ? reason.descAr : reason.descEn}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Actionable Trader Recommendation */}
              <div className="mt-3 pt-3 border-t border-amber-300/40 flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="font-bold flex items-center gap-1 text-slate-800 dark:text-slate-200">
                  <Info className="w-4 h-4 text-cyan-600" />
                  <span>
                    {isAr
                      ? 'ما الذي ينتظره الذكاء الاصطناعي للموافقة؟'
                      : 'What is the AI waiting for before allowing a trade?'}
                  </span>
                </span>
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  {isAr
                    ? 'انتظار سحب السيولة القادمة + شمعة 15M ارتدادية واضحة خارج منطقة التوازن 50%.'
                    : 'Awaiting clean liquidity sweep + 15M displacement candle exiting 50% equilibrium.'}
                </span>
              </div>
            </div>
          )}

          {/* 5. SUCCESS VALIDATION BOX: If allowed */}
          {isTradeAllowed && (
            <div className={`p-4 rounded-2xl border transition-all ${
              isLight ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950' : 'bg-emerald-950/40 border-emerald-700/70 text-emerald-200'
            }`}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  <span className="font-bold text-sm">
                    {isFr
                      ? 'Validation Confluence Réussie (Trade Score >= 75%)'
                      : isAr
                      ? 'توافق مكتمل لشروط الأموال الذكية (Trade Score >= 75%)'
                      : 'Confluence Verification Passed (Trade Score >= 75%)'}
                  </span>
                </div>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-500 text-white">
                  {tradeScore} / 100 (APPROVED)
                </span>
              </div>
              <p className="text-xs leading-relaxed opacity-90">
                {isAr
                  ? 'تم استيفاء شروط الـ CHoCH، واختبار كتلة الأوامر (OB)، وسحب السيولة بالتزامن مع انتظام الفريمات 4H و 1H. الصفقة مؤهلة للتنفيذ المباشر.'
                  : 'All 3 core SMC confluences (CHoCH, Order Block, and Liquidity Sweep) have aligned with multi-timeframe confirmation. High-probability institutional setup.'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* 3. TECHNICAL INDICATORS TAB (Classic view) */}
      {activeTab === 'indicators' && (
        <div className="space-y-4">
          {/* Grid: Trend, Structure, Resistance, Support */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* Trend */}
            <div className={`p-3 rounded-xl border flex flex-col ${
              isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
            }`}>
              <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isFr ? 'Tendance (Trend)' : isAr ? 'الاتجاه (Trend)' : 'Trend'}
              </span>
              <div className="flex items-center gap-1.5 mt-1">
                {isUptrend ? (
                  <TrendingUp className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                )}
                <span className={`text-xs font-bold ${
                  isUptrend
                    ? 'text-emerald-700 dark:text-emerald-400'
                    : 'text-rose-700 dark:text-rose-400'
                }`}>
                  {asset.trend === 'Bullish'
                    ? (isFr ? 'Haussier (Bullish)' : isAr ? 'صاعد (Uptrend)' : 'Uptrend')
                    : (isFr ? 'Baissier (Bearish)' : isAr ? 'هابط (Downtrend)' : 'Downtrend')}
                </span>
              </div>
              <span className="text-xs mt-1 font-mono-numbers text-slate-500">{asset.trendStrength}% strength</span>
            </div>

            {/* Market Structure */}
            <div className={`p-3 rounded-xl border flex flex-col ${
              isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
            }`}>
              <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isFr ? 'Structure SMC' : isAr ? 'هيكل السوق' : 'Structure'}
              </span>
              <div className="flex items-center gap-1.5 mt-1">
                <Layers className="w-4 h-4 text-gold-500" />
                <span className={`text-xs font-bold ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                  {indicators.structureBreak || 'CHoCH + BOS'}
                </span>
              </div>
              <span className="text-xs mt-1 text-slate-500 font-mono-numbers">
                {indicators.smc?.orderBlock 
                  ? `${indicators.smc.orderBlock.type} (${indicators.smc.orderBlock.timeframe || '4H'})` 
                  : 'Order Block (4H)'}
              </span>
            </div>

            {/* Support */}
            <div className={`p-3 rounded-xl border flex flex-col ${
              isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
            }`}>
              <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isFr ? 'Zone de Support' : isAr ? 'منطقة الدعم (SSL)' : 'Support Zone'}
              </span>
              <div className="flex items-center gap-1.5 mt-1">
                <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span className="text-xs font-black font-mono-numbers text-emerald-700 dark:text-emerald-400">
                  ${indicators.support.toFixed(asset.decimalPlaces)}
                </span>
              </div>
              <span className="text-xs mt-1 text-slate-500">{isFr ? 'Liquidité d\'achat' : isAr ? 'سحب سيولة شرائية' : 'Demand Pool'}</span>
            </div>

            {/* Resistance */}
            <div className={`p-3 rounded-xl border flex flex-col ${
              isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
            }`}>
              <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isFr ? 'Zone de Résistance' : isAr ? 'منطقة المقاومة (BSL)' : 'Resistance Zone'}
              </span>
              <div className="flex items-center gap-1.5 mt-1">
                <Target className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                <span className="text-xs font-black font-mono-numbers text-rose-700 dark:text-rose-400">
                  ${indicators.resistance.toFixed(asset.decimalPlaces)}
                </span>
              </div>
              <span className="text-xs mt-1 text-slate-500">{isFr ? 'Liquidité de vente' : isAr ? 'سحب سيولة بيعية' : 'Supply Pool'}</span>
            </div>
          </div>

          {/* Technical Indicators Breakdown (RSI, EMAs, Volume) */}
          <div className={`p-4 rounded-xl border space-y-3 ${
            isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
          }`}>
            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                {isFr ? 'Indice de Force Relative (RSI 14) :' : isAr ? 'مؤشر القوة النسبية (RSI 14):' : 'RSI (14) Momentum:'}
              </span>
              <span className={`font-mono-numbers font-black ${
                indicators.rsi > 70
                  ? 'text-rose-600 dark:text-rose-400'
                  : indicators.rsi < 30
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-gold-700 dark:text-gold-400'
              }`}>
                {indicators.rsi} {indicators.rsi > 70 ? '(Overbought)' : indicators.rsi < 30 ? '(Oversold)' : '(Neutral)'}
              </span>
            </div>

            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                {isFr ? 'Moyennes Mobiles EMA (20 / 50 / 200) :' : isAr ? 'المتوسطات المتحركة EMA (20/50/200):' : 'EMAs (20 / 50 / 200):'}
              </span>
              <span className="font-mono-numbers text-xs font-bold text-slate-600 dark:text-slate-300">
                ${indicators.ema20.toFixed(asset.decimalPlaces)} / ${indicators.ema50.toFixed(asset.decimalPlaces)} / ${indicators.ema200.toFixed(asset.decimalPlaces)}
              </span>
            </div>

            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                {isFr ? 'Confirmation Volume Institutionnel :' : isAr ? 'تأكيد أحجام التداول (Institutional Volume):' : 'Institutional Volume Confluence:'}
              </span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">
                {isFr ? '✓ Validé au-dessus de la moyenne' : isAr ? '✓ مؤكد أعلى من المتوسط' : '✓ Above 20D Average'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 3. PAIR PROFILE & STRUCTURE-FIRST SL/TP TAB */}
      {activeTab === 'pairProfile' && (() => {
        const pairProfile = signal?.pairProfile || buildDynamicPairProfile(asset, []);
        const dynamicSLTP = signal?.dynamicSLTP || calculateStructureFirstSLTP(
          asset,
          asset.trend === 'Bullish' ? 'BUY' : 'SELL',
          [],
          pairProfile,
          detectMarketStructureAndRegime([], asset, pairProfile)
        );
        const isWait = dynamicSLTP.lifecycleState === 'WAIT';

        return (
          <div className="space-y-4">
            {/* Header Banner */}
            <div className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 ${
              isLight ? 'bg-amber-50/50 border-amber-200/80 text-amber-950' : 'bg-surface border-white/[0.08] text-zinc-100'
            }`}>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-gold-500/10 border border-gold-500/30 flex items-center justify-center text-gold-500">
                  <Crosshair className="w-5 h-5 text-gold-500" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm text-zinc-100">{asset.symbol}</span>
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-gold-500/15 text-gold-500 font-bold">
                      {pairProfile.volatilityRegime.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400">
                    {isAr ? 'تحليل مستقل لكل زوج يرفض المعادلات الثابتة ويحدد الستوب بناءً على هيكل السيولة' : 'Independent quantitative profile: never uses universal SL/TP formulas.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-zinc-400">{isAr ? 'الحالة:' : 'Lifecycle:'}</span>
                <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                  isWait ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                }`}>
                  {dynamicSLTP.lifecycleState}
                </span>
              </div>
            </div>

            {/* Quick Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <div className="p-3 rounded-xl bg-surface border border-white/[0.06]">
                <span className="text-xs font-mono text-zinc-400 block mb-0.5">{isAr ? 'السبريد' : 'Spread'}</span>
                <span className="font-mono text-sm font-bold text-gold-500">{pairProfile.currentSpreadPips} pips</span>
              </div>
              <div className="p-3 rounded-xl bg-surface border border-white/[0.06]">
                <span className="text-xs font-mono text-zinc-400 block mb-0.5">{isAr ? 'المدى اليومي' : 'Daily ADR'}</span>
                <span className="font-mono text-sm font-bold text-zinc-100">{pairProfile.averageDailyRangePips} pips</span>
              </div>
              <div className="p-3 rounded-xl bg-surface border border-white/[0.06]">
                <span className="text-xs font-mono text-zinc-400 block mb-0.5">{isAr ? 'حساسية الأخبار' : 'News Risk'}</span>
                <span className="font-mono text-sm font-bold text-amber-400">{pairProfile.newsSensitivity}</span>
              </div>
              <div className="p-3 rounded-xl bg-surface border border-white/[0.06]">
                <span className="text-xs font-mono text-zinc-400 block mb-0.5">{isAr ? 'الجلسة الحالية' : 'Active Session'}</span>
                <span className="font-mono text-xs font-bold text-emerald-400 truncate block">{pairProfile.typicalSessionBehavior.activeSessionNow}</span>
              </div>
            </div>

            {/* Structure-First Stop Loss Breakdown */}
            <div className="p-4 rounded-xl bg-surface border border-white/[0.06] space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-rose-400" />
                  <span className="font-mono font-bold text-xs text-zinc-200">
                    {isAr ? 'محرك الستوب الهيكلي (Structure-First SL Engine)' : 'Structure-First Stop Loss Engine'}
                  </span>
                </div>
                <span className="font-mono font-bold text-xs text-rose-400">
                  SL = ${dynamicSLTP.stopLossPrice} ({dynamicSLTP.slDistancePips} pips)
                </span>
              </div>

              <div className="p-3 rounded-lg bg-canvas border border-white/[0.04] space-y-2 text-xs">
                <div>
                  <span className="text-xs font-mono text-zinc-400 block">
                    {isAr ? 'مستوى الإلغاء الفني الحقيقي (Technical Invalidation Point):' : 'Technical Invalidation Level:'}
                  </span>
                  <span className="font-mono font-bold text-zinc-100 text-xs">
                    ${dynamicSLTP.invalidationLevel}
                  </span>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {isAr ? dynamicSLTP.invalidationReasonAr : dynamicSLTP.invalidationReason}
                  </p>
                </div>
                <div className="pt-2 border-t border-white/[0.04]">
                  <span className="text-xs font-mono text-zinc-400 block">
                    {isAr ? 'هامش حماية التقلبات المؤسساتي:' : 'Volatility-Aware Buffer:'}
                  </span>
                  <span className="font-mono font-semibold text-gold-500 text-xs">
                    +{dynamicSLTP.volatilityBuffer} ({pairProfile.falseBreakoutFrequency} False Breakout Profile)
                  </span>
                  <p className="text-xs text-zinc-400 mt-0.5">{dynamicSLTP.bufferReason}</p>
                </div>
              </div>
            </div>

            {/* Structure-First Take Profit Targets */}
            <div className="p-4 rounded-xl bg-surface border border-white/[0.06] space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-emerald-400" />
                  <span className="font-mono font-bold text-xs text-zinc-200">
                    {isAr ? 'أهداف السيولة الهيكلية (Realistic High-Probability Targets)' : 'Structure-First Take Profit Targets'}
                  </span>
                </div>
                <span className="font-mono font-bold text-xs text-emerald-400">
                  R:R {dynamicSLTP.overallRR}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 rounded-lg bg-canvas border border-white/[0.04]">
                  <div className="flex items-center justify-between font-mono font-bold text-emerald-400 text-xs mb-1">
                    <span>TP1: ${dynamicSLTP.takeProfit1Price}</span>
                    <span className="text-xs text-zinc-400">1:{dynamicSLTP.takeProfit1RR.toFixed(2)} R:R</span>
                  </div>
                  <p className="text-xs text-zinc-400">
                    {isAr ? 'حجز 50% أرباح فوراً ونقل الوقف إلى نقطة الدخول (Breakeven).' : dynamicSLTP.takeProfit1Reason}
                  </p>
                </div>

                <div className="p-2.5 rounded-lg bg-canvas border border-white/[0.04]">
                  <div className="flex items-center justify-between font-mono font-bold text-emerald-400 text-xs mb-1">
                    <span>TP2: ${dynamicSLTP.takeProfit2Price}</span>
                    <span className="text-xs text-zinc-400">1:{dynamicSLTP.takeProfit2RR.toFixed(2)} R:R</span>
                  </div>
                  <p className="text-xs text-zinc-400">
                    {isAr ? 'هدف السيولة الخارجية الكبرى للهيكل الفني (HTF Liquidity Pool).' : dynamicSLTP.takeProfit2Reason}
                  </p>
                </div>
              </div>
            </div>

            {/* ATR Matrix */}
            <div className="p-4 rounded-xl bg-surface border border-white/[0.06] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono font-bold text-zinc-200">
                  {isAr ? 'مصفوفة التقلبات الحقيقية (Real 14-ATR Matrix):' : 'Multi-Timeframe 14-ATR Matrix:'}
                </span>
                <span className="text-xs font-mono text-zinc-400">{pairProfile.volatilityRegime}</span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                <div className="p-2 rounded-lg bg-canvas border border-white/[0.04]">
                  <span className="text-xs font-mono text-zinc-500 block">15M</span>
                  <span className="font-mono font-bold text-zinc-200">{pairProfile.atrByTimeframe.m15}</span>
                </div>
                <div className="p-2 rounded-lg bg-canvas border border-white/[0.04]">
                  <span className="text-xs font-mono text-zinc-500 block">1H</span>
                  <span className="font-mono font-bold text-gold-500">{pairProfile.atrByTimeframe.h1}</span>
                </div>
                <div className="p-2 rounded-lg bg-canvas border border-white/[0.04]">
                  <span className="text-xs font-mono text-zinc-500 block">4H</span>
                  <span className="font-mono font-bold text-zinc-200">{pairProfile.atrByTimeframe.h4}</span>
                </div>
                <div className="p-2 rounded-lg bg-canvas border border-white/[0.04]">
                  <span className="text-xs font-mono text-zinc-500 block">D1</span>
                  <span className="font-mono font-bold text-zinc-200">{pairProfile.atrByTimeframe.d1}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};
