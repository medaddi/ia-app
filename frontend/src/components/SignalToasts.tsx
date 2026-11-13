import React, { useEffect, useRef, useState } from 'react';
import { Target, X } from 'lucide-react';
import { apiJson } from '../api';
import { tr } from './ui';
import type { Language } from '../types';
import { signalHead, signalLevels, type TeamSetup } from '../smcTeam';

/**
 * The in-app live feed: every 20 s it reads /api/smc/signals; a Set & Forget signal it has not shown yet appears as a
 * toast with a short sound. Radar reads are never announced. What was already shown is remembered per browser, so a
 * reload never replays old alerts. A click opens the pair's chart.
 */
const POLL_MS = 20000;
const SEEN_KEY = 'ld_seen_alerts';
const KEEP_MS = 30000;
interface Toast { id: string; symbol: string; title: string; body: string; lot?: string }

const loadSeen = (): Set<string> => { try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]')); } catch { return new Set(); } };
const saveSeen = (s: Set<string>) => { try { localStorage.setItem(SEEN_KEY, JSON.stringify([...s].slice(-200))); } catch { /* storage blocked */ } };

function beep() {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.type = 'sine'; osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start(); osc.stop(ctx.currentTime + 0.5);
    osc.onended = () => ctx.close();
  } catch { /* no sound before a first click, or no audio: the toast is enough */ }
}

export const SignalToasts: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (document.hidden) return;
      let j: { signals?: TeamSetup[] };
      try { j = await apiJson('/api/smc/signals'); } catch { return; }
      if (!alive) return;
      const signals = j.signals ?? [];
      const first = seen.current === null;
      const known = seen.current ?? loadSeen();
      const fresh: Toast[] = [];
      const nowSec = Date.now() / 1000;
      for (const s of signals) {
        if (known.has(s.id)) continue;
        known.add(s.id);
        // on the first read only what is very recent is announced (a reload never replays the history)
        if (first && nowSec - s.time > 1800) continue;
        fresh.push({ id: s.id, symbol: s.symbol ?? '', title: `🎯 ${signalHead(s)}`, body: signalLevels(s) });
      }
      seen.current = known;
      saveSeen(known);
      if (fresh.length) {
        // my own lot under each new signal (from MY risk; never anyone else's)
        await Promise.all(fresh.map(async f => {
          try {
            const z = await apiJson<{ status: string; lots?: number; riskUsd?: number }>(`/api/me/sizing/${encodeURIComponent(f.id)}`);
            if (z.status === 'ok') f.lot = `${t('Your lot', 'Votre lot', 'اللوت ديالك')} ${z.lots} · ${t('risk', 'risque', 'ريسك')} $${z.riskUsd}`;
          } catch { /* no lot line */ }
        }));
        if (!alive) return;
        setToasts(x => [...fresh, ...x].slice(0, 4));
        beep();
        fresh.forEach(f => setTimeout(() => setToasts(x => x.filter(y => y.id !== f.id)), KEEP_MS));
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!toasts.length) return null;
  return (
    <div className="fixed z-[70] top-3 inset-x-3 sm:inset-x-auto sm:end-4 sm:w-[380px] space-y-2" role="status" aria-live="polite">
      {toasts.map(x => (
        <div key={x.id} className="flex items-start gap-2 rounded-xl border border-emerald-500/50 px-3 py-2.5 glass shadow-lg">
          <Target className="w-4 h-4 mt-0.5 shrink-0 text-emerald-300" aria-hidden="true" />
          <button type="button" className="min-w-0 flex-1 text-start cursor-pointer"
            onClick={() => { window.dispatchEvent(new CustomEvent('ld-open-symbol', { detail: x.symbol })); setToasts(v => v.filter(y => y.id !== x.id)); }}>
            <p className="text-xs font-semibold text-white truncate">{x.title}</p>
            <p className="text-[11px] font-mono text-slate-300 leading-snug">{x.body}</p>
            {x.lot && <p className="text-[11px] font-mono text-gold-200">{x.lot}</p>}
          </button>
          <button type="button" onClick={() => setToasts(v => v.filter(y => y.id !== x.id))} aria-label={t('Dismiss', 'Fermer', 'سد')}
            className="shrink-0 w-6 h-6 flex items-center justify-center rounded-md text-slate-400 hover:text-white hover:bg-white/10 cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
};
