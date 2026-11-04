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

// Each pair's chart follows its own agent (backend app/agents/): the timeframe it decides on, the timeframes offered and
// the EMAs shown for context
export interface ChartSpec { entryTf: string; timeframes: string[]; emas: number[]; emaNote: string }
const H1_SPEC = { entryTf: 'H1', timeframes: ['M15', 'M30', 'H1', 'H4', 'D1'], emas: [50, 200] };
export const CHART_SPEC: Record<InstrumentSymbol, ChartSpec> = {
  'XAU/USD': { ...H1_SPEC, emaNote: 'trend on H1' },  // XAUUSD_TrendBreakout_Agent: 20-hour channel breakout in the EMA50 / EMA200 trend
  'EUR/USD': { ...H1_SPEC, emaNote: 'context on H1' },  // EURUSD_AsianFade_Agent: 10-hour channel fade, 00–06 GMT
  'GBP/USD': { entryTf: 'H4', timeframes: ['M30', 'H1', 'H4', 'D1', 'W1'], emas: [50, 200], emaNote: 'context on H4' },  // GBPUSD_ChannelFade_Agent
  'AUD/CHF': { ...H1_SPEC, emaNote: 'context on H1' },  // AUDCHF_AsianFade_Agent: 40-hour channel fade, 22–05 GMT
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[s];
