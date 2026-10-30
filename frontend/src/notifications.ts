/**
 * Browser notifications for new trades. The app already polls /api/signals; every signal id that becomes actionable
 * for the first time shows one notification (through the service worker, so it also works on Android and when the tab
 * is in the background). The seen ids are kept per browser so a reload never notifies the same trade twice.
 */
import type { AISignal, Language } from './types';
import { strategyKind } from './instruments';

const ENABLED_KEY = 'ld_notify_enabled';
const SEEN_KEY = 'ld_notify_seen_v1';

export const notifySupported = () => typeof window !== 'undefined' && 'Notification' in window;
export const notifyPermission = (): NotificationPermission | 'unsupported' => (notifySupported() ? Notification.permission : 'unsupported');

export function notifyEnabled(): boolean {
  try { return notifyPermission() === 'granted' && localStorage.getItem(ENABLED_KEY) === '1'; } catch { return false; }
}

function setEnabled(on: boolean) {
  try { localStorage.setItem(ENABLED_KEY, on ? '1' : '0'); } catch { /* storage unavailable */ }
  window.dispatchEvent(new Event('ld-notify-change'));
}

let swReg: Promise<ServiceWorkerRegistration | null> | null = null;
export function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!swReg) {
    swReg = 'serviceWorker' in navigator
      ? navigator.serviceWorker.register('/sw.js').then(() => navigator.serviceWorker.ready).catch(() => null)
      : Promise.resolve(null);
  }
  return swReg;
}

/** Asks the browser (must run from a click). Returns true when notifications are on. */
export async function enableNotifications(): Promise<boolean> {
  if (!notifySupported()) return false;
  const p = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission;
  setEnabled(p === 'granted');
  if (p === 'granted') await registerServiceWorker();
  return p === 'granted';
}

export function disableNotifications() { setEnabled(false); }

// A clicked notification asks the chart page to bring its lot calculator into view for that pair.
// Kept until the calculator of that pair is on screen (the chart page may still be loading).
let lotFocus: string | null = null;
export function requestLotFocus(symbol: string) {
  lotFocus = symbol;
  window.dispatchEvent(new Event('ld-lot-focus'));
}
export function takeLotFocus(symbol: string): boolean {
  if (lotFocus !== symbol) return false;
  lotFocus = null;
  return true;
}

async function show(title: string, body: string, tag: string, symbol: string) {
  const options: NotificationOptions = { body, tag, icon: '/brand/emblem-192.webp', badge: '/brand/favicon-64.png', data: { symbol }, requireInteraction: true } as NotificationOptions;
  const reg = await registerServiceWorker();
  if (reg) return reg.showNotification(title, options);
  const n = new Notification(title, options);
  n.onclick = () => { window.focus(); window.dispatchEvent(new CustomEvent('ld-open-symbol', { detail: symbol })); n.close(); };
}

const word = (lang: Language, side: string) => (side === 'BUY' ? { en: 'BUY', fr: 'ACHAT', ar: 'شراء' } : { en: 'SELL', fr: 'VENTE', ar: 'بيع' })[lang];

/** Call with every fresh signals list: notifies the trades that were not seen before (the first list is the baseline). */
export function notifyNewSignals(signals: AISignal[], lang: Language) {
  let seen: string[] | null = null;
  try { seen = JSON.parse(localStorage.getItem(SEEN_KEY) || 'null'); } catch { seen = null; }
  const live = signals.filter(s => s.isActionableNow && s.signalType !== 'WAIT');
  const known = new Set(seen ?? []);
  const fresh = seen === null ? [] : live.filter(s => !known.has(s.id));
  live.forEach(s => known.add(s.id));
  try { localStorage.setItem(SEEN_KEY, JSON.stringify([...known].slice(-200))); } catch { /* storage unavailable */ }
  if (!notifyEnabled()) return;
  for (const s of fresh) {
    const kind = strategyKind(s.symbol);
    const tp = kind === 'gold' ? `TP1 ${s.target1} · TP2 ${s.target2}` : kind === 'rsi2' ? `exit EMA5 · cap ${s.target3 ?? s.target2}` : `TP ${s.target3 ?? s.target2}`;
    const body = lang === 'fr' ? `Entrée ${s.entryPrice} · SL ${s.stopLoss} · ${tp}` : lang === 'ar' ? `الدخول ${s.entryPrice} · SL ${s.stopLoss} · ${tp}` : `Entry ${s.entryPrice} · SL ${s.stopLoss} · ${tp}`;
    show(`${word(lang, s.signalType)} ${s.symbol} · ${s.confidence}%`, body, `ld-${s.id}`, s.symbol).catch(() => {});
  }
}
