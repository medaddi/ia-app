/**
 * Anti copy-trading protection for Telegram signals.
 *
 * 1. protect_content: Telegram blocks forwarding, saving and copying of signal messages.
 * 2. Personal micro-offset: every subscriber gets the SAME trade shifted by a tiny, deterministic
 *    amount (gold: 1–9 cents, EURUSD: 0.1–0.9 pip). Entry, SL and all TPs move together, so the
 *    stop distance, R:R and lot size are identical, but no two accounts send identical orders
 *    (brokers / prop firms flag identical copy trades).
 * 3. Personal reference code: printed on the message and logged with the offset, so a leaked
 *    screenshot or copied levels can be traced back to the subscriber.
 *
 * Toggle with TELEGRAM_PROTECT_CONTENT=false / TELEGRAM_PERSONAL_OFFSETS=false.
 */

import fs from "fs";
import path from "path";

export const COPY_PROTECTION = {
  protectContent: process.env.TELEGRAM_PROTECT_CONTENT !== "false",
  personalOffsets: process.env.TELEGRAM_PERSONAL_OFFSETS !== "false",
  maxOffsetTicks: 9,
  tick: { gold: 0.01, euro: 0.00001 },
};

/** FNV-1a 32-bit hash: stable across restarts and machines. */
export function hash32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function referenceCode(chatId: string, signalId: string): string {
  return hash32(`ref|${chatId}|${signalId}`).toString(36).toUpperCase().padStart(6, "0").slice(-6);
}

/** Signed offset in price units for this subscriber and this signal (never zero). */
export function personalOffset(symbol: string, chatId: string, signalId: string): number {
  const gold = !symbol.includes("EUR");
  const h = hash32(`off|${chatId}|${signalId}`);
  const ticks = 1 + (h % COPY_PROTECTION.maxOffsetTicks);
  const sign = (h >>> 16) & 1 ? 1 : -1;
  return sign * ticks * (gold ? COPY_PROTECTION.tick.gold : COPY_PROTECTION.tick.euro);
}

/** Returns a copy of the signal with every level shifted by the same personal offset. */
export function personalizeSignal<T extends Record<string, any>>(signal: T, chatId: string): { signal: T; offset: number; ref: string } {
  const ref = referenceCode(chatId, String(signal.id));
  if (!COPY_PROTECTION.personalOffsets) return { signal, offset: 0, ref };
  const gold = !String(signal.symbol).includes("EUR");
  const d = gold ? 2 : 5;
  const offset = personalOffset(String(signal.symbol), chatId, String(signal.id));
  const shift = (v: unknown) => (typeof v === "number" && v > 0 ? Number((v + offset).toFixed(d)) : v);
  return {
    signal: { ...signal, entryPrice: shift(signal.entryPrice), stopLoss: shift(signal.stopLoss), target1: shift(signal.target1), target2: shift(signal.target2), target3: shift(signal.target3) },
    offset,
    ref,
  };
}

// ---- Leak tracing log ----
const LOG_FILE = path.resolve(process.cwd(), "data/signal_watermarks.json");
interface WatermarkRecord { ref: string; chatId: string; signalId: string; symbol: string; offset: number; sentAt: string }

function readLog(): WatermarkRecord[] {
  try { return JSON.parse(fs.readFileSync(LOG_FILE, "utf8")); } catch { return []; }
}

export function recordWatermarks(records: WatermarkRecord[]) {
  if (!records.length) return;
  try {
    const all = [...readLog(), ...records].slice(-5000);
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    fs.writeFileSync(LOG_FILE, JSON.stringify(all, null, 1));
  } catch (err: any) {
    console.warn("[CopyProtection] Could not write watermark log:", err?.message || err);
  }
}

/** Finds who received a signal, by reference code or by a leaked entry price. */
export function traceLeak(query: { ref?: string; signalId?: string; entry?: number; originalEntry?: number }): WatermarkRecord[] {
  const log = readLog();
  if (query.ref) return log.filter(r => r.ref === query.ref.toUpperCase());
  if (query.signalId && typeof query.entry === "number" && typeof query.originalEntry === "number") {
    const off = query.entry - query.originalEntry;
    return log.filter(r => r.signalId === query.signalId && Math.abs(r.offset - off) < 1e-9 + Math.abs(off) * 1e-6);
  }
  return [];
}
