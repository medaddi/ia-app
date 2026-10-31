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
export type StrategyKind = 'gold' | 'rsi2' | 'forex';
// RSI(2) Connors H4 runs on the pairs where it held up; the other pairs run FXAlexG GPA (keep in sync with backend RSI2_CONFIGS)
export const RSI2_PAIRS: readonly InstrumentSymbol[] = ['EUR/USD', 'GBP/USD'];
export const strategyKind = (s: string): StrategyKind => (s === 'XAU/USD' ? 'gold' : (RSI2_PAIRS as readonly string[]).includes(s) ? 'rsi2' : 'forex');
export const CHART_SPEC: Record<StrategyKind, ChartSpec> = {
  // H1 Trend Breakout: EMA50 vs EMA200 and the 20-hour range, all on H1
  gold: { entryTf: 'H1', timeframes: ['M15', 'H1', 'H4', 'D1'], emas: [50, 200], emaNote: 'trend on H1' },
  // FXAlexG Set & Forget GPA: trend W1 / D1 / H4, AOI on W1 / D1, 50 EMA rejection on H4 and 1H, 30m engulfing entry
  // RSI(2) Connors pullback: EMA200 trend filter and EMA5 exit, all on H4
  rsi2: { entryTf: 'H4', timeframes: ['H1', 'H4', 'D1', 'W1'], emas: [5, 200], emaNote: 'exit / trend on H4' },
  forex: { entryTf: 'M30', timeframes: ['M30', 'H1', 'H4', 'D1', 'W1'], emas: [50], emaNote: 'rejection on H4 / 1H' },
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[strategyKind(s)];
