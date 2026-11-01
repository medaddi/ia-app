import { apiFetch, apiJson } from '../api';
import React, { useEffect, useState } from 'react';
import type { InstrumentSymbol } from '../instruments';
import { ArrowUpRight, ArrowDownRight, Send, Copy, Check, X } from 'lucide-react';
import type { StrategyResult, TpReach } from '../strategyTypes';
import { TradeManagement } from './TradeManagement';
import { TradeProgress } from './TradeProgress';

interface ExunuActiveSetupProps {
  symbol: InstrumentSymbol;
  result: StrategyResult | null;
  explanation?: string;
  lang?: string;
}

const TONE: Record<string, string> = {
  SIGNAL: 'text-emerald-300 bg-emerald-500/15 ring-emerald-500/30', WATCH: 'text-gold-200 bg-gold-500/15 ring-gold-500/30',
  IGNORE: 'text-slate-300 bg-slate-500/15 ring-slate-500/30', NO_TRADE: 'text-slate-300 bg-slate-500/15 ring-slate-500/30',
};

/** Side panel: bias, the strategy's checklist (✔/✘), its score / grade, the levels and why it enters or not. */
export const ExunuActiveSetup: React.FC<ExunuActiveSetupProps> = ({ symbol, result, explanation, lang = 'en' }) => {
  const ar = lang === 'ar';
  const t = (en: string, fr: string, a: string) => (ar ? a : lang === 'fr' ? fr : en);
  const [copied, setCopied] = useState(false);
  const [sendState, setSendState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [sendMsg, setSendMsg] = useState('');

  if (!result) {
    return <div className="p-6 bg-surface border border-line rounded-[var(--radius-card)] min-h-[320px] flex items-center justify-center text-sm text-slate-400">{t('Loading the strategy…', 'Chargement de la stratégie…', 'كيتحمل الاستراتيجية…')}</div>;
  }
  const s = result.setup;
  const d = result.spec.decimals;
  const f = (v: number) => v.toFixed(d);
  const buy = s?.direction === 'BUY';
  const gold = result.symbol === 'XAUUSD';
  const single = !!s && s.params?.breakeven === false; // forex set & forget: one target
  const scored = gold || result.strategy === 'RSI2_Connors_H4';  // score ≥ 75 (gold, RSI(2)) rather than the GPA grade
  const signalMin = scored ? 75 : 60;
  const grade = (result as any).grade as string | undefined;
  const statusLabel = {
    SIGNAL: scored ? t('Signal', 'Signal', 'إشارة') : t(`Signal · ${grade ?? ''}`, `Signal · ${grade ?? ''}`, `إشارة · ${grade ?? ''}`),
    WATCH: scored ? t('Watch · score 60–74, no signal', 'À surveiller · 60–74, pas de signal', 'مراقبة · 60–74، بلا إشارة') : t('Watch · below C+ (60%), no signal', 'À surveiller · sous C+ (60 %), pas de signal', 'مراقبة · تحت C+ (60%)، بلا إشارة'),
    IGNORE: t(`Ignored · score < ${signalMin - 15}`, `Ignoré · score < ${signalMin - 15}`, `متجاهل · النقطة < ${signalMin - 15}`),
    NO_TRADE: t('No trade', 'Pas de trade', 'لا صفقة'),
  }[result.status] ?? result.status;
  const order: Record<string, string> = {
    PENDING: t('Order pending', 'Ordre en attente', 'الأمر معلق'), OPEN: t('In trade', 'En position', 'داخل الصفقة'),
    TP1_HIT: single ? t('Running · 1R reached', 'En cours · 1R atteint', 'جارية · وصلات 1R') : t('TP1 hit · stop at breakeven', 'TP1 touché · stop au point mort', 'ضرب TP1 · الستوب فالدخول'),
    TP2_HIT: single ? t('Running · 1.5R reached', 'En cours · 1,5R atteint', 'جارية · وصلات 1.5R') : t('TP2 hit · runner open', 'TP2 touché · reste ouvert', 'ضرب TP2 · الباقي مفتوح'),
    CLOSED: t('Closed', 'Clôturé', 'مسدودة'), CANCELLED: t('Cancelled (TP1 before fill)', 'Annulé (TP1 avant exécution)', 'ملغاة (TP1 قبل الدخول)'),
    EXPIRED: t('Expired (not filled)', 'Expiré (non exécuté)', 'انتهت (ما تنفذاتش)'),
  };
  const canSend = result.status === 'SIGNAL' && !!s && ['PENDING', 'OPEN'].includes(s.lifecycle.state);
  const rrTarget = s ? Math.abs(s.tp3 - s.entry) / Math.abs(s.entry - s.sl) : 0;

  const copy = () => {
    if (!s) return;
    const text = single
      ? `${result.symbol} ${s.direction} ${s.entryType} ${f(s.entry)}\nSL ${f(s.sl)} (${s.slPips} pips)\nTP ${f(s.tp3)} (1:${rrTarget.toFixed(1)})${grade ? `\nGrade ${grade} ${result.score}%` : ''}`
      : `${result.symbol} ${s.direction} ${s.entryType} ${f(s.entry)}\nSL ${f(s.sl)} (${s.slPips} pips)\nTP1 ${f(s.tp1)}\nTP2 ${f(s.tp2)} (1:${s.rrTp2.toFixed(1)})\nTP3 ${f(s.tp3)}\nScore ${result.score}/100`;
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  const send = async () => {
    setSendState('sending');
    try {
      const res = await apiFetch('/api/exunu/dispatch-telegram', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol }) });
      const data = await res.json();
      setSendState(data.success ? 'sent' : 'error');
      setSendMsg(data.success ? t('Sent to Telegram', 'Envoyé sur Telegram', 'تصيفطات للتيليغرام') : data.error || t('Not sent', 'Non envoyé', 'ما تصيفطاتش'));
    } catch {
      setSendState('error');
      setSendMsg(t('Server unreachable', 'Serveur injoignable', 'السيرفر ما جاوبش'));
    }
    setTimeout(() => { setSendState('idle'); setSendMsg(''); }, 5000);
  };


  return (
    <div className="flex flex-col glass border rounded-[var(--radius-card)] overflow-hidden" dir={ar ? 'rtl' : 'ltr'}>
      <div className="p-4 border-b border-line">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-slate-400 truncate">{result.strategyName}</span>
          {s && (gold
            ? <span className="font-mono text-slate-400 shrink-0">Score <span className={result.score >= 75 ? 'text-emerald-300' : 'text-gold-300'}>{result.score}</span>/100</span>
            : <span className="font-mono text-slate-400 shrink-0">{t('Grade', 'Note', 'التقييم')} <span className={result.score >= 60 ? 'text-emerald-300' : 'text-gold-300'}>{grade} {result.score}%</span></span>)}
        </div>
        <div className="mt-3 flex items-center gap-3">
          {s && (
            <div className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center ${buy ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
              {buy ? <ArrowUpRight className="w-5 h-5" aria-hidden="true" /> : <ArrowDownRight className="w-5 h-5" aria-hidden="true" />}
            </div>
          )}
          <div className="min-w-0">
            <div className="text-lg font-semibold text-white leading-tight">{s ? `${s.direction === 'BUY' ? t('BUY', 'ACHAT', 'شراء') : t('SELL', 'VENTE', 'بيع')} ${symbol} · ${s.setup}` : `${t('No trade', 'Pas de trade', 'لا صفقة')} · ${symbol}`}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <span className={`inline-flex px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${TONE[result.status] ?? TONE.NO_TRADE}`}>{statusLabel}</span>
              {s && <span className="inline-flex px-2 py-0.5 rounded-md text-xs ring-1 ring-inset ring-line text-slate-300">{order[s.lifecycle.state] ?? s.lifecycle.state}</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-line text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">{t('Trend', 'Tendance', 'الاتجاه')} ({result.timeframes.bias})</span>
          <span className={`font-semibold ${result.bias.direction === 'BULLISH' ? 'text-emerald-300' : result.bias.direction === 'BEARISH' ? 'text-rose-300' : 'text-slate-300'}`}>
            {result.bias.direction === 'BULLISH' ? t('Bullish', 'Haussière', 'صاعد') : result.bias.direction === 'BEARISH' ? t('Bearish', 'Baissière', 'هابط') : t('Neutral', 'Neutre', 'محايد')}
          </span>
        </div>
      </div>

      {s && (
        <div className="p-4 border-b border-line">
          {/* The trade as a live bar: stop, entry and target, with the price now moving between them */}
          <TradeProgress direction={s.direction} entry={s.entry} sl={s.sl} tp={s.tp3} price={result.price} decimals={result.spec.decimals}
            pip={result.spec.pipSize} lang={(ar ? 'ar' : lang === 'fr' ? 'fr' : 'en')} />
          <TradeManagement result={result} lang={(ar ? 'ar' : lang === 'fr' ? 'fr' : 'en')} />
          <AutoLot symbol={result.spec.displaySymbol} entry={s.entry} sl={s.sl} t={t} />
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-mono">
            <span className="px-2 py-1 rounded-lg bg-surface-2 border border-line text-slate-300">1:{rrTarget.toFixed(1)}</span>
            {result.tpReach?.targetHit != null && (
              <span className={`px-2 py-1 rounded-lg border ${result.tpReach.targetHit >= 50 ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-gold-500/10 border-gold-500/30 text-gold-200'}`}>
                {t('TP hit', 'TP atteint', 'TP وصلو')} {result.tpReach.targetHit}%
              </span>
            )}
            <span className="px-2 py-1 rounded-lg bg-surface-2 border border-line text-slate-300">SL {s.slPips} pips</span>
          </div>
        </div>
      )}

      {s && result.tpReach && <TargetOptions reach={result.tpReach} planned={rrTarget} f={f} t={t} />}

      <div className="p-4 flex flex-col gap-2">
        <div className="flex gap-2">
          <button onClick={copy} disabled={!s} className="flex-1 h-10 inline-flex items-center justify-center gap-1.5 rounded-lg border border-line text-xs font-medium text-slate-200 hover:bg-surface-2 disabled:opacity-40 cursor-pointer transition-colors">
            {copied ? <Check className="w-4 h-4 text-emerald-300" /> : <Copy className="w-4 h-4" />}{copied ? t('Copied', 'Copié', 'تنسخ') : t('Copy levels', 'Copier les niveaux', 'نسخ المستويات')}
          </button>
          <button onClick={send} disabled={!canSend || sendState === 'sending'}
            title={canSend ? t('Send this signal to Telegram', 'Envoyer ce signal sur Telegram', 'صيفط هاد الإشارة للتيليغرام') : t('Only a valid SIGNAL can be sent', 'Seul un SIGNAL valide peut être envoyé', 'غير إشارة صالحة لي تقدر تتصيفط')}
            className="flex-1 h-10 inline-flex items-center justify-center gap-1.5 rounded-lg bg-gold-gradient bg-gold-gradient-hover text-ink-strong text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">
            <Send className="w-4 h-4" />{sendState === 'sending' ? t('Sending…', 'Envoi…', 'كيتصيفط…') : t('Send to Telegram', 'Envoyer sur Telegram', 'صيفط للتيليغرام')}
          </button>
        </div>
        {sendMsg && <p role="status" className={`text-xs ${sendState === 'error' ? 'text-rose-300' : 'text-emerald-300'}`}>{sendMsg}</p>}
      </div>
    </div>
  );
};


/** Reachable targets: each R multiple with the share of this pair's past trades that got there before the stop. */
const MIN_SAMPLE = 15;  // below this the odds are shown but not trusted
function TargetOptions({ reach, planned, f, t }: { reach: TpReach; planned: number; f: (v: number) => string; t: (en: string, fr: string, ar: string) => string }) {
  const few = reach.sample < MIN_SAMPLE;
  const steps = reach.steps.filter(st => st.price !== undefined && st.r <= Math.max(planned, 3) + 1e-9);
  return (
    <details className="group p-4 border-b border-line">
      <summary className="flex items-baseline justify-between gap-2 cursor-pointer list-none">
        <h4 className="text-xs font-semibold text-slate-300">{t('Reachable targets', 'Objectifs atteignables', 'الأهداف لي يقدر يوصل ليها السوق')} <span className="text-slate-500 group-open:hidden">▸</span><span className="text-slate-500 hidden group-open:inline">▾</span></h4>
        <span className="text-[11px] text-slate-500">{t(`${reach.sample} past trades`, `${reach.sample} trades passés`, `${reach.sample} صفقة فاتت`)}</span>
      </summary>
      <div className="mt-2">
      {reach.sample === 0 ? (
        <p className="text-xs text-slate-500">{t('No closed trade on this pair yet: no odds to show.', 'Aucun trade clôturé sur cette paire : pas encore de probabilités.', 'ما كاينة حتى صفقة مسدودة ف هاد الزوج: ما كاينينش احتمالات.')}</p>
      ) : (
        <ul className="space-y-1">
          {steps.map(st => {
            const pct = st.reach ?? 0;
            const isPlan = Math.abs(st.r - planned) < 0.05;
            const isReal = !few && reach.realistic === st.r;
            return (
              <li key={st.r} className={`grid grid-cols-[3rem_1fr_5.5rem_2.75rem] items-center gap-2 text-xs rounded-lg px-2 py-1 ${isReal ? 'bg-emerald-500/[0.07] ring-1 ring-inset ring-emerald-500/25' : ''}`}>
                <span className="font-mono text-slate-300">{st.r}R</span>
                <span className="h-1.5 rounded-full bg-surface-2 overflow-hidden" aria-hidden="true">
                  <span className={`block h-full rounded-full ${pct >= 50 ? 'bg-emerald-400/80' : pct >= 30 ? 'bg-gold-400/80' : 'bg-rose-400/70'}`} style={{ width: `${pct}%` }} />
                </span>
                <span className="font-mono text-slate-200 text-end">{f(st.price!)}</span>
                <span className={`font-mono text-end ${pct >= 50 ? 'text-emerald-300' : pct >= 30 ? 'text-gold-200' : 'text-rose-300'}`}>{pct}%</span>
                {(isPlan || isReal) && (
                  <span className="col-span-4 -mt-0.5 text-[10px] text-slate-500">
                    {isReal && <span className="text-emerald-300">{t('Realistic: reached by at least half the past trades', 'Réaliste : atteint par au moins la moitié des trades passés', 'واقعي: وصلو ليه على الأقل نص الصفقات الفايتة')}</span>}
                    {isReal && isPlan && ' · '}
                    {isPlan && t('the strategy’s target', 'l’objectif de la stratégie', 'هدف الاستراتيجية')}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      </div>
    </details>
  );
}


/** The lot for this trade, worked out from the risk saved in the user's account (Mon compte): the trade's own stop,
 * spread and slippage included, rounded down so the loss at the stop stays within that risk. */
interface LotAnswer { lots: number; actualRisk: number; riskUsd: number; tooSmall: boolean }
function AutoLot({ symbol, entry, sl, t }: { symbol: string; entry: number; sl: number; t: (en: string, fr: string, ar: string) => string }) {
  const [lot, setLot] = useState<LotAnswer | null>(null);
  useEffect(() => {
    let live = true;
    apiJson<LotAnswer>(`/api/lot?symbol=${encodeURIComponent(symbol)}&entry=${entry}&sl=${sl}`)
      .then(r => { if (live) setLot(r); }).catch(() => { if (live) setLot(null); });
    return () => { live = false; };
  }, [symbol, entry, sl]);
  if (!lot) return null;
  if (!lot.riskUsd) {
    return (
      <p className="mt-3 rounded-xl border border-gold-500/30 bg-gold-500/[0.06] px-3 py-2 text-xs text-gold-200">
        {t('Set your risk in My account', 'Définissez votre risque dans Mon compte', 'حدد المخاطرة ف حسابي')}
      </p>
    );
  }
  return (
    <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-gold-500/30 bg-gold-500/[0.07] px-3 py-2.5">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-gold-300/80">{t('Your lot', 'Votre lot', 'اللوت ديالك')}</div>
        <div className="font-mono text-2xl font-bold tabular-nums text-gold-200">{lot.lots.toFixed(2)}</div>
      </div>
      <div className="text-end text-[11px] font-mono leading-relaxed">
        <div className="text-rose-300">−${lot.actualRisk.toFixed(2)} {t('at the stop', 'au stop', 'ف الستوب')}</div>
        {lot.tooSmall && <div className="text-gold-300">{t('min. lot', 'lot min.', 'أقل لوت')}</div>}
      </div>
    </div>
  );
}
