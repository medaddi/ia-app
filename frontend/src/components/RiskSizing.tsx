import React, { useEffect, useState } from 'react';
import { Scale } from 'lucide-react';
import { apiJson } from '../api';
import type { Language } from '../types';
import { Button, Card, Field, Notice, inputCls, tr, useCopy } from './ui';

/**
 * My USD risk per trade and my lot for a signal. Everything here is the signed-in user's own: the backend scopes every route
 * to the session's user. Nothing places an order.
 */
export interface Sizing {
  status: 'ok' | 'unavailable'; reason?: string; signalId?: string; source?: string; riskUsd?: number | null; lots?: number; estLossUsd?: number;
  saved?: boolean; createdAt?: string; symbol?: string; direction?: string; entry?: number; sl?: number; tp?: number;
  meta?: { contractSize: number; quoteCcy: string; quoteToUsd: number; minLot: number; lotStep: number; costsPerLotUsd: number; riskPerLotUsd: number; stopPips: number;
    conversion?: { pair?: string | null; price?: number; source?: string } };
}

/** My USD risk per trade: private, saved on my account, applied to signals sized from now on. */
export function RiskCard({ isLight, lang }: { isLight: boolean; lang: Language }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [saved, setSaved] = useState<number | null | undefined>(undefined);
  const [val, setVal] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error' | 'info'; text: string } | null>(null);
  useEffect(() => { apiJson<{ riskUsd: number | null }>('/api/me/risk').then(r => { setSaved(r.riskUsd); setVal(r.riskUsd != null ? String(r.riskUsd) : ''); }).catch(() => setSaved(null)); }, []);
  const n = Number(val.replace(',', '.'));
  const ok = val.trim() !== '' && Number.isFinite(n) && n > 0 && n <= 1_000_000;
  const save = async () => {
    setMsg(null);
    try {
      const r = await apiJson<{ riskUsd: number | null }>('/api/me/risk', { method: 'PUT', body: JSON.stringify({ riskUsd: n }) });
      setSaved(r.riskUsd);
      setMsg({ kind: 'ok', text: t(`Saved: $${r.riskUsd} per trade. It applies to signals sized from now on; sizes already saved stay as they were.`,
        `Enregistré : ${r.riskUsd} $ par trade. Il s’applique aux signaux calculés à partir de maintenant ; les tailles déjà enregistrées ne changent pas.`,
        `تسجل: ${r.riskUsd}$ لكل صفقة. كيتطبق على الإشارات اللي غادي تتحسب من دابا؛ الأحجام اللي تسجلات ما كتبدلش.`) });
    } catch (e: any) { setMsg({ kind: 'error', text: e.message }); }
  };
  return (
    <Card isLight={isLight} icon={<Scale className="w-4 h-4" />} title={t('My risk per trade', 'Mon risque par trade', 'الريسك ديالي لكل صفقة')}
      right={saved != null ? <span className="text-xs font-mono text-gold-300">${saved}</span> : undefined}>
      <p className="text-xs text-slate-400 mb-3">{t('The USD amount you accept to lose if a signal hits its stop. Your lot for each signal is calculated from it and the pair’s contract data. Only you see it.',
        'Le montant en USD que vous acceptez de perdre si un signal touche son stop. Votre lot pour chaque signal en est calculé avec les données du contrat de la paire. Vous seul le voyez.',
        'المبلغ بالدولار اللي قابل تخسرو إلا وصلات الإشارة للستوب. اللوت ديالك لكل إشارة كيتحسب منو ومن معطيات العقد ديال الزوج. غير نتا اللي كتشوفو.')}</p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t('Risk in USD', 'Risque en USD', 'الريسك بالدولار')}>
          <input inputMode="decimal" value={val} onChange={e => setVal(e.target.value)} placeholder="50" className={inputCls(isLight)} aria-invalid={val !== '' && !ok} />
        </Field>
        <Button disabled={!ok} onClick={save}>{t('Save', 'Enregistrer', 'سجل')}</Button>
      </div>
      {val !== '' && !ok && <p className="mt-1.5 text-[11px] text-rose-400">{t('A positive amount, for example 50', 'Un montant positif, par exemple 50', 'مبلغ موجب، بحال 50')}</p>}
      {saved === null && !msg && <div className="mt-2"><Notice kind="info">{t('Not set yet: lot sizes are unavailable until you set it.', 'Pas encore défini : les tailles de lot sont indisponibles tant qu’il n’est pas réglé.', 'مازال ما تحدد: الأحجام ما كايناش حتى تحددو.')}</Notice></div>}
      {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </Card>
  );
}

/** One line: my lot for a signal, or why there is none. */
export function SizeLine({ s, lang, decimals }: { s: Sizing | null; lang: Language; decimals?: number }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [copied, copy] = useCopy();
  if (!s) return <p className="text-[11px] text-slate-500">{t('Your size: loading…', 'Votre taille : chargement…', 'الحجم ديالك: كيتحمل…')}</p>;
  if (s.status !== 'ok') return <p className="text-[11px] text-amber-300">{t('Size unavailable', 'Taille indisponible', 'الحجم ما متوفرش')}: <span className="text-slate-400">{s.reason}</span></p>;
  const m = s.meta;
  return (
    <p className="text-[11px] text-slate-300" title={m ? `${m.contractSize} units/lot · ${m.quoteCcy}→USD ${m.quoteToUsd.toFixed(6)}${m.conversion?.pair ? ` (${m.conversion.pair})` : ''} · costs $${m.costsPerLotUsd}/lot · $${m.riskPerLotUsd}/lot at the stop · step ${m.lotStep}, min ${m.minLot}` : undefined}>
      {t('Your size', 'Votre taille', 'الحجم ديالك')}:{' '}
      <button type="button" onClick={() => copy('lot', String(s.lots))} title={t('Tap to copy', 'Touchez pour copier', 'كليكي باش تكوبي')}
        className="font-mono font-semibold text-gold-200 underline decoration-dotted underline-offset-2 hover:text-gold-100">{s.lots} lot</button>
      {copied === 'lot' && <span className="text-emerald-300"> ✓ {t('Copied', 'Copié', 'تكوبا')}</span>}
      {' · '}{t('your risk', 'votre risque', 'الريسك ديالك')} ${s.riskUsd}{' · '}{t('loss at the stop', 'perte au stop', 'الخسارة ف الستوب')} ≈ ${s.estLossUsd}
      {m && <span className="text-slate-500"> ({m.stopPips} pips, {t('costs included', 'coûts inclus', 'بالتكاليف')})</span>}
      {s.saved && <span className="text-slate-500"> · {t('saved', 'enregistrée', 'مسجل')}</span>}
    </p>
  );
}

/** My lot for one sent signal, from /api/me/sizing (my saved snapshot, or computed from my risk and saved). */
/** Told to every lot on screen when the user saves a new risk: a size that was unavailable is asked again (a saved size stays). */
const RISK_EVENT = 'ld-risk-changed';

export function useMySizing(signalId: string | null | undefined): Sizing | null {
  const [s, setS] = useState<Sizing | null>(null);
  const [rev, setRev] = useState(0);
  useEffect(() => {
    const on = () => setRev(r => r + 1);
    window.addEventListener(RISK_EVENT, on);
    return () => window.removeEventListener(RISK_EVENT, on);
  }, []);
  useEffect(() => {
    if (!signalId) { setS(null); return; }
    let alive = true;
    if (!rev) setS(null);
    apiJson<Sizing>(`/api/me/sizing/${encodeURIComponent(signalId)}`).then(r => { if (alive) setS(r); })
      .catch(e => { if (alive) setS({ status: 'unavailable', reason: e.message }); });
    return () => { alive = false; };
  }, [signalId, rev]);
  return s;
}

/**
 * My risk per trade, in one line (the dashboard's overview): the amount, and a field to change it. Saving updates every
 * lot on screen at once. The same setting as My account → "My risk per trade" (one value per user, private).
 */
export function RiskInline({ lang }: { lang: Language }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [saved, setSaved] = useState<number | null | undefined>(undefined);
  const [edit, setEdit] = useState(false);
  const [val, setVal] = useState('');
  const [err, setErr] = useState(false);
  useEffect(() => { apiJson<{ riskUsd: number | null }>('/api/me/risk').then(r => { setSaved(r.riskUsd); if (r.riskUsd == null) setEdit(true); }).catch(() => setSaved(null)); }, []);
  const n = Number(val.replace(',', '.'));
  const ok = val.trim() !== '' && Number.isFinite(n) && n > 0 && n <= 1_000_000;
  const save = async () => {
    try {
      const r = await apiJson<{ riskUsd: number | null }>('/api/me/risk', { method: 'PUT', body: JSON.stringify({ riskUsd: n }) });
      setSaved(r.riskUsd); setEdit(false); setErr(false);
      window.dispatchEvent(new CustomEvent(RISK_EVENT));
    } catch { setErr(true); }
  };
  if (saved === undefined) return null;
  if (!edit) {
    return (
      <button type="button" onClick={() => { setVal(saved != null ? String(saved) : ''); setEdit(true); }}
        className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-line text-[11px] text-slate-300 hover:border-gold-500/40 cursor-pointer"
        title={t('Your risk per trade: every lot is calculated from it', 'Votre risque par trade : chaque lot en est calculé', 'الريسك ديالك لكل صفقة: كل لوت كيتحسب منو')}>
        <Scale className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />{t('Risk', 'Risque', 'الريسك')} <span className="font-mono text-gold-200">${saved}</span>
      </button>
    );
  }
  return (
    <form className="inline-flex items-center gap-1.5" onSubmit={e => { e.preventDefault(); if (ok) save(); }}>
      <label className="inline-flex items-center gap-1.5 h-8 ps-2.5 pe-1 rounded-lg border border-gold-500/40 bg-gold-500/[0.05] text-[11px] text-slate-300">
        <Scale className="w-3.5 h-3.5 text-gold-300" aria-hidden="true" />{t('Risk per trade $', 'Risque par trade $', 'الريسك لكل صفقة $')}
        <input autoFocus={saved != null} inputMode="decimal" value={val} onChange={e => setVal(e.target.value)} placeholder="50" aria-invalid={(val !== '' && !ok) || err}
          className="w-16 bg-transparent font-mono text-gold-100 outline-none placeholder:text-slate-600" />
      </label>
      <button type="submit" disabled={!ok} className="h-8 px-2.5 rounded-lg text-[11px] font-semibold text-ink-strong bg-gold-gradient disabled:opacity-40 cursor-pointer">{t('Save', 'OK', 'سجل')}</button>
    </form>
  );
}
