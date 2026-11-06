// The app's pairs (keep in the order of backend market/pairs.py PAIRS, gold first)
export const FOREX_PAIRS = ['EUR/USD', 'GBP/USD', 'EUR/CHF', 'AUD/CAD', 'AUD/CHF'] as const;
export const INSTRUMENT_SYMBOLS = ['XAU/USD', ...FOREX_PAIRS] as const;
export type InstrumentSymbol = (typeof INSTRUMENT_SYMBOLS)[number];
export type StrategySymbol = { [K in InstrumentSymbol]: K extends `${infer A}/${infer B}` ? `${A}${B}` : never }[InstrumentSymbol];

export const INSTRUMENT_LABELS: Record<InstrumentSymbol, string> = {
  'XAU/USD': 'Gold', 'EUR/USD': 'Euro / Dollar', 'GBP/USD': 'Pound / Dollar', 'EUR/CHF': 'Euro / Franc', 'AUD/CAD': 'Aussie / Loonie',
  'AUD/CHF': 'Aussie / Franc',
};

export const isInstrument = (s: string | undefined | null): s is InstrumentSymbol => !!s && (INSTRUMENT_SYMBOLS as readonly string[]).includes(s);

// The chart: every timeframe for every pair, and the price precision of each pair
export const TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'];
export const PAIR_DECIMALS: Record<InstrumentSymbol, number> = {
  'XAU/USD': 2, 'EUR/USD': 5, 'GBP/USD': 5, 'EUR/CHF': 5, 'AUD/CAD': 5, 'AUD/CHF': 5,
};

/** Gold and forex trade from Sunday 22:00 to Friday 21:00 UTC. */
export function marketOpenNow(now = new Date()): boolean {
  const d = now.getUTCDay(), h = now.getUTCHours();
  if (d === 6) return false;
  if (d === 0) return h >= 22;
  if (d === 5) return h < 21;
  return true;
}
