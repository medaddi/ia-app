import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Crosshair, Loader2, X } from 'lucide-react';
import { apiFetch } from '../api';
import { tr } from './ui';
import type { Language } from '../types';

interface Step { label: string; ok: boolean; detail: string }
interface Stat { setups: number; trades: number; winRate: number; totalR: number; avgR: number }
interface Test extends Stat { days: number; checklist: Stat }
interface Row {
  id: 'A' | 'B' | 'C' | 'D' | 'E'; name: string; status: 'CONFIRMED' | 'RUNNING' | 'BLOCKED' | 'FORMING' | 'WAITING'; reason: string; steps: Step[]; checklist: Step[]; test: Test;
  setup?: { direction: 'BUY' | 'SELL'; entryType: string; entry: number; sl: number; tp: number; rr: number; since: number; validUntil: number; slPips: number; lots: Record<string, number>; rNow: number };
  last?: { direction: string; at: number; result: string; r: number };
}
interface Smc {
  success: boolean; error?: string; symbol: string; price: number; at: number; marketOpen: boolean; decimals: number; verdict: string;
  read: { trend: string; lastBreak: { kind: string; dir: string; level: number; at: number } | null; zone: string | null; bsl: number | null; ssl: number | null };
  strategies: Row[]; test: Test; dataNote: string | null;
}

const TONE: Record<Row['status'], string> = {
  CONFIRMED: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30', RUNNING: 'bg-sky-500/15 text-sky-200 ring-sky-500/30',
  BLOCKED: 'bg-rose-500/15 text-rose-200 ring-rose-500/30', FORMING: 'bg-amber-500/15 text-amber-200 ring-amber-500/30', WAITING: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
};
const hm = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const signed = (v: number) => `${v >= 0 ? '+' : ''}${v}`;

/**
 * The "SMC" button of a pair: one request (backend /api/analyze/smc) that runs the four mechanical SMC strategies
 * (trend continuation, PDH / PDL sweep, supply-demand flip, Asian-range sweep, single candle OB) and shows a CONFIRMED
 * setup only when every rule AND the 7-question master checklist are met, with each rule's check and each strategy's own result on the pair's M5 history.
 */
export const SmcButton: React.FC<{ symbol: string; lang: Language; compact?: boolean }> = ({ symbol, lang, compact = false }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<Smc | null>(null);
  const [err, setErr] = useState('');

  const run = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setOpen(true);
    setBusy(true);
    setErr('');
    try {
      const res = await apiFetch(`/api/analyze/smc?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || j.detail || `HTTP ${res.status}`);
      setData(j);
    } catch (x) {
      setErr(String((x as Error).message || x));
    } finally {
      setBusy(false);
    }
  };

  const status = (s: Row['status']) => s === 'CONFIRMED' ? t('CONFIRMED', 'CONFIRMÉ', 'مأكد') : s === 'RUNNING' ? t('RUNNING', 'EN COURS', 'خدام') : s === 'BLOCKED' ? t('CHECKLIST: NO', 'CHECKLIST : NON', 'الشيكليست: لا')
    : s === 'FORMING' ? t('FORMING', 'EN FORMATION', 'كيتكون') : t('WAITING', 'EN ATTENTE', 'كيتسنا');
  const d = data?.decimals ?? 2;

  return (
    <>
      <button type="button" onClick={run} onKeyDown={e => e.stopPropagation()}
        className={`inline-flex items-center gap-1.5 rounded-lg bg-sky-500/10 text-sky-200 ring-1 ring-inset ring-sky-500/40 hover:bg-sky-500/20 font-semibold cursor-pointer transition-colors ${compact ? 'h-7 px-2 text-[11px]' : 'h-9 px-3 text-xs'}`}
        aria-label={t(`Look for a confirmed SMC setup on ${symbol}`, `Chercher un setup SMC confirmé sur ${symbol}`, `قلب على سيتاب SMC مأكد ف ${symbol}`)}>
        <Crosshair className="w-3.5 h-3.5" aria-hidden="true" />SMC
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" onClick={() => setOpen(false)} role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="smc-title" onClick={e => e.stopPropagation()}
            className="w-full sm:max-w-2xl max-h-[88vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl glass-strong border p-4 sm:p-5">
            <header className="flex items-start justify-between gap-3">
              <div>
                <h3 id="smc-title" className="text-base font-semibold text-white">{t('SMC setup', 'Setup SMC', 'سيتاب SMC')} · {symbol}</h3>
                {data && <p className="mt-0.5 text-xs text-slate-400">{new Date(data.at * 1000).toLocaleString()} · {t('price', 'prix', 'الثمن')} <span className="font-mono text-slate-200">{data.price.toFixed(d)}</span>{data.marketOpen ? '' : ` · ${t('market closed', 'marché fermé', 'السوق مسدود')}`}</p>}
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => run()} disabled={busy} className="h-8 px-2.5 rounded-lg border border-line text-xs text-slate-200 hover:bg-white/[0.05] disabled:opacity-50 cursor-pointer">{t('Re-check', 'Relancer', 'عاود')}</button>
                <button type="button" onClick={() => setOpen(false)} className="h-8 w-8 flex items-center justify-center rounded-lg border border-line text-slate-300 hover:bg-white/[0.05] cursor-pointer" aria-label={t('Close', 'Fermer', 'سد')}><X className="w-4 h-4" /></button>
              </div>
            </header>

            {busy && !data && <div className="py-10 flex items-center justify-center gap-2 text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin" />{t('Checking every SMC rule…', 'Vérification de chaque règle SMC…', 'كيشيك كل قاعدة SMC…')}</div>}
            {err && <p className="mt-4 text-sm text-rose-300">{err}</p>}

            {data && (
              <>
                <div className={`mt-3 rounded-xl border px-3 py-2 text-sm font-semibold ${data.strategies.some(s => s.status === 'CONFIRMED') ? 'border-emerald-500/30 bg-emerald-500/[0.07] text-emerald-200' : 'border-line bg-white/[0.02] text-slate-300'}`}>{data.verdict}</div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-mono">
                  <span className={`px-2 py-1 rounded-lg border border-line ${data.read.trend === 'bullish' ? 'text-emerald-300' : data.read.trend === 'bearish' ? 'text-rose-300' : 'text-slate-300'}`}>H1 {data.read.trend}</span>
                  {data.read.lastBreak && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">{data.read.lastBreak.kind} {data.read.lastBreak.dir} {data.read.lastBreak.level.toFixed(d)} · {hm(data.read.lastBreak.at)}</span>}
                  {data.read.zone && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">{data.read.zone}</span>}
                  {data.read.bsl != null && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">BSL {data.read.bsl.toFixed(d)}</span>}
                  {data.read.ssl != null && <span className="px-2 py-1 rounded-lg border border-line text-slate-300">SSL {data.read.ssl.toFixed(d)}</span>}
                </div>
                {data.dataNote && <p className="mt-2 text-[11px] text-amber-200/90">{data.dataNote}</p>}

                <ul className="mt-3 space-y-2">
                  {data.strategies.map(s => (
                    <li key={s.id} className="rounded-xl border border-line bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-white">{s.id} · {s.name}</span>
                        <span className={`shrink-0 px-2 py-0.5 rounded-md text-[11px] font-bold ring-1 ring-inset ${TONE[s.status]}`}>{status(s.status)}</span>
                      </div>
                      {s.setup && (
                        <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-xs font-mono">
                          <div className={`rounded-lg px-2 py-1.5 ${s.setup.direction === 'BUY' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-rose-500/10 text-rose-300'}`}>{s.setup.direction} LIMIT {s.setup.entry.toFixed(d)}</div>
                          <div className="rounded-lg px-2 py-1.5 bg-rose-500/10 text-rose-200">SL {s.setup.sl.toFixed(d)} <span className="text-slate-500">({s.setup.slPips}p)</span></div>
                          <div className="rounded-lg px-2 py-1.5 bg-emerald-500/10 text-emerald-200">TP {s.setup.tp.toFixed(d)} <span className="text-slate-500">(1:{s.setup.rr})</span></div>
                          <div className="rounded-lg px-2 py-1.5 bg-white/[0.04] text-slate-300">{t('lot', 'lot', 'لوت')} $1000 · {s.setup.lots['1000$']}</div>
                        </div>
                      )}
                      {s.steps.length > 0 && (
                        <ol className="mt-2 space-y-1">
                          {s.steps.map((st, k) => (
                            <li key={k} className="flex items-start gap-1.5 text-[11px] leading-snug">
                              {st.ok ? <Check className="w-3.5 h-3.5 mt-px text-emerald-400 shrink-0" aria-label={t('met', 'validé', 'تحقق')} /> : <X className="w-3.5 h-3.5 mt-px text-slate-500 shrink-0" aria-label={t('not yet', 'pas encore', 'مازال')} />}
                              <span className={st.ok ? 'text-slate-200' : 'text-slate-500'}>{st.label} <span className="font-mono text-slate-500">· {st.detail}</span></span>
                            </li>
                          ))}
                        </ol>
                      )}
                      {s.checklist.length > 0 && (
                        <div className="mt-2 rounded-lg border border-line bg-black/20 p-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{t('Master checklist (7 questions)', 'Checklist (7 questions)', 'الشيكليست (7 أسئلة)')}</p>
                          <ol className="mt-1 space-y-0.5">
                            {s.checklist.map((st, k) => (
                              <li key={k} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                {st.ok ? <Check className="w-3.5 h-3.5 mt-px text-emerald-400 shrink-0" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 mt-px text-rose-400 shrink-0" aria-label={t('no', 'non', 'لا')} />}
                                <span className={st.ok ? 'text-slate-200' : 'text-rose-200'}>{st.label} <span className="font-mono text-slate-500">· {st.detail}</span></span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}
                      <p className="mt-1.5 text-[11px] text-slate-400 leading-snug">{s.reason}</p>
                      <p className="mt-1 text-[10px] text-slate-500 font-mono">
                        {t(`last ${s.test.days} days`, `${s.test.days} derniers jours`, `آخر ${s.test.days} يوم`)}: {s.test.trades} {t('trades', 'trades', 'صفقة')}{s.test.trades ? ` · ${s.test.winRate}% · ${signed(s.test.totalR)}R` : ''} · {t('with the checklist', 'avec la checklist', 'بالشيكليست')}: {s.test.checklist.trades}{s.test.checklist.trades ? ` · ${s.test.checklist.winRate}% · ${signed(s.test.checklist.totalR)}R` : ''}
                        {s.last ? ` · ${t('last', 'dernier', 'آخر')} ${s.last.direction} ${s.last.result} ${signed(s.last.r)}R` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[10px] text-slate-500 leading-relaxed">
                  {t(`The rules are checked mechanically on closed M5 / H1 candles. Tested on this pair's last ${data.test.days} days of M5: ${data.test.trades} trades, ${data.test.winRate}% won, ${signed(data.test.totalR)}R; only those passing the 7 questions: ${data.test.checklist.trades} trades, ${signed(data.test.checklist.totalR)}R. A confirmed setup means every rule and the 7 questions are met, not that it wins: set your own risk.`,
                    `Les règles sont vérifiées mécaniquement sur les bougies M5 / H1 clôturées. Testé sur les ${data.test.days} derniers jours en M5 : ${data.test.trades} trades, ${data.test.winRate} % gagnés, ${signed(data.test.totalR)}R ; avec les 7 questions : ${data.test.checklist.trades} trades, ${signed(data.test.checklist.totalR)}R. Un setup confirmé respecte chaque règle, il ne garantit pas le gain : fixez votre risque.`,
                    `القواعد كتشيكا بطريقة آلية على شموع M5 / H1 المسدودة. تجربة آخر ${data.test.days} يوم ف M5: ${data.test.trades} صفقة، ${data.test.winRate}% ربحات، ${signed(data.test.totalR)}R؛ بالشيكليست: ${data.test.checklist.trades} صفقة، ${signed(data.test.checklist.totalR)}R. سيتاب مأكد معناه كل قاعدة تحققات، ماشي معناه غادي يربح: حدد المخاطرة ديالك.`)}
                </p>
              </>
            )}
          </section>
        </div>, document.body)}
    </>
  );
};
