import React, { useEffect, useState } from 'react';
import { ClipboardPaste, Scale } from 'lucide-react';
import { apiJson } from '../api';
import type { Language } from '../types';
import { Button, Card, Field, Notice, inputCls, tr } from './ui';

/**
 * My USD risk per trade, my lot for a signal, and pasting a signal copied from Telegram (the owner's prompt of 2026-11-11).
 * Everything here is the signed-in user's own: the backend scopes every route to the session's user. Nothing places an order.
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

interface ImportResult { success: boolean; errors?: string[]; signal?: { id: string; symbol: string; side: string; entry: number; sl: number; tp: number; tf: string; time: number }; sizing?: Sizing; imported?: boolean }

/** Paste a signal copied from Telegram: checked against the signal the app sent, previewed with MY lot, then saved. */
export function ImportCard({ isLight, lang }: { isLight: boolean; lang: Language }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [text, setText] = useState('');
  const [res, setRes] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState<Sizing[]>([]);
  const loadMine = () => apiJson<{ items: Sizing[] }>('/api/me/sizings').then(r => setMine(r.items)).catch(() => setMine([]));
  useEffect(() => { loadMine(); }, []);
  const call = async (path: string) => {
    setBusy(true);
    try { setRes(await apiJson<ImportResult>(path, { method: 'POST', body: JSON.stringify({ text }) })); } catch (e: any) { setRes({ success: false, errors: [e.message] }); }
    setBusy(false);
  };
  const pasteFromClipboard = async () => { try { setText(await navigator.clipboard.readText()); setRes(null); } catch { /* the browser refused: paste by hand */ } };
  const g = res?.signal;
  const dec = g ? (g.symbol.startsWith('XAU') ? 2 : g.symbol.endsWith('JPY') ? 3 : 5) : 5;
  return (
    <Card isLight={isLight} icon={<ClipboardPaste className="w-4 h-4" />} title={t('Import a signal', 'Importer un signal', 'استورد إشارة')}>
      <p className="text-xs text-slate-400 mb-2">{t('In Telegram tap “Copy setup data” (or copy the line starting with LD|), then paste it here. The app checks it against the signal it sent and calculates YOUR lot from YOUR risk. No order is placed.',
        'Dans Telegram touchez « Copy setup data » (ou copiez la ligne qui commence par LD|), puis collez-la ici. L’app la vérifie avec le signal qu’elle a envoyé et calcule VOTRE lot avec VOTRE risque. Aucun ordre n’est passé.',
        'ف تيليغرام ضغط “Copy setup data” (ولا نسخ السطر اللي كيبدا ب LD|)، ولصقو هنا. التطبيق كيقارنو مع الإشارة اللي صيفط وكيحسب اللوت ديالك من الريسك ديالك. حتى أمر ما كيتدار.')}</p>
      <textarea value={text} onChange={e => { setText(e.target.value); setRes(null); }} rows={3} spellCheck={false}
        placeholder="LD|v=1|id=SMC-XAUUSD-…|symbol=XAUUSD|side=SELL|entry=…|sl=…|tp=…|tf=M15|time=…Z" className={`${inputCls(isLight)} font-mono text-xs`} aria-label={t('Pasted signal', 'Signal collé', 'الإشارة الملصوقة')} />
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="ghost" onClick={pasteFromClipboard}>{t('Paste', 'Coller', 'لصق')}</Button>
        <Button variant="ghost" disabled={!text.trim() || busy} onClick={() => call('/api/me/import/preview')}>{t('Check', 'Vérifier', 'تحقق')}</Button>
        <Button disabled={!res?.success || res.imported || busy} onClick={async () => { await call('/api/me/import'); loadMine(); }}>{t('Import', 'Importer', 'استورد')}</Button>
      </div>
      {res && !res.success && <div className="mt-2"><Notice kind="error">{t('Rejected', 'Refusé', 'مرفوض')}: {(res.errors ?? []).join(' · ')}</Notice></div>}
      {res?.success && g && (
        <div className="mt-2 rounded-lg border border-line bg-white/[0.02] px-3 py-2 text-xs">
          <p className="font-mono text-slate-200"><span className={g.side === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{g.side}</span> {g.symbol} · {g.tf} · {new Date(g.time * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC</p>
          <p className="font-mono text-slate-300">Entry {g.entry.toFixed(dec)} · SL {g.sl.toFixed(dec)} · TP {g.tp.toFixed(dec)}</p>
          <p className="text-[10px] text-slate-500">ID {g.id}</p>
          <div className="mt-1"><SizeLine s={res.sizing ?? null} lang={lang} /></div>
          {res.imported && <p className="mt-1 text-[11px] text-emerald-300">{t('Imported into your history. No order was placed.', 'Importé dans votre historique. Aucun ordre passé.', 'تزاد للتاريخ ديالك. حتى أمر ما تدار.')}</p>}
        </div>
      )}
      {mine.length > 0 && (
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">{t('My saved sizes', 'Mes tailles enregistrées', 'الأحجام ديالي المسجلة')}</p>
          <ul className="mt-1 space-y-0.5 text-[11px] font-mono text-slate-300">
            {mine.slice(0, 12).map(x => (
              <li key={x.signalId} className="flex flex-wrap gap-x-2">
                <span className={x.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{x.direction}</span><span>{x.symbol}</span>
                <span className="text-gold-200">{x.lots} lot</span><span className="text-slate-500">${x.riskUsd} · {x.source} · {x.createdAt?.slice(0, 16).replace('T', ' ')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
