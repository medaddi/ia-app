import React, { useEffect } from 'react';
import { Radar } from 'lucide-react';
import { useRadar } from '../radarStore';
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
export const AgentRadar: React.FC<{ symbol: string; lang: Language; className?: string; wrap?: boolean; silent?: boolean }> = ({ symbol, lang, className = '', wrap = false, silent = false }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const r = useRadar(symbol) as RadarState | null;  // every pair's radar in one shared request every 5 s
  const drawn = useAnalysisDrawing(symbol);
  useEffect(() => {
    // the radar found a confirmed setup: it goes on the chart (unless that one is already drawn)
    if (r?.status === 'SETUP' && r.draw && (!drawn || drawn.label !== r.draw.label)) setAnalysisDrawing(symbol, r.draw);
  }, [r, symbol]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!r || silent) return null;  // silent: the radar still draws a confirmed setup on the chart, with no text
  const label = r.status === 'SETUP' ? t('setup', 'setup', 'سيتاب') : r.status === 'FORMING' ? t('forming', 'en formation', 'كيتكون') : t('watching', 'veille', 'كيراقب');
  return (
    <div className={`flex min-w-0 ${wrap ? 'items-start' : 'items-center'} gap-1.5 rounded-lg border px-2 py-1 text-[11px] leading-snug ${TONE[r.status]} ${className}`} title={`${r.agent.id} · ${r.headline}`}>
      <Radar className={`w-3.5 h-3.5 shrink-0 ${wrap ? 'mt-px' : ''} ${r.status !== 'WATCHING' ? 'animate-pulse' : ''}`} aria-hidden="true" />
      <span className={`min-w-0 ${wrap ? 'line-clamp-1' : 'truncate'}`}><span className="font-semibold">{label}</span> · {r.headline.replace(/^[A-Z]{2,4}-[A-Z0-9-]+ · /, '')}{r.zoneNow ? ` · ${r.zoneNow}` : ''}</span>
    </div>
  );
};
