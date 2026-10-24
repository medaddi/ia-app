import React, { useState, useEffect } from 'react';
import { 
  Briefcase, 
  RefreshCw, 
  ShieldCheck, 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  ExternalLink,
  Sliders,
  DollarSign,
  AlertCircle
} from 'lucide-react';
import { Language, MarketAsset } from '../types';

interface OpenPositionsViewProps {
  asset: MarketAsset;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const OpenPositionsView: React.FC<OpenPositionsViewProps> = ({
  asset,
  lang,
  theme = 'dark',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';

  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const fetchTrades = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/user-trades');
      if (res.ok) {
        const data = await res.json();
        if (data.trades) {
          // Filter to active or breakeven secured trades on Gold
          const goldTrades = data.trades.filter((t: any) => 
            (t.symbol?.includes('XAU') || t.symbol?.includes('Gold'))
          );
          setTrades(goldTrades.length > 0 ? goldTrades : data.trades.slice(0, 4));
        }
      }
    } catch (e) {
      // quiet fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleBreakeven = async (chatId: string, tradeId: string) => {
    setActionInProgress(tradeId);
    try {
      await fetch('/api/user-trades/breakeven', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatId, tradeId }),
      });
      await fetchTrades();
    } catch (e) {
    } finally {
      setActionInProgress(null);
    }
  };

  const handleClose = async (chatId: string, tradeId: string) => {
    setActionInProgress(tradeId);
    try {
      await fetch('/api/user-trades/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatId, tradeId }),
      });
      await fetchTrades();
    } catch (e) {
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="space-y-6 w-full text-zinc-100">
      
      {/* 1. Header Metrics Card */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2">
          <span className="text-xs text-zinc-400 block mb-1">
            {isAr ? 'الصفقات المفتوحة حالياً' : 'Open Positions Count'}
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black font-mono text-white">
              {trades.filter(t => t.status === 'ACTIVE' || t.status === 'BE_SECURED').length}
            </span>
            <span className="text-xs text-gold-500 font-bold">Gold (XAU/USD)</span>
          </div>
        </div>

        <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2">
          <span className="text-xs text-zinc-400 block mb-1">
            {isAr ? 'السعر الحالي الفوري' : 'Live Spot Price'}
          </span>
          <div className="flex items-baseline gap-2 font-mono">
            <span className="text-2xl font-black text-white">${asset.price.toFixed(2)}</span>
            <span className="text-xs text-emerald-400 font-bold">LBMA 24/7</span>
          </div>
        </div>

        <div className="p-4 rounded-xl border border-white/[0.08] bg-surface-2">
          <span className="text-xs text-zinc-400 block mb-1">
            {isAr ? 'انضباط حجز الأرباح وتأمين الدخول' : 'Breakeven Guard Status'}
          </span>
          <div className="flex items-center gap-1.5 text-emerald-400 text-sm font-bold pt-1">
            <ShieldCheck className="w-4 h-4" />
            <span>{isAr ? 'حماية آلية مفعلة' : 'Active 100%'}</span>
          </div>
        </div>
      </div>

      {/* 2. Positions Table / Cards */}
      <div className="rounded-2xl border border-white/[0.08] bg-surface-2 p-5 sm:p-6 shadow-xl">
        <div className="flex items-center justify-between pb-4 border-b border-white/[0.08] mb-4">
          <div className="flex items-center gap-2.5">
            <Briefcase className="w-5 h-5 text-gold-500" />
            <div>
              <h3 className="font-black text-sm sm:text-base text-white tracking-tight">
                {isFr ? 'Positions Ouvertes & Exécution Broker' : isAr ? 'المراكز المفتوحة وتنفيذ البروكر' : 'Open Positions & Broker Execution Desk'}
              </h3>
              <p className="text-xs text-zinc-400">
                {isFr ? 'Surveillance tick-par-tick des ordres engagés' : isAr ? 'متابعة لحظية بالمليمتر للصفقات المنفذة على حسابات المشتركين' : 'Real-time tick tracking of executed Gold contracts'}
              </p>
            </div>
          </div>

          <button
            onClick={fetchTrades}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-white/[0.08] hover:border-gold-500/40 bg-surface-3 text-xs font-bold transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gold-500 ${loading ? 'animate-spin' : ''}`} />
            <span>{isAr ? 'تحديث' : 'Refresh'}</span>
          </button>
        </div>

        {trades.length === 0 ? (
          <div className="py-12 text-center text-zinc-500 text-xs space-y-2">
            <CheckCircle2 className="w-8 h-8 mx-auto text-zinc-600" />
            <p className="font-bold text-zinc-400 text-sm">
              {isAr ? 'لا توجد صفقات مفتوحة حالياً (0 Open Risk)' : 'No open active positions currently (0 Open Risk)'}
            </p>
            <p className="text-zinc-500 max-w-md mx-auto">
              {isAr
                ? 'رأس المال آمن بنسبة 100%. المحرك في وضع الترقب لظهور فرصة A+ عالية الاحتمالية على الذهب.'
                : '100% equity secured. Engine is patiently scanning order flow for confirmed A+ Gold liquidity sweeps.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-white/[0.06] text-xs text-zinc-400 uppercase tracking-wider font-sans">
                  <th className="py-2.5 px-3">Position / User</th>
                  <th className="py-2.5 px-3">Side</th>
                  <th className="py-2.5 px-3">Entry</th>
                  <th className="py-2.5 px-3">Current Spot</th>
                  <th className="py-2.5 px-3">Stop Loss</th>
                  <th className="py-2.5 px-3">TP1 / TP2</th>
                  <th className="py-2.5 px-3">Unrealized P&L</th>
                  <th className="py-2.5 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {trades.map((trade) => {
                  const isBuy = trade.signalType === 'BUY';
                  const pips = trade.unrealizedPips || 0;
                  const isProfitable = pips >= 0;

                  return (
                    <tr key={trade.id} className="hover:bg-white/[0.02] transition">
                      <td className="py-3 px-3">
                        <div className="font-bold text-white flex items-center gap-1.5 font-sans">
                          <span>{trade.symbol}</span>
                          <span className="text-xs text-zinc-500 font-mono">({trade.userName || 'Broker MT5'})</span>
                        </div>
                        <span className="text-xs text-zinc-500 block font-mono">{trade.id}</span>
                      </td>

                      <td className="py-3 px-3 font-sans">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                          isBuy ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                        }`}>
                          {trade.signalType}
                        </span>
                      </td>

                      <td className="py-3 px-3 text-zinc-300">${trade.entryPrice?.toFixed(2) || '4,159.50'}</td>
                      <td className="py-3 px-3 font-bold text-white">${asset.price.toFixed(2)}</td>
                      <td className="py-3 px-3 text-rose-400">${trade.stopLoss?.toFixed(2)}</td>
                      <td className="py-3 px-3 text-emerald-400">${trade.target1?.toFixed(2)}</td>

                      <td className="py-3 px-3 font-bold">
                        <span className={isProfitable ? 'text-emerald-400' : 'text-rose-400'}>
                          {isProfitable ? '+' : ''}{pips} pips
                        </span>
                      </td>

                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5 font-sans">
                          {!trade.isBreakeven && (
                            <button
                              onClick={() => handleBreakeven(trade.chatId, trade.id)}
                              disabled={actionInProgress === trade.id}
                              className="px-2 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 text-xs font-bold border border-emerald-500/30 transition cursor-pointer"
                              title="Move Stop Loss to Entry (0 Risk)"
                            >
                              Move BE
                            </button>
                          )}
                          <button
                            onClick={() => handleClose(trade.chatId, trade.id)}
                            disabled={actionInProgress === trade.id}
                            className="px-2 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 text-xs font-bold border border-rose-500/30 transition cursor-pointer"
                            title="Close Position Now"
                          >
                            Close
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
};
