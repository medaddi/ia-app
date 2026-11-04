// Instruments the backend analyses (keep in the order of backend STRATEGY_DEFS)
// Only the pairs whose strategy held up in its test (backend strategies/_pairs.py PAIRS)
export const FOREX_PAIRS = ['EUR/USD', 'GBP/USD', 'EUR/CHF', 'AUD/CAD', 'AUD/CHF'] as const;
export const INSTRUMENT_SYMBOLS = ['XAU/USD', ...FOREX_PAIRS] as const;
export type InstrumentSymbol = (typeof INSTRUMENT_SYMBOLS)[number];
export type StrategySymbol = { [K in InstrumentSymbol]: K extends `${infer A}/${infer B}` ? `${A}${B}` : never }[InstrumentSymbol];

export const INSTRUMENT_LABELS: Record<InstrumentSymbol, string> = {
  'XAU/USD': 'Gold', 'EUR/USD': 'Euro / Dollar', 'GBP/USD': 'Pound / Dollar', 'EUR/CHF': 'Euro / Franc', 'AUD/CAD': 'Aussie / Loonie',
  'AUD/CHF': 'Aussie / Franc',
};

export const isInstrument = (s: string | undefined | null): s is InstrumentSymbol => !!s && (INSTRUMENT_SYMBOLS as readonly string[]).includes(s);

// Each pair's chart follows its own agent (backend app/agents/): the timeframe it decides on, the timeframes offered and
// the EMAs shown for context
export interface ChartSpec { entryTf: string; timeframes: string[]; emas: number[]; emaNote: string }
const H1_SPEC = { entryTf: 'H1', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1'], emas: [50, 200] };
export const CHART_SPEC: Record<InstrumentSymbol, ChartSpec> = {
  'XAU/USD': { ...H1_SPEC, emaNote: 'trend on H1' },  // XAUUSD_FastIntraday_Agent: Asian breakout + London dip on H1, every trade closed within 3 h
  'EUR/USD': { ...H1_SPEC, emaNote: 'context on H1' },  // EURUSD_AsianFade_Agent: 10-hour channel fade, 00–06 GMT, ADX < 35
  'GBP/USD': { ...H1_SPEC, emaNote: 'trend on H1' },  // GBPUSD_TrendPullback_Agent: 40-hour fade in the trend's direction (EMA200)
  'EUR/CHF': { ...H1_SPEC, emaNote: 'context on H1' },  // EURCHF_AsianFade_Agent: 10-hour channel fade, 00–06 GMT
  'AUD/CAD': { ...H1_SPEC, emaNote: 'context on H1' },  // AUDCAD_RangeFade_Agent: 40-hour channel fade
  'AUD/CHF': { ...H1_SPEC, emaNote: 'context on H1' },  // AUDCHF_RangeFade_Agent: 40-hour channel fade, ADX < 35
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[s];
