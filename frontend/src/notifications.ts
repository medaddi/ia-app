/**
 * Notifications (Web Push): the browser subscribes with the server's key, so a push reaches the phone even when the app
 * is closed or the tab is frozen. Nothing is pushed automatically for now: the app's analysis is being rebuilt.
 * iPhone / iPad: web notifications only exist once the app is added to the home screen (iOS 16.4+).
 */
import { apiFetch, apiJson } from './api';

const ENABLED_KEY = 'ld_notify_enabled';

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

/** A test push from the server to this account's devices. */
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
