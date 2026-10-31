/**
 * Trade notifications.
 * - Web Push: the browser subscribes with the server's key; the server pushes every new trade, so it reaches the phone
 *   even when the app is closed or the tab is frozen (the only way it works on mobile).
 * - In-app: while the app is open it also notifies the trades it sees in /api/signals, with the same tag
 *   ("ld-<id>"), so a trade never shows twice. Seen ids are kept per browser.
 * iPhone / iPad: web notifications only exist once the app is added to the home screen (iOS 16.4+).
 */
import { apiFetch, apiJson } from './api';
import type { AISignal, Language } from './types';
import { strategyKind } from './instruments';

const ENABLED_KEY = 'ld_notify_enabled';
const SEEN_KEY = 'ld_notify_seen_v1';

export const notifySupported = () => typeof window !== 'undefined' && 'Notification' in window;
export const isIos = () => typeof navigator !== 'undefined' && (/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
export const isStandalone = () => typeof window !== 'undefined' && (window.matchMedia?.('(display-mode: standalone)').matches || (navigator as any).standalone === true);
/** iPhone in Safari: notifications need the app on the home screen first. */
export const needsInstall = () => isIos() && !isStandalone();
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

function keyBytes(b64url: string): Uint8Array {
  const b64 = (b64url + '='.repeat((4 - (b64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0));
}

/** Subscribes this browser to the server's pushes (or refreshes the subscription). Returns true when the server has it. */
export async function subscribePush(): Promise<boolean> {
  const reg = await registerServiceWorker();
  if (!reg || !('pushManager' in reg)) return false;
  try {
    const { publicKey } = await apiJson<{ publicKey: string }>('/api/push/key');
    let sub = await reg.pushManager.getSubscription();
    if (sub && sub.options?.applicationServerKey) {
      const have = new Uint8Array(sub.options.applicationServerKey as ArrayBuffer), want = keyBytes(publicKey);
      if (have.length !== want.length || have.some((b, i) => b !== want[i])) { await sub.unsubscribe(); sub = null; }  // server key changed
    }
    sub = sub ?? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) as BufferSource });
    const res = await apiFetch('/api/push/subscribe', { method: 'POST', body: JSON.stringify(sub.toJSON()) });
    return res.ok;
  } catch {
    return false;
  }
}

/** Asks the browser (must run from a click), then subscribes to the server's pushes. Returns true when notifications are on. */
export async function enableNotifications(): Promise<boolean> {
  if (!notifySupported()) return false;
  const p = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission;
  setEnabled(p === 'granted');
  if (p === 'granted') await subscribePush();
  return p === 'granted';
}

/** A test push from the server to this account's devices (the same path as a real trade). */
export async function testPush(): Promise<boolean> {
  try { return (await apiJson<{ success: boolean }>('/api/push/test', { method: 'POST' })).success; } catch { return false; }
}

export async function disableNotifications() {
  setEnabled(false);
  const reg = await registerServiceWorker();
  const sub = await reg?.pushManager?.getSubscription().catch(() => null);
  if (sub) {
    apiFetch('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
    await sub.unsubscribe().catch(() => {});
  }
}

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
  const options: NotificationOptions = { body, tag, icon: '/brand/icon-192.png', badge: '/brand/favicon-64.png', data: { symbol }, requireInteraction: true } as NotificationOptions;
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
    const tp = `TP ${s.target3 ?? s.target2}${kind === 'rsi2' ? ' · or EMA5' : ''}`;  // every strategy: one target between 1.5R and 2R
    const body = lang === 'fr' ? `Entrée ${s.entryPrice} · SL ${s.stopLoss} · ${tp}` : lang === 'ar' ? `الدخول ${s.entryPrice} · SL ${s.stopLoss} · ${tp}` : `Entry ${s.entryPrice} · SL ${s.stopLoss} · ${tp}`;
    show(`${word(lang, s.signalType)} ${s.symbol} · ${s.confidence}%`, body, `ld-${s.id}`, s.symbol).catch(() => {});
  }
}
