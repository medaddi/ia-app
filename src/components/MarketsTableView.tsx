import React, { useState } from 'react';
import { MarketAsset, AISignal, Language } from '../types';
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  Search, 
  TrendingUp, 
  SlidersHorizontal,
  ChevronRight,
  ShieldCheck,
  Activity,
  Layers,
  ArrowRight,
  Crosshair
} from 'lucide-react';
import { TradingBadge, MarketRegimeTag, TradingButton } from './common/TradingDesignSystem';
import { PairProfileInspectorModal } from './PairProfileInspectorModal';

interface MarketsTableViewProps {
  assets: MarketAsset[];
  signals: AISignal[];
  selectedSymbol: string;
  onSelectAsset: (asset: MarketAsset) => void;
  onNavigateTab: (tab: string) => void;
  lang: Language;
}

export const MarketsTableView: React.FC<MarketsTableViewProps> = ({
  assets,
  signals,
  selectedSymbol,
  onSelectAsset,
  onNavigateTab,
  lang,
}) => {
  const [filterType, setFilterType] = useState<'ALL' | 'SPOT'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<'symbol' | 'price' | 'change' | 'volatility'>('symbol');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [inspectingAsset, setInspectingAsset] = useState<MarketAsset | null>(null);

  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const filteredAssets = assets.filter((asset) => {
    if (filterType === 'SPOT' && asset.symbol !== 'XAU/USD') return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return asset.symbol.toLowerCase().includes(q) || asset.name.toLowerCase().includes(q);
    }
    return true;
  });

  const getSignalForAsset = (symbol: string) => {
    return signals.find((s) => s.symbol === symbol && s.status === 'ACTIVE');
  };

  const getRegimeForAsset = (asset: MarketAsset) => {
    return 'INSTITUTIONAL EXPANSION';
  };

  const getStrategyForAsset = (asset: MarketAsset) => {
    return 'ICT Silver Bullet & London/NY Sweep';
  };

  return (
    <div className="space-y-4">
      {/* Table Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-surface-2 border border-white/[0.08]">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            placeholder={isAr ? 'بحث في الأسواق...' : isFr ? 'Filtrer les actifs...' : 'Filter markets by pair or name...'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-8 pl-8 pr-3 text-xs rounded-lg bg-surface border border-white/[0.08] text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-gold-500 focus:ring-1 focus:ring-gold-500"
          />
        </div>

        {/* Gold Asset Categories */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
          {[
            { id: 'ALL', label: isFr ? 'Tout l\'Or' : isAr ? 'كافة أسواق الذهب' : 'All Gold' },
            { id: 'SPOT', label: isFr ? 'Or Spot (XAU/USD)' : isAr ? 'الذهب الفوري (XAU/USD)' : 'Spot Gold' },
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setFilterType(cat.id as any)}
              className={`px-3 py-1 text-xs font-mono rounded-md border transition-colors cursor-pointer select-none whitespace-nowrap ${
                filterType === cat.id
                  ? 'bg-gold-500/15 text-gold-500 border-gold-500/40 font-semibold'
                  : 'bg-surface text-zinc-400 border-white/[0.06] hover:text-zinc-200 hover:bg-surface-3'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Professional Market Table */}
      <div className="rounded-xl border border-white/[0.08] bg-surface-2 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/[0.08] bg-surface text-xs font-mono uppercase tracking-wider text-zinc-400">
                <th className="py-3 px-4 font-medium">PAIR</th>
                <th className="py-3 px-4 font-medium text-right">PRICE</th>
                <th className="py-3 px-4 font-medium text-right">24H CHANGE</th>
                <th className="py-3 px-4 font-medium">MARKET REGIME</th>
                <th className="py-3 px-4 font-medium">ACTIVE STRATEGY</th>
                <th className="py-3 px-4 font-medium text-center">CONFIRMATION</th>
                <th className="py-3 px-4 font-medium text-center">ACTION / SETUP</th>
                <th className="py-3 px-4 font-medium text-right">TERMINAL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] text-xs">
              {filteredAssets.map((asset) => {
                const signal = getSignalForAsset(asset.symbol);
                const regime = signal?.marketRegime?.replace('_', ' ') || signal?.dynamicSLTP?.marketRegime?.replace('_', ' ') || getRegimeForAsset(asset);
                const strategy = signal?.strategyUsed || signal?.pairProfile?.bestPerformingStrategies[0] || getStrategyForAsset(asset);
                const isSelected = asset.symbol === selectedSymbol;
                const isPositive = asset.change24h >= 0;
                const isWait = signal?.signalType === 'WAIT' || signal?.lifecycleState === 'WAIT';

                return (
                  <tr
                    key={asset.symbol}
                    onClick={() => onSelectAsset(asset)}
                    className={`transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-gold-500/10 hover:bg-gold-500/15'
                        : 'hover:bg-white/[0.02]'
                    }`}
                  >
                    {/* Pair */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div className="flex flex-col">
                          <span className="font-mono font-bold text-zinc-100 text-sm">
                            {asset.symbol}
                          </span>
                          <span className="text-xs text-zinc-500 font-sans">
                            {asset.name}
                          </span>
                        </div>
                        {isSelected && (
                          <span className="w-1.5 h-1.5 rounded-full bg-gold-500" />
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setInspectingAsset(asset);
                          }}
                          title={isAr ? 'عرض الملف الفني والستوب الهيكلي' : 'Inspect Pair Profile & Dynamic SL/TP'}
                          className="p-1 rounded text-zinc-400 hover:text-gold-500 hover:bg-gold-500/10 transition-colors cursor-pointer"
                        >
                          <SlidersHorizontal className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>

                    {/* Price */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <span className="font-mono font-bold text-zinc-100 text-sm">
                        {asset.price.toLocaleString(undefined, {
                          minimumFractionDigits: asset.price < 10 ? 4 : 2,
                          maximumFractionDigits: asset.price < 10 ? 4 : 2,
                        })}
                      </span>
                    </td>

                    {/* Change */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <span
                        className={`inline-flex items-center gap-0.5 font-mono text-xs font-semibold ${
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {isPositive ? (
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        ) : (
                          <ArrowDownRight className="w-3.5 h-3.5" />
                        )}
                        {asset.change24h > 0 ? '+' : ''}
                        {asset.change24h.toFixed(2)}%
                      </span>
                    </td>

                    {/* Regime */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <MarketRegimeTag regime={regime} />
                    </td>

                    {/* Strategy */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 text-zinc-300">
                        <Layers className="w-3 h-3 text-zinc-500 shrink-0" />
                        <span className="text-xs truncate max-w-[180px]">{strategy}</span>
                      </div>
                    </td>

                    {/* Confirmation Score */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      {signal ? (
                        <div className="inline-flex items-center gap-1">
                          <span className={`font-mono font-bold text-xs ${isWait ? 'text-amber-400' : 'text-gold-500'}`}>
                            {signal.confidence}%
                          </span>
                          <span className="text-xs text-zinc-500 font-mono">
                            ({signal.riskReward || '1:3.0'})
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs font-mono text-zinc-500">
                          Evaluating
                        </span>
                      )}
                    </td>

                    {/* Action / Setup */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      {signal ? (
                        <TradingBadge variant={isWait ? 'wait' : signal.signalType === 'BUY' ? 'buy' : 'sell'}>
                          {isWait ? 'WAIT (PATIENT)' : `${signal.signalType} ${signal.symbol}`}
                        </TradingBadge>
                      ) : (
                        <TradingBadge variant="wait">WAIT</TradingBadge>
                      )}
                    </td>

                    {/* Action button */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setInspectingAsset(asset);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-mono text-gold-500 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/25 transition-colors cursor-pointer"
                        >
                          <Crosshair className="w-3 h-3" />
                          <span>Profile</span>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectAsset(asset);
                            onNavigateTab('chart');
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-mono font-medium text-zinc-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] transition-colors cursor-pointer"
                        >
                          <span>Trade</span>
                          <ArrowRight className="w-3 h-3 text-zinc-400" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pair Profile Modal Inspector */}
      {inspectingAsset && (
        <PairProfileInspectorModal
          isOpen={!!inspectingAsset}
          onClose={() => setInspectingAsset(null)}
          asset={inspectingAsset}
          signal={getSignalForAsset(inspectingAsset.symbol)}
          lang={lang}
        />
      )}
    </div>
  );
};
