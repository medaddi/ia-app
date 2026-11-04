import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api';
import { useAgentOverlay } from '../agentOverlay';
import { chartSpec, type InstrumentSymbol } from '../instruments';
import { SmcChart, type SmcChartCandle } from './SmcChart';
import { TradingViewChart, useChartingLibrary } from '../tradingview/TradingViewChart';

const PROVIDER_TF: Record<string, string> = { M5: '5M', M15: '15M', M30: '30M', H1: '1H', H4: '4H', D1: '1D', W1: '1W' };

/**
 * One pane of the 4-chart split screen: its own candles and its own agent's overlay (subscribed for this symbol only),
 * so every chart renders exactly what its dedicated agent emits.
 */
export const AgentChartPanel: React.FC<{ symbol: InstrumentSymbol; lang: string; onOpen?: (s: InstrumentSymbol) => void }> = ({ symbol, lang, onOpen }) => {
  const spec = chartSpec(symbol);
  const [tf, setTf] = useState(spec.entryTf);
  const [candles, setCandles] = useState<SmcChartCandle[]>([]);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [quote, setQuote] = useState<{ time: number; source: string } | null>(null);
  const { overlay } = useAgentOverlay(symbol, 2000);
  const tvChart = useChartingLibrary();

  const load = useCallback(async () => {
    if (document.hidden) return;
    try {
      const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${PROVIDER_TF[tf]}&count=300`, { cache: 'no-store' });
      const j = await res.json();
      if (j.success && Array.isArray(j.candles)) { setCandles(j.candles); setUpdatedAt(Date.now()); setQuote(j.quoteTime ? { time: j.quoteTime, source: j.priceSource || '' } : null); }
    } catch { /* keep the last candles */ }
  }, [symbol, tf]);

  useEffect(() => { if (tvChart !== false) return; setCandles([]); load(); const id = setInterval(load, 2000); return () => clearInterval(id); }, [load, tvChart]);

  return (
    <div className="min-w-0">
      {tvChart ? (
        <>
          <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
            <span className="font-mono font-semibold text-white">{symbol} · {tf}</span>
            {overlay && <span className="truncate text-slate-400" title={overlay.statusBannerText}>{overlay.fsmState} · {overlay.statusBannerText.split(' · ').slice(2).join(' · ')}</span>}
          </div>
          <TradingViewChart symbol={symbol} timeframe={tf} overlay={overlay} decimals={symbol === 'XAU/USD' ? 2 : 5} lang={lang} compact onTimeframeChange={setTf} />
        </>
      ) : (
        <SmcChart symbol={symbol} candles={candles} result={null} overlay={overlay} timeframe={tf} timeframes={spec.timeframes} entryTf={spec.entryTf}
          emas={spec.emas} emaNote={spec.emaNote} updatedAt={updatedAt} onTimeframeChange={setTf} lang={lang} compact quote={quote} />
      )}
      {onOpen && (
        <button onClick={() => onOpen(symbol)} className="mt-1 text-[11px] text-slate-400 hover:text-gold-300 cursor-pointer">
          {lang === 'ar' ? 'فتح هاد الزوج' : lang === 'fr' ? 'Ouvrir cette paire' : 'Open this pair'} →
        </button>
      )}
    </div>
  );
};
