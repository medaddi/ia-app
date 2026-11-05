import React, { useState } from 'react';
import { Building2, ChevronDown, ClipboardList, Droplets, Layers, Shield, Target, TrendingUp, Users } from 'lucide-react';
import { tr } from '../components/ui';
import type { Language } from '../types';
import type { Dossier, Team, TeamMember } from './usePairDossier';

const ICON = { trade: ClipboardList, structure: TrendingUp, liquidity: Droplets, zones: Layers, strategy: Target, cot: Building2 };
const GRADE = { A: 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', B: 'bg-gold-500/15 text-gold-200 ring-gold-500/40', C: 'bg-slate-500/15 text-slate-300 ring-slate-500/30' };
const BOX = { IN_TRADE: 'border-sky-500/40 bg-sky-500/[0.06]', PENDING: 'border-sky-500/30 bg-sky-500/[0.04]', SETUP: 'border-emerald-500/40 bg-emerald-500/[0.06]',
  CONFLICT: 'border-amber-500/30 bg-amber-500/[0.05]', WAITING: 'border-line bg-white/[0.02]' };
const sideTone = (s?: string | null) => (s === 'BUY' ? 'text-emerald-300' : s === 'SELL' ? 'text-rose-300' : 'text-slate-400');

/**
 * A pair's dossier under its chart: its team (each member's role and view, the probabilities, the decision) and its
 * trades. Mounted once per pair (key = symbol): a switch starts a fresh dossier, never another pair's.
 */
export const PairDossier: React.FC<{ symbol: string; dossier: Dossier | null; decimals: number; lang: Language; details?: React.ReactNode }> =
  ({ symbol, dossier, decimals, lang, details }) => {
    const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
    const [tab, setTab] = useState<'team' | 'trades'>('team');
    const [open, setOpen] = useState(false);
    const team = dossier?.team;
    const trades = dossier?.trades;
    const nTrades = trades ? trades.running.length : 0;
    return (
      <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="pair-dossier-title">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="pair-dossier-title" className="flex items-center gap-2 text-sm font-semibold text-white">
            <span className="icon-tile icon-tile-gold w-7 h-7" aria-hidden="true"><Users className="w-4 h-4" /></span>
            {team?.desk ? tr(lang, team.desk.team, team.desk.teamFr, team.desk.teamAr) : t('Pair team', 'Équipe de la paire', 'فريق الزوج')}
            <span className="text-[11px] font-normal text-slate-500">{symbol}</span>
          </h3>
          <div role="tablist" className="inline-flex rounded-lg border border-line p-0.5 text-[11px]">
            {(['team', 'trades'] as const).map(k => (
              <button key={k} role="tab" type="button" aria-selected={tab === k} onClick={() => setTab(k)}
                className={`px-2.5 h-7 rounded-md cursor-pointer ${tab === k ? 'bg-gold-500/15 text-gold-200' : 'text-slate-400 hover:text-slate-200'}`}>
                {k === 'team' ? t('Team & analysis', 'Équipe & analyse', 'الفريق والتحليل') : `${t('Trades', 'Trades', 'الصفقات')}${nTrades ? ` · ${nTrades}` : ''}`}
              </button>
            ))}
          </div>
        </header>
        {!dossier && <div className="mt-3 h-24 rounded-lg bg-white/[0.03] animate-pulse" aria-busy="true" />}
        {team?.desk && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
            <span className={`px-1.5 py-0.5 rounded-md ring-1 ring-inset ${team.session.open ? 'bg-emerald-500/10 text-emerald-200 ring-emerald-500/30' : 'bg-white/[0.03] text-slate-400 ring-line'}`}
              title={(team.session.windows ?? []).map(w => `${w.label} ${w.from}:00–${w.to}:00 UTC`).join(' · ')}>
              {team.session.open ? `${t('Session open', 'Session ouverte', 'السيشن محلول')} · ${team.session.label}` : t('Outside its hours', 'Hors de ses heures', 'برا الوقت ديالو')}
            </span>
            {team.desk.tags.map(x => <span key={x} className="px-1.5 py-0.5 rounded-md bg-white/[0.03] text-slate-400 ring-1 ring-inset ring-line">{x}</span>)}
          </div>
        )}
        {team && tab === 'team' && <TeamView team={team} decimals={decimals} lang={lang} />}
        {trades && tab === 'trades' && <TradesView trades={trades} decimals={decimals} lang={lang} />}
        {dossier && details && tab === 'team' && (
          <>
            <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open} className="mt-2 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer">
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />{open ? t('Hide details', 'Masquer les détails', 'خبي التفاصيل') : t('Details', 'Détails', 'التفاصيل')}
            </button>
            {open && <div className="mt-1">{details}</div>}
          </>
        )}
      </section>
    );
  };

const TeamView: React.FC<{ team: Team; decimals: number; lang: Language }> = ({ team, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const f = (v?: number | null) => (typeof v === 'number' ? v.toFixed(decimals) : '—');
  const d = team.decision;
  const p = team.probabilities;
  const status = {
    IN_TRADE: t('In trade', 'En position', 'ف صفقة'), PENDING: t('Order pending', 'Ordre en attente', 'أوردر كيتسنا'), SETUP: t('Setup now', 'Setup maintenant', 'سيتاب دابا'),
    CONFLICT: t('No trade', 'Pas de trade', 'حتى صفقة'), WAITING: t('Waiting', 'En attente', 'كيتسنا'),
  }[d.status];
  const role = (k: TeamMember['key']) => ({
    trade: t('Trade manager', 'Gestion du trade', 'مسير الصفقة'), structure: t('Structure', 'Structure', 'الهيكلة'), liquidity: t('Liquidity', 'Liquidité', 'السيولة'),
    zones: t('Zones', 'Zones', 'المناطق'), strategy: t('SMC strategy', 'Stratégie SMC', 'استراتيجية SMC'), cot: 'COT',
  })[k];
  return (
    <>
      <div className={`mt-3 rounded-xl border px-3 py-2.5 ${BOX[d.status]}`} title={d.why}>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-white">{status}{d.side && <span className={`ms-2 ${sideTone(d.side)}`}>{d.side}</span>}</p>
          {team.grade && <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ring-1 ring-inset ${GRADE[team.grade]}`}
            title={t('A: the side is 60 %+ probable · B: 45 %+ · C: below', 'A : côté probable à 60 %+ · B : 45 %+ · C : moins', 'A: الجهة محتملة 60% ولا كثر · B: 45% ولا كثر · C: أقل')}>
            {t('Grade', 'Note', 'الدرجة')} {team.grade}</span>}
        </div>
        {d.entry != null && d.status !== 'CONFLICT' && (
          <p className="mt-1 text-[11px] font-mono text-slate-300">
            {d.entryZone ? `${f(d.entryZone[0])} – ${f(d.entryZone[1])}` : f(d.entry)} · <span className="text-rose-300">SL {f(d.sl)}</span> · <span className="text-emerald-300">TP {f(d.tp)}</span>{d.rr ? ` · 1:${d.rr}` : ''}
          </p>
        )}
        {d.status === 'WAITING' && d.trigger && <p className="mt-1 text-[11px] text-slate-400 truncate">{t('If', 'Si', 'إلا')} {d.trigger}</p>}
      </div>
      {/* the probabilities the team gives */}
      <div className="mt-2" aria-label={t('Probabilities', 'Probabilités', 'الاحتمالات')}>
        <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.04]">
          <div className="bg-emerald-500/70" style={{ width: `${p.buy}%` }} />
          <div className="bg-slate-500/40" style={{ width: `${p.wait}%` }} />
          <div className="bg-rose-500/70" style={{ width: `${p.sell}%` }} />
        </div>
        <div className="mt-1 flex justify-between text-[11px] font-mono">
          <span className="text-emerald-300">BUY {p.buy}%</span><span className="text-slate-400">{t('wait', 'attente', 'انتظار')} {p.wait}%</span><span className="text-rose-300">SELL {p.sell}%</span>
        </div>
      </div>
      {/* each member: its role, its side, how sure it is (the detail on hover) */}
      <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={t('The team', 'L’équipe', 'الفريق')}>
        {team.members.map(m => {
          const Icon = ICON[m.key];
          const ring = m.agrees === true ? 'border-emerald-500/40' : m.agrees === false ? 'border-rose-500/40' : 'border-line';
          return (
            <li key={m.key} title={m.line} className={`inline-flex items-center gap-1.5 rounded-lg border ${ring} bg-white/[0.02] px-2 py-1 text-[11px]`}>
              <Icon className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />
              <span className="text-slate-300">{role(m.key)}</span>
              <span className={`font-bold ${sideTone(m.side)}`}>{m.side ?? '—'}</span>
              {m.side && <span className="text-slate-500 font-mono">{Math.round(m.conf * 100)}%</span>}
            </li>
          );
        })}
        <li title={team.risk.line} className={`inline-flex items-center gap-1.5 rounded-lg border ${team.risk.approves ? 'border-emerald-500/40' : 'border-line'} bg-white/[0.02] px-2 py-1 text-[11px]`}>
          <Shield className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />
          <span className="text-slate-300">{t('Risk', 'Risque', 'المخاطرة')}</span>
          <span className={team.risk.approves ? 'font-bold text-emerald-300' : 'text-slate-500'}>{team.risk.approves ? t('OK', 'OK', 'واخا') : '—'}</span>
        </li>
      </ul>
    </>
  );
};

const TradesView: React.FC<{ trades: Dossier['trades']; decimals: number; lang: Language }> = ({ trades, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const f = (v?: number | null) => (typeof v === 'number' ? v.toFixed(decimals) : '—');
  const when = (s?: number) => (s ? new Date(s * 1000).toISOString().slice(5, 16).replace('T', ' ') : '');
  const row = (x: Dossier['trades']['running'][number], live: boolean) => (
    <li key={x.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border border-line bg-white/[0.02] px-2.5 py-1.5 text-[11px] font-mono">
      <span className={`font-bold ${sideTone(x.direction)}`}>{x.direction}</span>
      <span className="text-slate-200">{f(x.entry)}</span>
      <span className="text-rose-300">SL {f(x.sl)}</span>
      <span className="text-emerald-300">TP {f(x.tp2 ?? x.tp)}</span>
      <span className="text-slate-500">{when(x.signalTime ?? x.time)}</span>
      <span className={`ms-auto ${live ? 'text-sky-200' : x.outcome === 'WIN' ? 'text-emerald-300' : x.outcome === 'LOSS' ? 'text-rose-300' : 'text-slate-400'}`}>
        {live ? x.state.replace(/_/g, ' ') : x.outcome ?? x.state}{x.r != null ? ` ${x.r >= 0 ? '+' : ''}${x.r}R` : ''}</span>
    </li>
  );
  return (
    <div className="mt-3 space-y-3">
      <div>
        <p className="text-[11px] text-slate-400">{t('Running now', 'En cours', 'خدامة دابا')}</p>
        {trades.running.length ? <ul className="mt-1 space-y-1">{trades.running.map(x => row(x, true))}</ul>
          : <p className="mt-1 text-[11px] text-slate-500">{t('No trade running', 'Aucun trade en cours', 'حتى صفقة خدامة')}</p>}
      </div>
      <div>
        <p className="text-[11px] text-slate-400">{t('Last signals sent', 'Derniers signaux envoyés', 'آخر الإشارات المرسلة')}</p>
        {trades.history.length ? <ul className="mt-1 space-y-1">{trades.history.map(x => row(x, false))}</ul>
          : <p className="mt-1 text-[11px] text-slate-500">{t('None yet', 'Aucun pour l’instant', 'حتى وحدة باقي')}</p>}
      </div>
    </div>
  );
};
