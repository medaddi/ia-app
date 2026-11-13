// The intro (index.html #splash) covers the app while it gathers its data: it fades out once the first real screen is
// ready, never before MIN_MS (a short logo flash), never after MAX_MS (a slow server must not trap the user: the screen then
// shows and fills in as its data arrives).
const MIN_MS = 900;
const MAX_MS = 4000;
let done = false;
let dataReady = false;
let waiting: (() => void) | null = null;

// The dashboard / chart call this once their first data is on screen
export function markDataReady() {
  dataReady = true;
  waiting?.();
}

function fade() {
  const el = document.getElementById('splash');
  if (!el) return;
  el.classList.add('fade-out');
  setTimeout(() => el.remove(), 900);
}

/** `withData`: wait for markDataReady() first (a logged-in account opening its dashboard). */
export function hideSplash(withData = false) {
  if (done) return;
  done = true;
  const go = () => setTimeout(fade, Math.max(0, MIN_MS - performance.now()));
  if (!withData || dataReady) { go(); return; }
  const cap = setTimeout(() => { waiting = null; go(); }, Math.max(0, MAX_MS - performance.now()));
  waiting = () => { clearTimeout(cap); waiting = null; go(); };
}
