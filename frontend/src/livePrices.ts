/**
 * Live prices of every traded pair, one request per second for all of them (backend /api/market/prices, whose own
 * cache asks each provider at most once a second whatever the number of viewers), shared by every component that
 * shows a price. Paused while the tab is hidden.
 */
import { useEffect, useState } from 'react';
import { apiFetch } from './api';

export interface LivePrice { price: number; quoteTime: number | null; source: string; at: number }

const prices = new Map<string, LivePrice>();
const subs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let busy = false;

async function tick() {
  if (busy || document.hidden) return;
  busy = true;
  try {
    const res = await apiFetch('/api/market/prices', { cache: 'no-store' });
    const j = await res.json();
    if (j.success) {
      for (const [sym, p] of Object.entries(j.prices as Record<string, any>)) {
        if (p && p.price > 0) prices.set(sym, { price: p.price, quoteTime: p.quoteTime ?? null, source: p.source ?? '', at: Date.now() });
      }
      subs.forEach(f => f());
    }
  } catch { /* the next second retries */ } finally { busy = false; }
}

export function useLivePrice(symbol: string): LivePrice | null {
  const [, bump] = useState(0);
  useEffect(() => {
    const f = () => bump(n => n + 1);
    subs.add(f);
    if (!timer) { tick(); timer = setInterval(tick, 1000); }
    return () => {
      subs.delete(f);
      if (!subs.size && timer) { clearInterval(timer); timer = null; }
    };
  }, []);
  return prices.get(symbol) ?? null;
}
