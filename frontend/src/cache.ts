/**
 * The app's own memory on this device (localStorage): the last data each screen received, shown at once when the app is
 * opened again, while fresh data loads behind it. So opening the app never starts from an empty screen and the server is
 * not asked for everything again on every visit.
 *
 * - Each entry keeps its save time; `read` ignores an entry older than `maxAgeMs`.
 * - At most MAX_ENTRIES entries per kind (`ld_c:<kind>:…`), the least recently saved ones are dropped first, and a full
 *   storage drops the oldest entries until the new one fits, so the cache never breaks the app.
 * - Every access is wrapped: a private window or a blocked storage simply means no cache.
 * Nothing private is stored beyond what the signed-in user's own screens already show; sign-out clears it.
 */
const PREFIX = 'ld_c:';
const MAX_ENTRIES = 12;

interface Entry<T> { at: number; v: T }

export function readCache<T>(kind: string, key: string, maxAgeMs: number): T | null {
  try {
    const raw = localStorage.getItem(`${PREFIX}${kind}:${key}`);
    if (!raw) return null;
    const e = JSON.parse(raw) as Entry<T>;
    return Date.now() - e.at <= maxAgeMs ? e.v : null;
  } catch { return null; }
}

function entriesOf(kind?: string): { k: string; at: number }[] {
  const out: { k: string; at: number }[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(kind ? `${PREFIX}${kind}:` : PREFIX)) continue;
    try { out.push({ k, at: (JSON.parse(localStorage.getItem(k) || '{}') as Entry<unknown>).at || 0 }); } catch { out.push({ k, at: 0 }); }
  }
  return out.sort((a, b) => a.at - b.at);
}

export function writeCache<T>(kind: string, key: string, v: T): void {
  try {
    const k = `${PREFIX}${kind}:${key}`;
    const body = JSON.stringify({ at: Date.now(), v } as Entry<T>);
    const mine = entriesOf(kind).filter(e => e.k !== k);
    while (mine.length >= MAX_ENTRIES) localStorage.removeItem(mine.shift()!.k);
    for (let tries = 0; tries < 20; tries++) {
      try { localStorage.setItem(k, body); return; } catch {
        const old = entriesOf().filter(e => e.k !== k);  // storage full: drop the oldest cached entry and try again
        if (!old.length) return;
        localStorage.removeItem(old[0].k);
      }
    }
  } catch { /* storage blocked: no cache */ }
}

/** Sign-out: forget every cached screen of this device. */
export function clearCache(): void {
  try { entriesOf().forEach(e => localStorage.removeItem(e.k)); } catch { /* storage blocked */ }
}
