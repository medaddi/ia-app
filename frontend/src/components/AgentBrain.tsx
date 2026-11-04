import React, { useEffect, useState } from 'react';
import { Bot, Building2, CandlestickChart, Check, Minus, ShieldCheck, X } from 'lucide-react';
import { apiJson } from '../api';
import { tr } from './ui';
import type { Language } from '../types';

interface Vote { key: 'plan' | 'smc' | 'skill' | 'market'; name: string; side: 'BUY' | 'SELL' | null; state: string; line: string; agrees: boolean | null }
interface Brain {
  agent: { id: string; name: string; read: string } | null;
  decision: { status: 'SETUP' | 'WAITING'; family: string | null; side: 'BUY' | 'SELL' | null; name: string | null; entry?: number | null;
    entryZone?: [number, number] | null; sl?: number | null; tp?: number | null; rr?: number | null; trigger?: string | null; why: string };
  votes: Vote[]; agree: number; against: number; grade: 'A' | 'B' | 'C' | null; buyPct?: number; sellPct?: number;
}

const ICON = { plan: ShieldCheck, smc: CandlestickChart, skill: Building2, market: Bot };
const GRADE = { A: 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', B: 'bg-gold-500/15 text-gold-200 ring-gold-500/40', C: 'bg-slate-500/15 text-slate-300 ring-slate-500/30' };

/**
 * The pair's one agent (backend analysis/brain.py): its proven plan, the SMC strategies and the big players' positioning
 * (the trader skill) read together, with the decision, each view's vote and a confluence grade.
 */
export const AgentBrain: React.FC<{ symbol: string; lang: Language }> = ({ symbol, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [b, setB] = useState<Brain | null>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let alive = true;
    setB(null);
    const load = async () => {
      if (document.hidden) return;
      try {
        const r = await apiJson<Brain>(`/api/agents/brain?symbol=${encodeURIComponent(symbol)}`);
        if (alive) { setB(r); setErr(''); }
      } catch (e: any) { if (alive) setErr(e.message); }
    };
    load();
    const id = setInterval(load, 15000);  // the agent re-reads the market at each candle close
    return () => { alive = false; clearInterval(id); };
  }, [symbol]);

  const dec = symbol === 'XAU/USD' ? 2 : 5;
  const f = (v?: number | null) => (typeof v === 'number' ? v.toFixed(dec) : '—');
  const d = b?.decision;
  const sideTone = (s?: string | null) => (s === 'BUY' ? 'text-emerald-300' : s === 'SELL' ? 'text-rose-300' : 'text-slate-400');
  return (
    <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="agent-brain-title">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="agent-brain-title" className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="icon-tile icon-tile-gold w-7 h-7" aria-hidden="true"><Bot className="w-4 h-4" /></span>
          {b?.agent?.id ?? t('Pair agent', 'Agent de la paire', 'وكيل الزوج')}
          <span className="text-[10px] font-normal text-slate-500">{t('plan · SMC · big players · market', 'plan · SMC · gros joueurs · marché', 'الخطة · SMC · الكبار · السوق')}</span>
        </h3>
        {b?.grade && <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ring-1 ring-inset ${GRADE[b.grade]}`} title={t('Confluence: how many views agree', 'Confluence : combien de vues sont d’accord', 'التوافق: شحال من قراءة متافقة')}>
          {t('Grade', 'Note', 'الدرجة')} {b.grade} · {b.agree}/4{b.against ? ` · ${b.against} ${t('against', 'contre', 'ضد')}` : ''}</span>}
      </header>
      {err && !b && <p className="mt-2 text-xs text-rose-300">{err}</p>}
      {!b && !err && <div className="mt-3 h-16 rounded-lg bg-white/[0.03] animate-pulse" aria-busy="true" />}
      {d && (
        <>
          <div className={`mt-3 rounded-xl border px-3 py-2.5 ${d.status === 'SETUP' ? 'border-emerald-500/40 bg-emerald-500/[0.06]' : 'border-line bg-white/[0.02]'}`}>
            <p className="text-sm font-semibold text-white">
              {d.status === 'SETUP' ? t('Setup now', 'Setup maintenant', 'سيتاب دابا') : t('Waiting', 'En attente', 'كيتسنا')}
              {d.side && <span className={`ms-2 ${sideTone(d.side)}`}>{d.side}</span>}
              {d.name && <span className="ms-2 text-xs font-normal text-slate-400">{d.family === 'smc' ? 'SMC · ' : ''}{d.name}</span>}
            </p>
            {(d.entry != null) && (
              <p className="mt-1 text-[11px] font-mono text-slate-300">
                {t('entry', 'entrée', 'الدخول')} {d.entryZone ? `${f(d.entryZone[0])} – ${f(d.entryZone[1])}` : f(d.entry)} · <span className="text-rose-300">SL {f(d.sl)}</span> · <span className="text-emerald-300">TP {f(d.tp)}</span>{d.rr ? ` · 1:${d.rr}` : ''}
              </p>
            )}
            <p className="mt-1 text-[11px] text-slate-400 leading-snug">{d.trigger ? `${t('If', 'Si', 'إلا')} ${d.trigger} · ` : ''}{d.why}</p>
          </div>
          <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {b!.votes.map(v => {
              const Icon = ICON[v.key];
              return (
                <li key={v.key} className="rounded-lg border border-line bg-white/[0.02] px-2.5 py-2 text-[11px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 font-semibold text-slate-200"><Icon className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />
                      {v.key === 'plan' ? t('Proven plan', 'Plan prouvé', 'الخطة المجربة') : v.key === 'skill' ? t('Big players (COT)', 'Gros joueurs (COT)', 'الكبار (COT)') : v.key === 'market' ? t('Market', 'Marché', 'السوق') : 'SMC'}</span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`font-bold ${sideTone(v.side)}`}>{v.side ?? '—'}</span>
                      {v.agrees === true && <Check className="w-3.5 h-3.5 text-emerald-400" aria-label={t('agrees', 'd’accord', 'متافق')} />}
                      {v.agrees === false && <X className="w-3.5 h-3.5 text-rose-400" aria-label={t('against', 'contre', 'ضد')} />}
                      {v.agrees === null && <Minus className="w-3.5 h-3.5 text-slate-600" aria-label={t('no view', 'sans avis', 'بلا رأي')} />}
                    </span>
                  </div>
                  <p className="mt-0.5 text-slate-500 leading-snug line-clamp-2" title={v.line}>{v.line}</p>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-[10px] text-slate-500">{t('Grade A: 3 or more views agree and none is against · B: 2 agree · C: alone or contradicted. Confluence, not a guarantee.',
            'Note A : 3 vues ou plus d’accord et aucune contre · B : 2 d’accord · C : seule ou contredite. De la confluence, pas une garantie.',
            'درجة A: 3 قراءات ولا كثر متافقين وحتى وحدة ضد · B: 2 متافقين · C: بوحدها ولا عندها اعتراض. توافق، ماشي ضمانة.')}</p>
        </>
      )}
    </section>
  );
};
