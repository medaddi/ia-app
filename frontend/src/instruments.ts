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
export const CHART_SPEC: Record<'gold' | 'forex', ChartSpec> = {
  // H1 Trend Breakout: EMA50 vs EMA200 and the 20-hour range, all on H1
  gold: { entryTf: 'H1', timeframes: ['M15', 'H1', 'H4', 'D1'], emas: [50, 200], emaNote: 'trend on H1' },
  // FXAlexG: weekly → daily → H4 top-down; EMA20 is the trend filter on W1 and D1
  forex: { entryTf: 'H4', timeframes: ['H1', 'H4', 'D1', 'W1'], emas: [20], emaNote: 'trend on D1 / W1' },
};
export const chartSpec = (s: InstrumentSymbol): ChartSpec => CHART_SPEC[s === 'XAU/USD' ? 'gold' : 'forex'];
