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
const M5_SPEC = { entryTf: 'M5', timeframes: ['M5', 'M15', 'M30', 'H1', 'H4'], emas: [50, 200], emaNote: 'context on M5' };
export const CHART_SPEC: Record<InstrumentSymbol, ChartSpec> = {
  'XAU/USD': M5_SPEC,  // XAUUSD_Sovereign_SMC_Agent: M15 liquidity, M5 MSS + FVG ∩ OTE
  'EUR/USD': M5_SPEC,  // EURUSD_AsianSweep_FVG_Agent: M15 Asian range, M5 execution
  'GBP/USD': M5_SPEC,  // GBPUSD_LondonJudas_SMT_Agent: D1 / M15 levels, M5 SMT + OB
  'AUD/CHF': { entryTf: 'H1', timeframes: ['M15', 'H1', 'H4', 'D1'], emas: [50, 200], emaNote: 'context on H1' },  // H4 range, H1 trigger
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[s];
