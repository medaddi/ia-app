// Instruments the backend analyses (keep in the order of backend STRATEGY_DEFS)
// Only the pairs whose strategy held up in its test (backend strategies/_pairs.py PAIRS)
export const FOREX_PAIRS = ['EUR/USD', 'GBP/USD', 'AUD/CHF'] as const;
export const INSTRUMENT_SYMBOLS = ['XAU/USD', ...FOREX_PAIRS] as const;
export type InstrumentSymbol = (typeof INSTRUMENT_SYMBOLS)[number];
export type StrategySymbol = { [K in InstrumentSymbol]: K extends `${infer A}/${infer B}` ? `${A}${B}` : never }[InstrumentSymbol];

export const INSTRUMENT_LABELS: Record<InstrumentSymbol, string> = {
  'XAU/USD': 'Gold', 'EUR/USD': 'Euro / Dollar', 'GBP/USD': 'Pound / Dollar', 'AUD/CHF': 'Aussie / Franc',
};

export const isInstrument = (s: string | undefined | null): s is InstrumentSymbol => !!s && (INSTRUMENT_SYMBOLS as readonly string[]).includes(s);

// What the chart shows for each pair's strategy (keep in sync with backend strategies/pairs/config.py): the timeframe it
// decides on, the timeframes offered, and the EMAs on the chart (EMA50 vs EMA200: the trend a breakout needs, context for a fade)
export interface ChartSpec { entryTf: string; timeframes: string[]; emas: number[]; emaNote: string }
const H1_SPEC = { timeframes: ['M15', 'M30', 'H1', 'H4', 'D1'], emas: [50, 200] };
const H4_SPEC = { timeframes: ['M30', 'H1', 'H4', 'D1', 'W1'], emas: [50, 200] };
export const CHART_SPEC: Record<InstrumentSymbol, ChartSpec> = {
  'XAU/USD': { entryTf: 'H1', ...H1_SPEC, emaNote: 'trend on H1' },  // channel breakout in the trend
  'EUR/USD': { entryTf: 'H1', ...H1_SPEC, emaNote: 'context on H1' },  // Asian-session channel fade
  'GBP/USD': { entryTf: 'H4', ...H4_SPEC, emaNote: 'context on H4' },  // H4 channel fade
  'AUD/CHF': { entryTf: 'H1', ...H1_SPEC, emaNote: 'context on H1' },  // Asian-session channel fade
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[s];
