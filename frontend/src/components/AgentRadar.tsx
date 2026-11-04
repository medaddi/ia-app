import React, { useEffect, useState } from 'react';
import { Radar } from 'lucide-react';
import { apiFetch } from '../api';
import { setAnalysisDrawing, useAnalysisDrawing, type AnalysisDrawing } from '../analysisDrawing';
import { tr } from './ui';
import type { Language } from '../types';

interface RadarState { success: boolean; status: 'SETUP' | 'FORMING' | 'WATCHING'; headline: string; agent: { id: string }; draw: AnalysisDrawing | null; zoneNow?: string | null }

const TONE = {
  SETUP: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  FORMING: 'border-amber-500/40 bg-amber-500/10 text-amber-100',
  WATCHING: 'border-line bg-white/[0.02] text-slate-400',
};

/**
 * The pair agent's radar (backend /api/agents/radar), asked every second: what it confirms now, or the
 * setup that is closest. A confirmed setup is drawn on the pair's chart as soon as the radar sees it.
 */
export const AgentRadar: React.FC<{ symbol: string; lang: Language; className?: string; wrap?: boolean }> = ({ symbol, lang, className = '', wrap = false }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [r, setR] = useState<RadarState | null>(null);
  const drawn = useAnalysisDrawing(symbol);
  useEffect(() => {
    let alive = true;
    let busy = false;
    const load = async () => {
      if (document.hidden || busy) return;
      busy = true;
      try {
        const res = await apiFetch(`/api/agents/radar?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
        const j = await res.json();
        if (alive && j.success) setR(j);
      } catch { /* the next tick retries */ } finally { busy = false; }
    };
    load();
    const id = setInterval(load, 1000);  // every second: the agent re-reads the market at each candle close, the price every call
    return () => { alive = false; clearInterval(id); };
  }, [symbol]);
  useEffect(() => {
    // the radar found a confirmed setup: it goes on the chart (unless that one is already drawn)
    if (r?.status === 'SETUP' && r.draw && (!drawn || drawn.label !== r.draw.label)) setAnalysisDrawing(symbol, r.draw);
  }, [r, symbol]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!r) return null;
  const label = r.status === 'SETUP' ? t('setup', 'setup', 'سيتاب') : r.status === 'FORMING' ? t('forming', 'en formation', 'كيتكون') : t('watching', 'veille', 'كيراقب');
  return (
    <div className={`flex min-w-0 ${wrap ? 'items-start' : 'items-center'} gap-1.5 rounded-lg border px-2 py-1 text-[11px] leading-snug ${TONE[r.status]} ${className}`} title={`${r.agent.id} · ${r.headline}`}>
      <Radar className={`w-3.5 h-3.5 shrink-0 ${wrap ? 'mt-px' : ''} ${r.status !== 'WATCHING' ? 'animate-pulse' : ''}`} aria-hidden="true" />
      <span className={`min-w-0 ${wrap ? 'line-clamp-2' : 'truncate'}`}><span className="font-semibold">{label}</span> · {r.headline.replace(/^[A-Z]{2,4}-[A-Z0-9-]+ · /, '')}{r.zoneNow ? ` · ${r.zoneNow}` : ''}</span>
    </div>
  );
};
