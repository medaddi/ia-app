import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Flame, Sparkles, Filter, Check, RefreshCw } from 'lucide-react';
import { MarketAsset, Language } from '../types';

interface LiveTickerBarProps {
  assets: MarketAsset[];
  selectedSymbol: string;
  onSelectAsset: (asset: MarketAsset) => void;
  lang: Language;
  theme?: 'light' | 'dark';
  isSyncing?: boolean;
  onForceRefresh?: () => void;
  lastSyncTime?: number;
}

export const LiveTickerBar: React.FC<LiveTickerBarProps> = ({
  assets,
  selectedSymbol,
  onSelectAsset,
  lang,
  theme = 'light',
  isSyncing = false,
  onForceRefresh,
  lastSyncTime,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  // Filter: 'all' | 'open' | 'closed'
  const [filterMode, setFilterMode] = useState<'all' | 'open' | 'closed'>('all');

  const filteredAssets = assets.filter((asset) => {
    if (filterMode === 'open') return asset.isMarketOpen !== false;
    if (filterMode === 'closed') return asset.isMarketOpen === false;
    return true;
  });

  return (
    <div className={`border-b px-4 py-2.5 overflow-x-auto no-scrollbar transition-colors duration-200 ${
      isLight ? 'bg-paper border-paper-line-2' : 'bg-canvas border-line'
    }`}>
      <div className="flex items-center justify-between gap-3 min-w-max">
        <div className="flex items-center gap-2.5">
          {/* Title & Quick Filter */}
          <div className={`flex items-center gap-2 text-xs font-bold pl-1 pr-3 border-r shrink-0 ${
            isLight ? 'text-slate-700 border-paper-line-2' : 'text-slate-300 border-line'
          }`}>
            <div className="w-5 h-5 rounded-md bg-gold-500/15 flex items-center justify-center text-gold-700 dark:text-gold-400">
              <Flame className="w-3.5 h-3.5 animate-pulse" />
            </div>
            <span className="tracking-wide text-[11.5px] font-extrabold uppercase">
              {isFr ? 'Dissection :' : isAr ? 'الأصول المتاحة :' : 'Markets:'}
            </span>

            {/* Quick Filter Pills */}
            <div className={`flex items-center p-0.5 rounded-lg border text-xs ml-1.5 ${
              isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line-2'
            }`}>
              <button
                onClick={() => setFilterMode('all')}
                className={`px-2 py-0.5 rounded-md font-bold transition cursor-pointer ${
                  filterMode === 'all'
                    ? 'bg-gold-500 text-ink-strong shadow-xs font-extrabold'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                {isFr ? 'Tous' : isAr ? 'الكل' : 'All'}
              </button>
              <button
                onClick={() => setFilterMode('open')}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-md font-bold transition cursor-pointer ${
                  filterMode === 'open'
                    ? 'bg-emerald-600 text-white shadow-xs font-extrabold'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>{isFr ? 'Ouverts' : isAr ? 'المفتوحة' : 'Open'}</span>
              </button>
              <button
                onClick={() => setFilterMode('closed')}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-md font-bold transition cursor-pointer ${
                  filterMode === 'closed'
                    ? 'bg-amber-600 text-white shadow-xs font-extrabold'
                    : isLight ? 'text-slate-600 hover:text-slate-900' : 'text-slate-400 hover:text-white'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                <span>{isFr ? 'Fermés' : isAr ? 'المغلقة' : 'Closed'}</span>
              </button>
            </div>
          </div>

          {filteredAssets.map((asset) => {
            const isSelected = asset.symbol === selectedSymbol;
            const isPositive = asset.change24h >= 0;
            const isClosed = asset.isMarketOpen === false;
            
            return (
              <button
                key={asset.id}
                onClick={() => onSelectAsset(asset)}
                className={`group flex items-center gap-3 px-3.5 py-1.5 rounded-xl text-xs transition-all duration-200 border cursor-pointer ${
                  isSelected
                    ? isLight
                      ? 'bg-white border-gold-500 shadow-md shadow-gold-500/15 ring-2 ring-gold-500/30'
                      : 'bg-surface-3 border-gold-500/80 shadow-lg shadow-black/50 ring-1 ring-gold-500/40'
                    : isLight
                    ? 'bg-white/90 border-paper-line-2 hover:bg-white hover:border-gold-500/50 text-slate-700 hover:shadow-xs hover:-translate-y-0.5'
                    : 'bg-surface-2 border-line hover:bg-surface-3 hover:border-line-2 text-slate-300 hover:text-white hover:-translate-y-0.5'
                }`}
              >
                <div className="flex flex-col text-left">
                  <div className="flex items-center gap-1.5">
                    <span className={`font-black tracking-tight font-mono-numbers text-xs ${
                      isSelected
                        ? isLight ? 'text-gold-700' : 'text-gold-400'
                        : isLight ? 'text-slate-900' : 'text-slate-200'
                    }`}>
                      {asset.symbol}
                    </span>
                    
                    {/* Market status badge */}
                    {isClosed ? (
                      <span className="text-xs px-1.5 py-0.2 rounded font-black bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                        {isFr ? 'FERMÉ' : isAr ? 'مغلق' : 'CLOSED'}
                      </span>
                    ) : (
                      <span className="text-xs px-1.5 py-0.2 rounded font-black bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 flex items-center gap-0.5">
                        <span className="w-1 h-1 rounded-full bg-emerald-500"></span>
                        {isFr ? 'OTC SPOT' : isAr ? 'فوري' : 'LIVE OTC'}
                      </span>
                    )}

                    {isSelected && (
                      <span className="w-1.5 h-1.5 rounded-full bg-gold-500 animate-pulse"></span>
                    )}
                  </div>
                  <span className={`text-xs font-medium ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                    {isFr ? (asset.frenchName || asset.name) : isAr ? asset.arabicName.split('/')[0].trim() : asset.category.toUpperCase()}
                  </span>
                </div>

                <div className="flex flex-col items-end">
                  <span className={`font-mono-numbers font-extrabold text-xs ${
                    isLight ? 'text-slate-900' : 'text-slate-100'
                  }`}>
                    ${asset.price.toLocaleString(undefined, { minimumFractionDigits: asset.decimalPlaces })}
                  </span>
                  <div className={`flex items-center gap-0.5 text-xs font-mono-numbers font-bold ${
                    isPositive
                      ? isLight ? 'text-emerald-600' : 'text-emerald-400'
                      : isLight ? 'text-rose-600' : 'text-rose-400'
                  }`}>
                    {isPositive ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : (
                      <TrendingDown className="w-3 h-3" />
                    )}
                    <span>{isPositive ? '+' : ''}{asset.change24h}%</span>
                  </div>
                </div>

                {/* Trend Tag */}
                <span className={`text-xs px-1.5 py-0.5 rounded-md font-bold uppercase tracking-wider ${
                  asset.trend === 'Bullish'
                    ? isLight ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/80' : 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/40'
                    : asset.trend === 'Bearish'
                    ? isLight ? 'bg-rose-50 text-rose-700 border border-rose-200/80' : 'bg-rose-950/80 text-rose-300 border border-rose-700/40'
                    : isLight ? 'bg-paper text-slate-700 border border-paper-line-2' : 'bg-slate-800 text-slate-300 border border-slate-700'
                }`}>
                  {asset.trend}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
