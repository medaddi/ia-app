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
