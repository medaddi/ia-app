import React, { useEffect, useState } from 'react';
import { Building2, CheckCircle2, Loader2, TicketCheck, TriangleAlert } from 'lucide-react';
import { apiJson } from '../api';
import { tr } from './ui';
import type { Language } from '../types';

interface Cot { bias: 'BUY' | 'SELL' | 'NEUTRAL'; netPct: number; score: number; strength: number; rising: boolean; crowded: boolean; reportDate: string }
interface Leg { market: string; netPct: number; index: number; net: number }
export interface Skill { cot: Cot; legs: Leg[]; history: { date: string; net: number }[]; agrees: { pick: boolean | null; buy: boolean | null; sell: boolean | null }; caveats: string[] }
interface Ticket {
  order: { symbol: string; side: string; lots: number; entry: number; sl: number; tp: number; stopPips: number; riskUsd: number; marginUsd: number | null; rr: number };
  plain: string; ready: boolean; status: string; source: 'pick' | 'buy' | 'sell';
  verdict: { verdict: 'PASS' | 'BLOCK'; reasons: string[]; warnings: string[] } | null;
  setup: { name: string; condition: string | null } | null;
}

/** A pair's net-position sparkline over the last year (speculators long − short). */
function Spark({ pts }: { pts: { net: number }[] }) {
  if (pts.length < 2) return null;
  const v = pts.map(p => p.net), lo = Math.min(...v, 0), hi = Math.max(...v, 0), span = hi - lo || 1;
  const y = (n: number) => 28 - ((n - lo) / span) * 26 - 1;
  const d = v.map((n, i) => `${(i / (v.length - 1)) * 100},${y(n)}`).join(' ');
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-8" role="img" aria-label="speculators' net position, last 52 weeks">
      <line x1="0" x2="100" y1={y(0)} y2={y(0)} stroke="#334155" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
      <polyline points={d} fill="none" stroke={v[v.length - 1] >= 0 ? '#16C784' : '#EA3943'} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/**
 * The trader skill on this pair (github.com/Jakeschincariol/trader-skill): the big players' positioning (CFTC COT),
 * and the pair's setup or scenario sized to your risk, risk-checked, and turned into a ticket that needs your own yes.
 * Nothing is ever placed by the app.
 */
export const SkillPanel: React.FC<{ symbol: string; skill: Skill | null; error?: string | null; hasPick: boolean; scenarios: { buy: boolean; sell: boolean }; lang: Language }> = ({ symbol, skill, error, hasPick, scenarios, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const q = `symbol=${encodeURIComponent(symbol)}`;
  useEffect(() => { apiJson<{ ticket: Ticket | null }>(`/api/trader/ticket?${q}`).then(r => setTicket(r.ticket)).catch(() => {}); }, [symbol]);  // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr('');
    try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const make = (source: 'pick' | 'buy' | 'sell') => run(source, async () => {
    const r = await apiJson<{ ticket: Ticket }>(`/api/trader/ticket?${q}`, { method: 'POST', body: JSON.stringify({ source }) });
    setTicket(r.ticket); setReply('');
  });
  const c = skill?.cot;
  const tone = (b?: string) => b === 'BUY' ? 'text-emerald-300' : b === 'SELL' ? 'text-rose-300' : 'text-slate-300';
  const agreeChip = (v: boolean | null, label: string) => v === null ? null : (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${v ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
      {label} {v ? t('with the big players', 'avec les gros joueurs', 'مع الكبار') : t('against them', 'contre eux', 'ضدهم')}
    </span>
  );
  const dec = symbol === 'XAU/USD' ? 2 : 5;

  return (
    <section className="mt-4 rounded-xl border border-gold-500/25 bg-gold-500/[0.03] p-3">
      <h4 className="flex items-center gap-1.5 text-sm font-semibold text-gold-200"><Building2 className="w-4 h-4" aria-hidden="true" />{t('Trader skill', 'Skill trader', 'سكيل التريدر')}
        <span className="text-[10px] font-normal text-slate-500">{t('positioning · budget · risk · your yes', 'positionnement · budget · risque · votre oui', 'التموقع · الميزانية · المخاطرة · نعم ديالك')}</span></h4>

      {!c ? <p className="mt-2 text-[11px] text-slate-500">{error ? t(`The CFTC report is unavailable right now (${error}).`, `Le rapport CFTC est indisponible (${error}).`, `تقرير CFTC ماكاينش دابا (${error}).`) : t('No COT data for this pair.', 'Pas de données COT pour cette paire.', 'ما كاين حتى COT لهاد الزوج.')}</p> : (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-[1fr_140px] gap-3">
          <div>
            <p className="text-[12px] text-slate-200">{t('Big players (CFTC COT)', 'Gros joueurs (CFTC COT)', 'الكبار (CFTC COT)')}: <b className={tone(c.bias)}>{c.bias === 'NEUTRAL' ? t('no clear side', 'pas de côté clair', 'ما واضحش') : c.bias}</b>
              {' · '}{t('speculators', 'spéculateurs', 'المضاربين')} <span className={`font-mono ${c.netPct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{c.netPct >= 0 ? '+' : ''}{c.netPct}%</span> net
              {' · '}{c.rising ? t('adding longs', 'ajoutent des achats', 'كيزيدو الشرا') : t('adding shorts', 'ajoutent des ventes', 'كيزيدو البيع')}</p>
            <p className="mt-0.5 text-[10px] text-slate-500">{skill!.legs.map(l => `${l.market} ${l.netPct >= 0 ? '+' : ''}${l.netPct}% · ${t('index', 'indice', 'مؤشر')} ${l.index.toFixed(0)}`).join(' · ')} · {t('report of', 'rapport du', 'تقرير')} {c.reportDate}</p>
            {c.crowded && <p className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-amber-300"><TriangleAlert className="w-3 h-3" />{t('crowded: their side is at its 3-year extreme', 'saturé : leur côté est à son extrême sur 3 ans', 'معمر: الجهة ديالهم ف أقصى 3 سنين')}</p>}
            <div className="mt-1.5 flex flex-wrap gap-1">
              {agreeChip(skill!.agrees.pick, t('The setup is', 'Le setup est', 'السيتاب'))}
              {!hasPick && agreeChip(skill!.agrees.buy, 'BUY')}
              {!hasPick && agreeChip(skill!.agrees.sell, 'SELL')}
            </div>
          </div>
          <div><Spark pts={skill!.history} /><p className="text-[9px] text-slate-500 text-center">{t('net, last 52 weeks', 'net, 52 dernières semaines', 'الصافي، آخر 52 سيمانة')}</p></div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-slate-400">{t('Make the ticket for', 'Faire le ticket pour', 'دير التيكي ديال')}:</span>
        {hasPick && <button type="button" disabled={!!busy} onClick={() => make('pick')} className="h-7 px-2 rounded-lg bg-gold-500/15 text-gold-200 text-[11px] font-semibold ring-1 ring-inset ring-gold-500/40 hover:bg-gold-500/25 cursor-pointer disabled:opacity-50">{busy === 'pick' ? <Loader2 className="w-3 h-3 animate-spin inline" /> : null} {t('the confirmed setup', 'le setup confirmé', 'السيتاب المأكد')}</button>}
        {scenarios.buy && <button type="button" disabled={!!busy} onClick={() => make('buy')} className="h-7 px-2 rounded-lg border border-emerald-500/40 text-emerald-200 text-[11px] hover:bg-emerald-500/10 cursor-pointer disabled:opacity-50">{busy === 'buy' ? <Loader2 className="w-3 h-3 animate-spin inline" /> : null} {t('BUY scenario', 'scénario BUY', 'سيناريو BUY')}</button>}
        {scenarios.sell && <button type="button" disabled={!!busy} onClick={() => make('sell')} className="h-7 px-2 rounded-lg border border-rose-500/40 text-rose-200 text-[11px] hover:bg-rose-500/10 cursor-pointer disabled:opacity-50">{busy === 'sell' ? <Loader2 className="w-3 h-3 animate-spin inline" /> : null} {t('SELL scenario', 'scénario SELL', 'سيناريو SELL')}</button>}
      </div>
      {err && <p className="mt-2 text-[11px] text-rose-300">{err}</p>}

      {ticket && (
        <div className={`mt-2 rounded-lg border p-2.5 ${ticket.ready ? 'border-gold-500/40' : 'border-line'}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-white"><TicketCheck className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />{ticket.plain}</span>
            <span className={`text-[10px] ${ticket.ready ? 'text-gold-300' : ticket.status.startsWith('DONE') ? 'text-emerald-300' : ticket.status.startsWith('BLOCKED') ? 'text-rose-300' : 'text-slate-500'}`}>{ticket.status}</span>
          </div>
          <div className="mt-1 grid grid-cols-2 sm:grid-cols-4 gap-1 text-[10px] font-mono">
            <span className="text-slate-400">{t('entry', 'entrée', 'الدخول')} {ticket.order.entry.toFixed(dec)}</span>
            <span className="text-rose-300">SL {ticket.order.sl.toFixed(dec)} ({ticket.order.stopPips}p)</span>
            <span className="text-emerald-300">TP {ticket.order.tp.toFixed(dec)} (1:{ticket.order.rr})</span>
            <span className="text-slate-300">{t('margin', 'marge', 'هامش')} ${ticket.order.marginUsd ?? '—'}</span>
          </div>
          {ticket.setup && <p className="mt-1 text-[10px] text-slate-500">{ticket.setup.name}{ticket.setup.condition ? ` · ${t('only if', 'seulement si', 'غير إلا')} ${ticket.setup.condition}` : ''}</p>}
          {ticket.verdict && (ticket.verdict.reasons.length > 0 || ticket.verdict.warnings.length > 0) && (
            <ul className="mt-1 space-y-0.5 text-[10px]">
              {ticket.verdict.reasons.map((r, k) => <li key={k} className="text-rose-300">✗ {r}</li>)}
              {ticket.verdict.warnings.map((w, k) => <li key={`w${k}`} className="text-amber-300">⚠ {w}</li>)}
            </ul>
          )}
          {ticket.ready && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <input value={reply} onChange={e => setReply(e.target.value)} placeholder={t('type: yes', 'tapez : yes', 'كتب: yes')}
                aria-label={t(`Your answer for ${ticket.plain}`, `Votre réponse pour ${ticket.plain}`, `الجواب ديالك على ${ticket.plain}`)}
                className="h-7 w-28 rounded-md border border-line bg-black/30 px-2 text-[11px] text-white" />
              <button type="button" disabled={!!busy} onClick={() => run('yes', async () => {
                setTicket((await apiJson<{ ticket: Ticket }>(`/api/trader/ticket/approve?${q}`, { method: 'POST', body: JSON.stringify({ reply }) })).ticket);
              })} className="inline-flex items-center gap-1 h-7 px-2 rounded-lg bg-gold-500/20 text-gold-100 text-[11px] font-semibold hover:bg-gold-500/30 cursor-pointer disabled:opacity-50">
                <CheckCircle2 className="w-3 h-3" aria-hidden="true" />{t('Approve this order', 'Approuver cet ordre', 'وافق على هاد الأوردر')}</button>
              <button type="button" disabled={!!busy} onClick={() => run('no', async () => {
                setTicket((await apiJson<{ ticket: Ticket }>(`/api/trader/ticket/decline?${q}`, { method: 'POST', body: '{}' })).ticket);
              })} className="h-7 px-2 rounded-lg border border-line text-[11px] text-slate-300 hover:bg-white/[0.05] cursor-pointer">{t('Decline', 'Refuser', 'رفض')}</button>
            </div>
          )}
          {ticket.status.startsWith('DONE: approved') && <p className="mt-1 text-[10px] text-emerald-300/90">{t('Recorded. Place this order yourself at your broker: the app never places it.', 'Enregistré. Passez cet ordre vous-même chez votre courtier : l’app ne le passe jamais.', 'تسجل. دير هاد الأوردر براسك عند البروكر: التطبيق عمرو ما كيديرو.')}</p>}
        </div>
      )}
      <p className="mt-2 text-[9px] text-slate-500 leading-relaxed">{t('Lots from your balance and risk % (My account); the stop stays where the setup put it. COT: weekly, as of Tuesday, published Friday, positioning not a signal. Not financial advice.',
        'Lots depuis votre solde et votre % de risque (Mon compte) ; le stop reste où le setup l’a mis. COT : hebdomadaire, au mardi, publié le vendredi, positionnement pas un signal. Pas un conseil financier.',
        'اللوت من الرصيد و% المخاطرة (حسابي)؛ الستوب كيبقى فين حطو السيتاب. COT: كل سيمانة، ديال الثلاثاء، كيتنشر الجمعة، تموقع ماشي إشارة. ماشي نصيحة مالية.')}</p>
    </section>
  );
};
