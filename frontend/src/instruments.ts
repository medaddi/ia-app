// The app's pairs: FXAlexG's watchlist (gold + 28 forex pairs; keep in the order of backend market/pairs.py PAIRS)
export const FOREX_PAIRS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CAD', 'USD/CHF', 'AUD/USD', 'NZD/USD', 'GBP/JPY', 'GBP/AUD', 'GBP/NZD', 'GBP/CAD', 'GBP/CHF', 'EUR/GBP', 'EUR/JPY', 'EUR/AUD', 'EUR/NZD', 'EUR/CAD', 'EUR/CHF', 'AUD/JPY', 'AUD/CAD', 'AUD/CHF', 'AUD/NZD', 'NZD/JPY', 'NZD/CAD', 'NZD/CHF', 'CAD/JPY', 'CAD/CHF', 'CHF/JPY'] as const;
export const INSTRUMENT_SYMBOLS = ['XAU/USD', ...FOREX_PAIRS] as const;
export type InstrumentSymbol = (typeof INSTRUMENT_SYMBOLS)[number];
export type StrategySymbol = { [K in InstrumentSymbol]: K extends `${infer A}/${infer B}` ? `${A}${B}` : never }[InstrumentSymbol];

export const INSTRUMENT_LABELS: Record<InstrumentSymbol, string> = {
  'XAU/USD': 'Gold / Dollar',
  'EUR/USD': 'Euro / Dollar',
  'GBP/USD': 'Pound / Dollar',
  'USD/JPY': 'Dollar / Yen',
  'USD/CAD': 'Dollar / Loonie',
  'USD/CHF': 'Dollar / Franc',
  'AUD/USD': 'Aussie / Dollar',
  'NZD/USD': 'Kiwi / Dollar',
  'GBP/JPY': 'Pound / Yen',
  'GBP/AUD': 'Pound / Aussie',
  'GBP/NZD': 'Pound / Kiwi',
  'GBP/CAD': 'Pound / Loonie',
  'GBP/CHF': 'Pound / Franc',
  'EUR/GBP': 'Euro / Pound',
  'EUR/JPY': 'Euro / Yen',
  'EUR/AUD': 'Euro / Aussie',
  'EUR/NZD': 'Euro / Kiwi',
  'EUR/CAD': 'Euro / Loonie',
  'EUR/CHF': 'Euro / Franc',
  'AUD/JPY': 'Aussie / Yen',
  'AUD/CAD': 'Aussie / Loonie',
  'AUD/CHF': 'Aussie / Franc',
  'AUD/NZD': 'Aussie / Kiwi',
  'NZD/JPY': 'Kiwi / Yen',
  'NZD/CAD': 'Kiwi / Loonie',
  'NZD/CHF': 'Kiwi / Franc',
  'CAD/JPY': 'Loonie / Yen',
  'CAD/CHF': 'Loonie / Franc',
  'CHF/JPY': 'Franc / Yen',
};

export const isInstrument = (s: string | undefined | null): s is InstrumentSymbol => !!s && (INSTRUMENT_SYMBOLS as readonly string[]).includes(s);

// The chart: every timeframe for every pair, and the price precision of each pair
// (the data feed spec: M1 | M5 | M15 | H1 | H4 | the H1 + M5 split view)
export const TIMEFRAMES = ['M15', 'M30', 'H1', 'H2', 'H4', 'D1', 'W1', 'SPLIT'];  // SPLIT = the H4 + H1 split view
/** The pair bar's groups (the spec, Part 6.1). */
export const PAIR_GROUPS: { id: string; label: [string, string, string]; pairs: InstrumentSymbol[] }[] = [
  { id: 'majors', label: ['Majors', 'Majeures', 'الرئيسية'], pairs: ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'USD/CAD', 'AUD/USD', 'NZD/USD'] },
  { id: 'jpy', label: ['JPY Crosses', 'Croisées JPY', 'كروس الين'], pairs: ['CAD/JPY', 'AUD/JPY', 'GBP/JPY', 'EUR/JPY', 'NZD/JPY', 'CHF/JPY'] },
  { id: 'gbpeur', label: ['GBP/EUR Crosses', 'Croisées GBP/EUR', 'كروس GBP/EUR'], pairs: ['GBP/NZD', 'GBP/AUD', 'GBP/CAD', 'GBP/CHF', 'EUR/GBP', 'EUR/AUD', 'EUR/NZD', 'EUR/CAD', 'EUR/CHF'] },
  { id: 'commodity', label: ['Commodity/CHF', 'Matières/CHF', 'السلع/CHF'], pairs: ['AUD/CAD', 'AUD/CHF', 'AUD/NZD', 'NZD/CAD', 'NZD/CHF', 'CAD/CHF'] },
  { id: 'gold', label: ['Gold', 'Or', 'الذهب'], pairs: ['XAU/USD'] },
];
export const PAIR_DECIMALS: Record<InstrumentSymbol, number> = {
  'XAU/USD': 2, 'EUR/USD': 5, 'GBP/USD': 5, 'USD/JPY': 3, 'USD/CAD': 5, 'USD/CHF': 5, 'AUD/USD': 5, 'NZD/USD': 5, 'GBP/JPY': 3, 'GBP/AUD': 5, 'GBP/NZD': 5, 'GBP/CAD': 5, 'GBP/CHF': 5, 'EUR/GBP': 5, 'EUR/JPY': 3, 'EUR/AUD': 5, 'EUR/NZD': 5, 'EUR/CAD': 5, 'EUR/CHF': 5, 'AUD/JPY': 3, 'AUD/CAD': 5, 'AUD/CHF': 5, 'AUD/NZD': 5, 'NZD/JPY': 3, 'NZD/CAD': 5, 'NZD/CHF': 5, 'CAD/JPY': 3, 'CAD/CHF': 5, 'CHF/JPY': 3,
}

/** Gold and forex trade from Sunday 22:00 to Friday 21:00 UTC. */
export function marketOpenNow(now = new Date()): boolean {
  const d = now.getUTCDay(), h = now.getUTCHours();
  if (d === 6) return false;
  if (d === 0) return h >= 22;
  if (d === 5) return h < 21;
  return true;
}
