import { apiFetch } from '../api';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, RefreshCw, Activity } from 'lucide-react';
import { SmcChart, SmcChartCandle } from './SmcChart';
import { ExunuActiveSetup } from './ExunuActiveSetup';
import type { ExunuSMCResult } from '../strategyTypes';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, chartSpec, type ChartSpec, type InstrumentSymbol } from '../instruments';
import type { StrategyResult } from '../strategyTypes';

interface ExunuTerminalViewProps {
  initialSymbol?: InstrumentSymbol;
  onSymbolChange?: (symbol: InstrumentSymbol) => void; // keeps the app header on the pair shown here
  onOpenTelegram?: () => void;
  lang?: string;
}

// Review mode: ?asOf=<unix seconds> replays the strategy at a past moment (read-only)
const REVIEW_AS_OF = (() => {
  try { return Number(new URLSearchParams(window.location.search).get('asOf')) || 0; } catch { return 0; }
})();
const asOfParam = REVIEW_AS_OF > 0 ? `&asOf=${REVIEW_AS_OF}` : '';

// Gold: H1 breakout + Bollinger reversion · EUR/USD, GBP/USD: RSI(2) Connors H4 · other forex: FXAlexG GPA (W1 / D1 / H4 trend, W1 / D1 AOI, 30m entry)
const INSTRUMENTS = Object.fromEntries(INSTRUMENT_SYMBOLS.map(s => [s, { label: INSTRUMENT_LABELS[s], ...chartSpec(s) }])) as Record<InstrumentSymbol, ChartSpec & { label: string }>;
const PROVIDER_TF: Record<string, string> = { M5: '5M', M15: '15M', M30: '30M', H1: '1H', H4: '4H', D1: '1D', W1: '1W' };
const LIVE_MS = 1000; // analysis, candles and price every second (the feed itself updates about once a second)

// Each pair remembers the timeframe it was last viewed on (default: the strategy's decision timeframe)
const tfKey = (s: string) => `ld_chart_tf_${s}`;
const savedTf = (s: InstrumentSymbol) => {
  try { const v = localStorage.getItem(tfKey(s)); return v && INSTRUMENTS[s].timeframes.includes(v) ? v : INSTRUMENTS[s].entryTf; } catch { return INSTRUMENTS[s].entryTf; }
};

export const ExunuTerminalView: React.FC<ExunuTerminalViewProps> = ({ initialSymbol = 'XAU/USD', onSymbolChange, onOpenTelegram, lang = 'en' }) => {
  const [symbol, setSymbolState] = useState<InstrumentSymbol>(initialSymbol);
  const [timeframe, setTimeframeState] = useState<string>(() => savedTf(initialSymbol));
  const setSymbol = (s: InstrumentSymbol) => { setSymbolState(s); setTimeframeState(savedTf(s)); onSymbolChange?.(s); };
  const setTimeframe = (tf: string) => { setTimeframeState(tf); try { localStorage.setItem(tfKey(symbol), tf); } catch { /* storage blocked */ } };
  // The app picked another pair (search, dashboard card): follow it
  useEffect(() => { if (initialSymbol !== symbol) { setSymbolState(initialSymbol); setTimeframeState(savedTf(initialSymbol)); } }, [initialSymbol]);
  const [candles, setCandles] = useState<SmcChartCandle[]>([]);
  const [bundle, setBundle] = useState<ExunuSMCResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number>(0);

  const result: StrategyResult | null = bundle?.strategy ?? null;
  const inst = INSTRUMENTS[symbol];

  const loadCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(sym)}&timeframe=${PROVIDER_TF[tf]}&count=400${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.success && Array.isArray(json.candles)) setCandles(json.candles);
    } catch {
      // keep the last good candles
    }
  }, []);

  const loadStrategy = useCallback(async (sym: string): Promise<ExunuSMCResult | null> => {
    try {
      const res = await apiFetch(`/api/exunu/setup?symbol=${encodeURIComponent(sym)}${asOfParam}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.success && json.result?.strategy) { setBundle(json.result); return json.result; }
    } catch {
      // next poll retries
    }
    return null;
  }, []);

  const refreshAll = useCallback(async () => {
    setIsLoading(true);
    const [b] = await Promise.all([loadStrategy(symbol), loadCandles(symbol, timeframe)]);
    if (b) setUpdatedAt(Date.now());
    setIsLoading(false);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  useEffect(() => { setBundle(null); setCandles([]); refreshAll(); }, [symbol, timeframe]);

  // Live loop: every second the analysis and the candles (with the forming one) are reloaded together,
  // so the drawings, the checklist and the chart always come from the same moment. Paused while the tab is hidden.
  useEffect(() => {
    if (REVIEW_AS_OF > 0) return;
    let busy = false;
    const id = setInterval(async () => {
      if (busy || document.hidden) return;
      busy = true;
      const [b] = await Promise.all([loadStrategy(symbol), loadCandles(symbol, timeframe)]);
      if (b) setUpdatedAt(Date.now());
      busy = false;
    }, LIVE_MS);
    return () => clearInterval(id);
  }, [symbol, timeframe, loadStrategy, loadCandles]);

  const t = (en: string, fr: string, ar: string) => (lang === 'ar' ? ar : lang === 'fr' ? fr : en);
  const agents = bundle ? [
    { name: t('Trend', 'Tendance', 'الاتجاه'), summary: bundle.agents.structure_agent.summary, ok: result?.bias.direction !== 'NEUTRAL' },
    { name: result?.symbol === 'XAUUSD' ? t('Breakout', 'Cassure', 'الاختراق') : result?.strategy === 'RSI2_Connors_H4' ? t('RSI(2) pullback', 'Repli RSI(2)', 'تراجع RSI(2)') : t('Area of interest', 'Zone (AOI)', 'منطقة الاهتمام'),
      summary: bundle.agents.liquidity_agent.summary, ok: !!result?.checklist.find(c => ['sweep', 'zone', 'breakout', 'retest', 'aoi', 'rsi'].includes(c.key) && c.passed) },
    { name: t('Risk', 'Risque', 'المخاطرة'), summary: bundle.agents.risk_agent.summary, ok: !!result?.setup && !!result.checklist.find(c => ['rr', 'stop'].includes(c.key) && c.passed) },
    { name: t('Decision', 'Décision', 'القرار'), summary: bundle.agents.cto_agent.summary, ok: result?.status === 'SIGNAL' },
  ] : [];

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-3 bg-surface border border-line rounded-[var(--radius-card)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="hidden sm:block">
            <div className="text-sm font-semibold tracking-wide text-white">{t('Live chart', 'Graphique en direct', 'الشارت المباشر')}</div>
            <div className="text-xs text-slate-500">{result?.strategyName ?? t('Loading…', 'Chargement…', 'كيتحمل…')}</div>
          </div>
          <div role="tablist" aria-label={t('Instrument', 'Instrument', 'الأداة')} className="flex items-center rounded-lg bg-surface-2 border border-line p-0.5 overflow-x-auto max-w-full">
            {INSTRUMENT_SYMBOLS.map(id => (
              <button key={id} role="tab" aria-selected={symbol === id}
                onClick={() => setSymbol(id)}
                className={`h-9 px-3 shrink-0 rounded-md text-xs font-medium transition-colors ${symbol === id ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-100'}`}>
                <span className="font-mono">{id}</span><span className="hidden 2xl:inline text-slate-500"> · {INSTRUMENTS[id].label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {REVIEW_AS_OF > 0 && <span className="px-2 py-1 rounded-md bg-gold-500/15 text-gold-200 text-xs font-medium">Review {new Date(REVIEW_AS_OF * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC</span>}
          <div className="hidden md:flex items-center gap-2 font-mono text-xs">
            <span className={`w-1.5 h-1.5 rounded-full ${result?.market.isOpen ? 'bg-emerald-400' : 'bg-slate-500'}`} aria-hidden="true" />
            <span className="text-slate-400">{result?.market.isOpen ? t('Market open', 'Marché ouvert', 'السوق مفتوح') : t('Market closed', 'Marché fermé', 'السوق مغلق')}</span>
            <span className="text-white font-semibold tabular-nums">{result ? result.price.toFixed(result.spec.decimals) : '—'}</span>
          </div>
          {onOpenTelegram && (
            <button onClick={onOpenTelegram} className="h-9 px-3 inline-flex items-center gap-1.5 rounded-lg border border-line text-xs text-slate-200 hover:bg-surface-2">
              <Send className="w-4 h-4 text-gold-400" aria-hidden="true" /><span className="hidden sm:inline">Telegram</span>
            </button>
          )}
          <button onClick={refreshAll} disabled={isLoading} className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-line text-slate-300 hover:bg-surface-2" aria-label={t('Refresh the analysis', 'Actualiser l’analyse', 'تحديث التحليل')}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-gold-400' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 min-w-0">
          <SmcChart symbol={symbol} candles={candles} result={result} timeframe={timeframe} timeframes={inst.timeframes} entryTf={inst.entryTf}
            emas={inst.emas} emaNote={inst.emaNote} updatedAt={REVIEW_AS_OF > 0 ? 0 : updatedAt}
            onTimeframeChange={setTimeframe} isLoading={isLoading} onRefresh={refreshAll} lang={lang} />
        </div>
        <div className="lg:col-span-4 min-w-0">
          <ExunuActiveSetup symbol={symbol} result={result} explanation={bundle?.explanation} lang={lang} />
          {(bundle as any)?.tradeDesk && (
            <div className="mt-4 p-4 rounded-[var(--radius-card)] bg-surface border border-line text-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-slate-200">{t('AI trade desk · last check before sending', 'Desk IA · dernier contrôle avant envoi', 'مكتب الذكاء · آخر فحص قبل الإرسال')}</span>
                <span className={`font-mono font-semibold ${(bundle as any).tradeDesk.approved ? 'text-emerald-300' : 'text-rose-300'}`}>
                  {(bundle as any).tradeDesk.approved ? t('Approved', 'Validé', 'مقبول') : t('Blocked', 'Bloqué', 'محبوس')}
                </span>
              </div>
              <ul className="space-y-1.5">
                {(bundle as any).tradeDesk.checks.map((c: { key: string; label: string; passed: boolean; detail: string }) => (
                  <li key={c.key} className="flex gap-2">
                    <span className={`mt-0.5 w-4 h-4 shrink-0 rounded-full flex items-center justify-center text-[10px] ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>{c.passed ? '✓' : '✕'}</span>
                    <span className="min-w-0"><span className="text-slate-200">{({
                      rules: t('Strategy rules re-checked', 'Règles de la stratégie revérifiées', 'شروط الاستراتيجية متحقق منها'),
                      data: t('Live, fresh data', 'Données en direct et fraîches', 'معطيات مباشرة وجديدة'),
                      drift: t('Price still near the entry', 'Prix encore proche de l’entrée', 'الثمن باقي قريب من الدخول'),
                      liveRr: t('R:R still valid from the live price', 'R:R encore valable au prix actuel', 'العائد/المخاطرة باقي صالح'),
                      market: t('Market open, no news window', 'Marché ouvert, pas de news', 'السوق مفتوح، بلا أخبار'),
                      exposure: t('Currency exposure (max 2 the same way)', 'Exposition par devise (max 2 dans le même sens)', 'التعرض للعملة (2 فالاتجاه نفسو كحد أقصى)'),
                    } as Record<string, string>)[c.key] ?? c.label}</span>
                      <span className="block text-slate-500 break-words" dir="ltr">{c.detail}</span></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {agents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {agents.map((a, i) => (
            <div key={a.name} className="p-3 rounded-xl bg-surface border border-line">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-gold-400" aria-hidden="true" />{i + 1}. {a.name}</span>
                <span className={`text-xs font-medium ${a.ok ? 'text-emerald-300' : 'text-slate-500'}`}>{a.ok ? t('OK', 'Validé', 'محقق') : t('Not met', 'Non validé', 'ما محققش')}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed break-words">{a.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
