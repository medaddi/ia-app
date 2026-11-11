/**
 * The TradingView Advanced Charts datafeed (JS API) on the app's own candles: the same feed the pair agents decide on
 * (backend /api/exunu/candles), so the chart shows exactly the prices behind every signal. The library draws; the app
 * supplies the data (TradingView's library ships no market data of its own).
 */
import { apiFetch } from '../api';
import { INSTRUMENT_LABELS, INSTRUMENT_SYMBOLS, PAIR_DECIMALS, type InstrumentSymbol } from '../instruments';

// TradingView resolution → the backend's timeframe code
const RES_TF: Record<string, string> = { '5': '5M', '15': '15M', '30': '30M', '60': '1H', '240': '4H', '1D': '1D', D: '1D', '1W': '1W', W: '1W' };
export const TF_RES: Record<string, string> = { M5: '5', M15: '15', M30: '30', H1: '60', H4: '240', D1: '1D', W1: '1W' };
const RES_SEC: Record<string, number> = { '5': 300, '15': 900, '30': 1800, '60': 3600, '240': 14400, '1D': 86400, D: 86400, '1W': 604800, W: 604800 };
const SUPPORTED = ['5', '15', '30', '60', '240', '1D', '1W'];
const DECIMALS: Record<InstrumentSymbol, number> = PAIR_DECIMALS;
const POLL_MS = 2000;

interface Bar { time: number; open: number; high: number; low: number; close: number; volume?: number }
type Any = any; // the library's own typings ship with its files (not in this repo)

async function candles(symbol: string, resolution: string, count: number): Promise<Bar[]> {
  const res = await apiFetch(`/api/exunu/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${RES_TF[resolution] ?? '1H'}&count=${count}`, { cache: 'no-store' });
  const j = await res.json();
  if (!j.success || !Array.isArray(j.candles)) throw new Error(j.error || 'No candles');
  // the library wants milliseconds
  return j.candles.map((c: Bar) => ({ time: c.time * 1000, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume ?? 0 }));
}

export function createDatafeed(): Any {
  const subs = new Map<string, number>();
  return {
    onReady(cb: (c: Any) => void) {
      setTimeout(() => cb({ supported_resolutions: SUPPORTED, supports_marks: false, supports_timescale_marks: false, supports_time: true,
        exchanges: [{ value: 'LD', name: 'LiquidityDissection', desc: 'The app feed' }], symbols_types: [{ name: 'All', value: '' }] }), 0);
    },
    searchSymbols(input: string, _ex: string, _type: string, onResult: (r: Any[]) => void) {
      const q = input.toUpperCase().replace('/', '');
      onResult(INSTRUMENT_SYMBOLS.filter(s => s.replace('/', '').includes(q)).map(s => ({
        symbol: s, full_name: s, description: INSTRUMENT_LABELS[s], exchange: 'LD', ticker: s, type: s === 'XAU/USD' ? 'commodity' : 'forex' })));
    },
    resolveSymbol(name: string, onResolve: (s: Any) => void, onError: (e: string) => void) {
      const sym = INSTRUMENT_SYMBOLS.find(s => s === name || s.replace('/', '') === name.toUpperCase().replace('/', ''));
      if (!sym) { setTimeout(() => onError('Unknown symbol'), 0); return; }
      const d = DECIMALS[sym];
      setTimeout(() => onResolve({
        name: sym, ticker: sym, full_name: sym, description: INSTRUMENT_LABELS[sym], type: sym === 'XAU/USD' ? 'commodity' : 'forex',
        session: '24x7', timezone: 'Etc/UTC', exchange: 'LD', listed_exchange: 'LD', format: 'price', minmov: 1, pricescale: 10 ** d,
        has_intraday: true, has_daily: true, has_weekly_and_monthly: true, intraday_multipliers: ['5', '15', '30', '60', '240'],
        supported_resolutions: SUPPORTED, volume_precision: 0, data_status: 'streaming' }), 0);
    },
    async getBars(si: Any, resolution: string, period: Any, onResult: (bars: Bar[], meta: Any) => void, onError: (e: string) => void) {
      try {
        // the backend keeps the most recent candles: one request covers the whole visible history
        const all = await candles(si.name, resolution, 1000);
        const from = period.from * 1000, to = period.to * 1000;
        const bars = all.filter(b => b.time >= from && b.time < to);
        onResult(bars, { noData: bars.length === 0 && (!all.length || all[0].time >= to) });
      } catch (e) {
        onError(String(e));
      }
    },
    subscribeBars(si: Any, resolution: string, onTick: (b: Bar) => void, guid: string) {
      let last = 0;
      const step = (RES_SEC[resolution] ?? 3600) * 1000;
      const tick = async () => {
        if (document.hidden) return;
        try {
          const bars = await candles(si.name, resolution, 3);
          for (const b of bars) if (b.time >= last && b.time > Date.now() - 3 * step) { onTick(b); last = b.time; }
        } catch { /* the next poll retries */ }
      };
      subs.set(guid, window.setInterval(tick, POLL_MS));
    },
    unsubscribeBars(guid: string) {
      const id = subs.get(guid);
      if (id) window.clearInterval(id);
      subs.delete(guid);
    },
  };
}
