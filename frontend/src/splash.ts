// The intro (index.html #splash) is the logo video: it always plays in full at every opening of the app (the owner's
// request of 2026-11-22), while the app gathers its data underneath. It fades out once BOTH the video has ended (the
// 'ld-intro-end' event of index.html's player, which also covers a phone refusing to play it) AND the first real screen
// is ready, never waiting for data more than MAX_MS (a slow server must not trap the user: the screen then fills in).
const MAX_MS = 4000;
let done = false;
let dataReady = false;
let appReady = false;
let introOver = !!(window as any).__ldIntroDone || !document.getElementById('intro');
let waiting: (() => void) | null = null;

function fade() {
  const el = document.getElementById('splash');
  if (!el) return;
  el.classList.add('fade-out');
  setTimeout(() => el.remove(), 900);
}

function maybeFade() {
  if (appReady && introOver) fade();
}

window.addEventListener('ld-intro-end', () => { introOver = true; maybeFade(); }, { once: true });

// The dashboard / chart call this once their first data is on screen
export function markDataReady() {
  dataReady = true;
  waiting?.();
}

/** `withData`: wait for markDataReady() first (a logged-in account opening its dashboard). */
export function hideSplash(withData = false) {
  if (done) return;
  done = true;
  const go = () => { appReady = true; maybeFade(); };
  if (!withData || dataReady) { go(); return; }
  const cap = setTimeout(() => { waiting = null; go(); }, Math.max(0, MAX_MS - performance.now()));
  waiting = () => { clearTimeout(cap); waiting = null; go(); };
}
