import { apiFetch } from '../api';
import React, { useState } from 'react';
import { NewsItem, Language } from '../types';
import { 
  Newspaper, 
  RefreshCw, 
  ExternalLink, 
  ShieldAlert, 
  ShieldCheck, 
  Radio, 
  AlertOctagon, 
  Flame, 
  TrendingUp, 
  TrendingDown,
  Layers,
  Clock
} from 'lucide-react';

interface NewsProps {
  news: NewsItem[];
  lang: Language;
  theme?: 'light' | 'dark';
  onRefreshNews?: () => void;
}

export const NewsAISection: React.FC<NewsProps> = ({ news, lang, theme = 'dark', onRefreshNews }) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const filteredNews = news.filter((item) => {
    if (selectedCategory === 'ALL') return true;
    return item.category === selectedCategory;
  });

  // Calculate active high-impact lockouts
  const activeLockouts = news.filter(n => n.importance === 'HIGH' && (n.isLockoutEvent || n.isUncertainty));
  const hasActiveLockout = activeLockouts.length > 0;

  const handleManualSync = async () => {
    setIsRefreshing(true);
    try {
      if (onRefreshNews) {
        await onRefreshNews();
      } else {
        await apiFetch('/api/news/sync', { method: 'POST' });
      }
    } catch (e) {
      // quiet failover
    } finally {
      setTimeout(() => setIsRefreshing(false), 600);
    }
  };

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-surface-3 p-4 sm:p-5 shadow-xl transition-all">
      {/* 1. Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-white/[0.08]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl border border-gold-500/30 bg-gold-500/10 text-gold-500 flex items-center justify-center shadow-md">
            <Newspaper className="w-5 h-5 text-gold-500" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-extrabold text-sm sm:text-base text-white tracking-tight">
                {isFr
                  ? 'Flux Macroéconomique & Impact de Liquidité 24/7'
                  : isAr
                  ? 'رادار الأخبار الماكرو وتأثيرها المباشر على السيولة'
                  : 'Live Macroeconomic News & Liquidity Radar'}
              </h3>
              <span className="flex items-center gap-1.5 text-xs font-bold px-2 py-0.5 rounded-full bg-gold-500/15 text-gold-500 border border-gold-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-gold-500 animate-pulse" />
                <span>{isFr ? 'En Direct' : isAr ? 'بث حي ومحدث' : 'Real-time Feed'}</span>
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isFr
                ? 'Données temps réel (Reuters, Bloomberg, Fed, Yahoo) intégrées dans notre moteur de décision 10 Piliers.'
                : isAr
                ? 'جلب فوري ولحظي من مصادر معتمدة دولياً ومربوطة بمحرك قرارات الصفقات لمنع التداول العشوائي.'
                : 'Live multi-source feeds (Yahoo Finance, Reuters, Bloomberg) directly factoring into our 10-Pillar Decision Engine.'}
            </p>
          </div>
        </div>

        {/* Sync Button & Category Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleManualSync}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-xl border border-gold-500/30 bg-surface text-gold-500 hover:bg-surface-3 transition active:scale-95 cursor-pointer shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gold-500 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>{isFr ? 'Actualiser' : isAr ? 'تحديث الأخبار الآن' : 'Sync Live Feeds'}</span>
          </button>
        </div>
      </div>

      {/* 2. Institutional Macro Sentinel Banner (User rule: Zero trade on high-impact uncertainty) */}
      <div className={`p-3.5 rounded-xl border mb-4 text-xs flex flex-wrap items-center justify-between gap-3 ${
        hasActiveLockout
          ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
          : 'bg-surface border-emerald-500/30 text-zinc-200'
      }`}>
        <div className="flex items-center gap-2.5">
          {hasActiveLockout ? (
            <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0 animate-pulse" />
          ) : (
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
          )}
          <div>
            <div className="font-black text-xs sm:text-sm flex items-center gap-2">
              <span className={hasActiveLockout ? 'text-rose-400' : 'text-emerald-400'}>
                {hasActiveLockout
                  ? (isFr ? 'ALERTE PROTECTION : PROTOCOLE NEWS LOCKOUT ACTIF' : isAr ? 'رادار المخاطر: حظر التداول مفعل (High-Impact News Lockout)' : 'CAPITAL DEFENSE: HIGH-IMPACT NEWS LOCKOUT ACTIVE')
                  : (isFr ? 'MARCHÉ STABLE : CONDITIONS FAVORABLES AUX TRADES' : isAr ? 'المحيط الاقتصادي مستقر: مسموح بتنفيذ الصفقات الفنية' : 'MACRO BACKDROP CLEAR: TECHNICAL SETUPS ALLOWED')}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-zinc-400 mt-0.5">
              {hasActiveLockout
                ? (isFr
                    ? 'Des événements économiques majeurs ou une volatilité incertaine ont été détectés. Le robot bloque tout nouveau trade pour protéger votre capital.'
                    : isAr
                    ? 'تم رصد بيانات اقتصادية فائقة التأثير أو تضارب حاد في السوق. تم تعليق فتح الصفقات آلياً لمنع الانزلاقات السعرية وحماية الحساب بنسبة 100%.'
                    : 'Major economic releases or market uncertainty detected. The desk halts new executions to preserve capital.')
                : (isFr
                    ? 'Aucun risque macroéconomique bloquant. Les signaux techniques SMC sont autorisés avec le strict respect du risque 1%.'
                    : isAr
                    ? 'لا توجد بيانات اقتصادية مفاجئة تعارض الاتجاه. الصفقات الفنية مسموح بتنفيذها بعد تأكيد كسر الهيكل وشمعة التأكيد.'
                    : 'Zero conflicting macro hazards detected. Signals are verified with 1% risk allocation.')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-lg border ${
            hasActiveLockout
              ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
              : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
          }`}>
            {hasActiveLockout
              ? `${activeLockouts.length} ${isAr ? 'أحداث عالية المخاطر' : 'High Risk Events'}`
              : (isAr ? 'حماية 100% نشطة' : '100% Protection')}
          </span>
        </div>
      </div>

      {/* 3. Category Filter Tabs */}
      <div className="flex items-center gap-1.5 p-1 rounded-xl border border-white/[0.08] bg-surface text-xs overflow-x-auto mb-4">
        {[
          { id: 'ALL', labelAr: 'جميع الأخبار', labelFr: 'Toutes', labelEn: 'All Feeds' },
          { id: 'fed', labelAr: 'الفيدرالي والفائدة (Fed)', labelFr: 'Fed & Taux', labelEn: 'Fed & Rates' },
          { id: 'cpi', labelAr: 'التضخم (CPI)', labelFr: 'Inflation CPI', labelEn: 'Inflation CPI' },
          { id: 'nfp', labelAr: 'بيانات التوظيف (NFP)', labelFr: 'Emploi NFP', labelEn: 'Jobs NFP' },
          { id: 'commodities', labelAr: 'الذهب والنفط (Gold & Oil)', labelFr: 'Or & Pétrole', labelEn: 'Gold & Oil' },
          { id: 'geopolitical', labelAr: 'الأزمات الجيوسياسية', labelFr: 'Géopolitique', labelEn: 'Geopolitics' },
        ].map((cat) => (
          <button
            key={cat.id}
            onClick={() => setSelectedCategory(cat.id)}
            className={`px-3 py-1.5 rounded-lg transition font-bold cursor-pointer whitespace-nowrap text-xs ${
              selectedCategory === cat.id
                ? 'bg-gradient-to-r from-gold-200 via-gold-500 to-gold-700 text-ink-strong font-black shadow-sm'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            {isFr ? cat.labelFr : isAr ? cat.labelAr : cat.labelEn}
          </button>
        ))}
      </div>

      {/* 4. Live News Items Grid */}
      <div className="space-y-3">
        {filteredNews.length === 0 ? (
          <div className="p-8 text-center text-zinc-500 text-xs">
            {isAr ? 'لا توجد أخبار في هذا التصنيف حالياً.' : 'No active news in this category.'}
          </div>
        ) : (
          filteredNews.map((item) => {
            const isHigh = item.importance === 'HIGH';
            const isLockout = item.isLockoutEvent || item.isUncertainty;

            return (
              <div
                key={item.id}
                className={`p-4 rounded-xl border transition-all duration-150 ${
                  isLockout
                    ? 'border-rose-500/40 bg-surface hover:border-rose-500/60'
                    : 'border-white/[0.08] bg-surface hover:border-gold-500/40 hover:shadow-md'
                }`}
              >
                {/* Meta Header */}
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    {/* Importance Badge */}
                    <span className={`text-xs font-black px-2 py-0.5 rounded border ${
                      isLockout
                        ? 'bg-rose-500/20 text-rose-400 border-rose-500/40'
                        : isHigh
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                        : 'bg-zinc-800 text-zinc-400 border-white/[0.06]'
                    }`}>
                      {isLockout ? 'LOCKOUT HAZARD' : `${item.importance || 'MEDIUM'} IMPACT`}
                    </span>

                    {/* Impact Asset Badge */}
                    {item.impactAsset && (
                      <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-gold-500/15 text-gold-500 border border-gold-500/30">
                        {item.impactAsset}
                      </span>
                    )}

                    {/* Relative Time and Source */}
                    <span className="text-xs font-medium text-zinc-400 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-zinc-500" />
                      <span>{item.timeAgo || 'الآن'}</span>
                      <span>•</span>
                      <span className="text-zinc-300 font-semibold">{item.source || 'Bloomberg / Reuters'}</span>
                    </span>
                  </div>

                  {/* Impact Verdict */}
                  {item.impactHeadlineAr && (
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                      item.impactVerdict === 'positive'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/25'
                        : item.impactVerdict === 'negative'
                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/25'
                        : 'bg-zinc-800 text-zinc-400 border border-white/[0.06]'
                    }`}>
                      {item.impactHeadlineAr}
                    </span>
                  )}
                </div>

                {/* News Headline */}
                <h4 className="text-sm font-extrabold text-white leading-snug mb-1.5 tracking-tight">
                  {isAr ? (item.titleAr || item.title) : item.title}
                </h4>

                {/* Macro Confluence Reason */}
                <p className="text-xs leading-relaxed text-zinc-400">
                  {isAr ? (item.reasonAr || item.reasonEn) : (item.reasonEn || item.reasonAr)}
                </p>

                {/* External Link */}
                {item.url && (
                  <div className="mt-2.5 pt-2 border-t border-white/[0.06] flex items-center justify-between">
                    <span className="text-xs text-zinc-500 font-mono">
                      {item.category?.toUpperCase()} CATALYST
                    </span>
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-gold-500 hover:text-gold-500 transition"
                    >
                      <span>{isFr ? 'Source originale' : isAr ? 'المصدر الأصلي' : 'Original Source'}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
