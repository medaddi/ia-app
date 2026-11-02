// Instruments the backend analyses (keep in the order of backend STRATEGY_DEFS)
export const FOREX_PAIRS = ['EUR/USD', 'GBP/USD', 'USD/CAD', 'NZD/USD', 'EUR/CHF', 'NZD/CAD', 'AUD/CAD', 'AUD/CHF'] as const;
export const INSTRUMENT_SYMBOLS = ['XAU/USD', ...FOREX_PAIRS] as const;
export type InstrumentSymbol = (typeof INSTRUMENT_SYMBOLS)[number];
export type StrategySymbol = { [K in InstrumentSymbol]: K extends `${infer A}/${infer B}` ? `${A}${B}` : never }[InstrumentSymbol];

export const INSTRUMENT_LABELS: Record<InstrumentSymbol, string> = {
  'XAU/USD': 'Gold', 'EUR/USD': 'Euro / Dollar', 'GBP/USD': 'Pound / Dollar', 'USD/CAD': 'Dollar / Loonie', 'NZD/USD': 'Kiwi / Dollar',
  'EUR/CHF': 'Euro / Franc', 'NZD/CAD': 'Kiwi / Loonie', 'AUD/CAD': 'Aussie / Loonie', 'AUD/CHF': 'Aussie / Franc',
};

export const isInstrument = (s: string | undefined | null): s is InstrumentSymbol => !!s && (INSTRUMENT_SYMBOLS as readonly string[]).includes(s);

// What the chart shows for each strategy: the timeframes it reads and the moving averages its rules use
export interface ChartSpec { entryTf: string; timeframes: string[]; emas: number[]; emaNote: string }
export type StrategyKind = 'gold' | 'rsi2' | 'london' | 'report' | 'forex';
// Each pair runs the strategy that held up on it (keep in sync with the backend configs): RSI(2) Connors H4 (RSI2_CONFIGS),
// London breakout H1 (LONDON_CONFIGS), FXAlexG GPA on the others
export const RSI2_PAIRS: readonly InstrumentSymbol[] = ['EUR/USD'];
export const LONDON_PAIRS: readonly InstrumentSymbol[] = ['GBP/USD'];
// A report strategy that won its 2-year test and runs live (backend REPORT_CONFIGS with live: true)
export const REPORT_PAIRS: readonly InstrumentSymbol[] = ['AUD/CAD'];
export const strategyKind = (s: string): StrategyKind => (s === 'XAU/USD' ? 'gold' : (RSI2_PAIRS as readonly string[]).includes(s) ? 'rsi2'
  : (LONDON_PAIRS as readonly string[]).includes(s) ? 'london' : (REPORT_PAIRS as readonly string[]).includes(s) ? 'report' : 'forex');
export const CHART_SPEC: Record<StrategyKind, ChartSpec> = {
  // H1 Trend Breakout: EMA50 vs EMA200 and the 20-hour range, all on H1
  gold: { entryTf: 'H1', timeframes: ['M15', 'H1', 'H4', 'D1'], emas: [50, 200], emaNote: 'trend on H1' },
  // FXAlexG Set & Forget GPA: trend W1 / D1 / H4, AOI on W1 / D1, 50 EMA rejection on H4 and 1H, 30m engulfing entry
  // RSI(2) Connors pullback: EMA200 trend filter and EMA5 exit, all on H4
  rsi2: { entryTf: 'H4', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1', 'W1'], emas: [5, 200], emaNote: 'exit / trend on H4' },
  // London breakout: the Asian range (00:00–07:00 GMT) and the first strong H1 close beyond it before 11:00 GMT
  london: { entryTf: 'H1', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1'], emas: [50, 200], emaNote: 'context on H1' },
  // Report mean reversion (AUD/CAD): Bollinger (20, 2) + Stochastic (14, 3, 3) on H4
  report: { entryTf: 'H4', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1'], emas: [20], emaNote: 'Bollinger middle' },
  forex: { entryTf: 'M30', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1', 'W1'], emas: [50], emaNote: 'rejection on H4 / 1H' },
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[strategyKind(s)];
