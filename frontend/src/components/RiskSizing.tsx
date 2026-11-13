import React, { useEffect, useState } from 'react';
import { Scale } from 'lucide-react';
import { apiJson } from '../api';
import type { Language } from '../types';
import { Button, Card, Field, Notice, inputCls, tr } from './ui';

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
  if (!s) return <p className="text-[11px] text-slate-500">{t('Your size: loading…', 'Votre taille : chargement…', 'الحجم ديالك: كيتحمل…')}</p>;
  if (s.status !== 'ok') return <p className="text-[11px] text-amber-300">{t('Size unavailable', 'Taille indisponible', 'الحجم ما متوفرش')}: <span className="text-slate-400">{s.reason}</span></p>;
  const m = s.meta;
  return (
    <p className="text-[11px] text-slate-300" title={m ? `${m.contractSize} units/lot · ${m.quoteCcy}→USD ${m.quoteToUsd.toFixed(6)}${m.conversion?.pair ? ` (${m.conversion.pair})` : ''} · costs $${m.costsPerLotUsd}/lot · $${m.riskPerLotUsd}/lot at the stop · step ${m.lotStep}, min ${m.minLot}` : undefined}>
      {t('Your size', 'Votre taille', 'الحجم ديالك')}: <span className="font-mono font-semibold text-gold-200">{s.lots} lot</span>
      {' · '}{t('your risk', 'votre risque', 'الريسك ديالك')} ${s.riskUsd}{' · '}{t('loss at the stop', 'perte au stop', 'الخسارة ف الستوب')} ≈ ${s.estLossUsd}
      {m && <span className="text-slate-500"> ({m.stopPips} pips, {t('costs included', 'coûts inclus', 'بالتكاليف')})</span>}
      {s.saved && <span className="text-slate-500"> · {t('saved', 'enregistrée', 'مسجل')}</span>}
    </p>
  );
}

/** My lot for one sent signal, from /api/me/sizing (my saved snapshot, or computed from my risk and saved). */
export function useMySizing(signalId: string | null | undefined): Sizing | null {
  const [s, setS] = useState<Sizing | null>(null);
  useEffect(() => {
    if (!signalId) { setS(null); return; }
    let alive = true;
    setS(null);
    apiJson<Sizing>(`/api/me/sizing/${encodeURIComponent(signalId)}`).then(r => { if (alive) setS(r); })
      .catch(e => { if (alive) setS({ status: 'unavailable', reason: e.message }); });
    return () => { alive = false; };
  }, [signalId]);
  return s;
}
