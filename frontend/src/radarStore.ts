/**
 * The pair agents' radars, shared by every screen: one request every 5 s for all the pairs shown
 * (backend GET /api/agents/radars), instead of one request per pair card.
 */
import { useEffect, useState } from 'react';
import { apiFetch } from './api';

const EVERY_MS = 5000;
const store = new Map<string, any>();
const subs = new Map<string, Set<() => void>>();
let timer: ReturnType<typeof setInterval> | null = null;
let busy = false;
let soon: ReturnType<typeof setTimeout> | null = null;

async function load() {
  if (document.hidden || busy || subs.size === 0) return;
  busy = true;
  try {
    const symbols = [...subs.keys()];
    const res = await apiFetch(`/api/agents/radars?symbols=${encodeURIComponent(symbols.join(','))}`, { cache: 'no-store' });
    const j = await res.json();
    if (j.success) {
      for (const [sym, r] of Object.entries<any>(j.radars || {})) {
        if (!r?.success) continue;
        store.set(sym, r);
        subs.get(sym)?.forEach(f => f());
      }
    }
  } catch { /* the next tick retries */ } finally { busy = false; }
}

/** A pair that appears asks soon (the cards mounting together share that one request). */
function loadSoon() {
  if (soon) return;
  soon = setTimeout(() => { soon = null; load(); }, 50);
}

export function useRadar(symbol: string): any | null {
  const [, tick] = useState(0);
  useEffect(() => {
    const f = () => tick(n => n + 1);
    if (!subs.has(symbol)) subs.set(symbol, new Set());
    subs.get(symbol)!.add(f);
    if (!store.has(symbol)) loadSoon();
    if (!timer) timer = setInterval(load, EVERY_MS);
    return () => {
      const s = subs.get(symbol);
      s?.delete(f);
      if (s && s.size === 0) subs.delete(symbol);
      if (subs.size === 0 && timer) { clearInterval(timer); timer = null; }
    };
  }, [symbol]);
  return store.get(symbol) ?? null;
}
