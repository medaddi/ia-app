import { apiFetch } from '../api';
import React, { useState } from 'react';
import type { InstrumentSymbol } from '../instruments';
import { ArrowUpRight, ArrowDownRight, Send, Copy, Check, X, Clock, CalendarClock } from 'lucide-react';
import type { StrategyResult } from '../strategyTypes';

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
  const signalMin = gold ? 75 : 60;
  const grade = (result as any).grade as string | undefined;
  const statusLabel = {
    SIGNAL: gold ? t('Signal · score ≥ 75', 'Signal · score ≥ 75', 'إشارة · النقطة ≥ 75') : t(`Signal · grade ${grade ?? ''}`, `Signal · note ${grade ?? ''}`, `إشارة · تقييم ${grade ?? ''}`),
    WATCH: gold ? t('Watch · score 60–74, no signal', 'À surveiller · 60–74, pas de signal', 'مراقبة · 60–74، بلا إشارة') : t('Watch · below C+ (60%), no signal', 'À surveiller · sous C+ (60 %), pas de signal', 'مراقبة · تحت C+ (60%)، بلا إشارة'),
    IGNORE: t(`Ignored · score < ${signalMin - 15}`, `Ignoré · score < ${signalMin - 15}`, `متجاهل · النقطة < ${signalMin - 15}`),
    NO_TRADE: t('No trade', 'Pas de trade', 'لا صفقة'),
  }[result.status] ?? result.status;
  const order: Record<string, string> = {
    PENDING: t('Order pending', 'Ordre en attente', 'الأمر معلق'), OPEN: t('In trade', 'En position', 'داخل الصفقة'),
    TP1_HIT: single ? t('Running · 1R reached', 'En cours · 1R atteint', 'جارية · وصلات 1R') : t('TP1 hit · stop at breakeven', 'TP1 touché · stop au point mort', 'ضرب TP1 · الستوب فالدخول'),
    TP2_HIT: single ? t('Running · 2R reached', 'En cours · 2R atteint', 'جارية · وصلات 2R') : t('TP2 hit · runner open', 'TP2 touché · reste ouvert', 'ضرب TP2 · الباقي مفتوح'),
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

  const levels = s ? (single ? [
    { l: `${t('Entry', 'Entrée', 'الدخول')} (${s.entryType})`, v: f(s.entry), sub: s.expiresAt ? `${t('valid until', 'valable jusqu’à', 'صالح حتى')} ${new Date(s.expiresAt * 1000).toISOString().slice(11, 16)} UTC` : '', tone: 'text-gold-200' },
    { l: 'Stop loss', v: f(s.sl), sub: `${s.slPips} pips`, tone: 'text-rose-300' },
    { l: `TP · 1:${rrTarget.toFixed(1)}`, v: f(s.tp3), sub: s.tp3Source, tone: 'text-emerald-300' },
    { l: t('Management', 'Gestion', 'التسيير'), v: 'Set & forget', sub: t('no partials, no breakeven', 'sans partiels, sans point mort', 'بلا إغلاق جزئي، بلا نقل الستوب'), tone: 'text-white' },
  ] : [
    { l: `${t('Entry', 'Entrée', 'الدخول')} (${s.entryType})`, v: f(s.entry), sub: s.expiresAt ? `${t('valid until', 'valable jusqu’à', 'صالح حتى')} ${new Date(s.expiresAt * 1000).toISOString().slice(11, 16)} UTC` : '', tone: 'text-gold-200' },
    { l: 'Stop loss', v: f(s.sl), sub: `${s.slPips} pips`, tone: 'text-rose-300' },
    { l: `TP1 · 1R · ${t('close 50%', 'clôturer 50 %', 'سد 50%')}`, v: f(s.tp1), sub: t('then stop to breakeven', 'puis stop au point mort', 'من بعد الستوب للدخول'), tone: 'text-emerald-300' },
    { l: `TP2 · 1:${s.rrTp2.toFixed(1)}`, v: f(s.tp2), sub: s.tp2Source, tone: 'text-emerald-300' },
    { l: 'TP3', v: f(s.tp3), sub: s.tp3Source, tone: 'text-emerald-300' },
    { l: t('Stop distance', 'Distance du stop', 'مسافة الستوب'), v: f(s.slDistance), sub: `${s.slPips} pips`, tone: 'text-white' },
  ]) : [];

  return (
    <div className="flex flex-col bg-surface border border-line rounded-[var(--radius-card)] overflow-hidden" dir={ar ? 'rtl' : 'ltr'}>
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
        <p className="mt-3 text-xs text-slate-400 break-words" dir="ltr">{result.rejection ? `${t('Missing', 'Manquant', 'ناقص')}: ${result.rejection}` : result.headline}</p>
      </div>

      <div className="px-4 py-3 border-b border-line text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">{t('Trend', 'Tendance', 'الاتجاه')} ({result.timeframes.bias})</span>
          <span className={`font-semibold ${result.bias.direction === 'BULLISH' ? 'text-emerald-300' : result.bias.direction === 'BEARISH' ? 'text-rose-300' : 'text-slate-300'}`}>
            {result.bias.direction === 'BULLISH' ? t('Bullish', 'Haussière', 'صاعد') : result.bias.direction === 'BEARISH' ? t('Bearish', 'Baissière', 'هابط') : t('Neutral', 'Neutre', 'محايد')}
          </span>
        </div>
        <p className="mt-1 text-slate-500 break-words" dir="ltr">{result.bias.detail}</p>
      </div>

      {s && (
        <div className="grid grid-cols-2 gap-px bg-line border-b border-line">
          {levels.map(x => (
            <div key={x.l} className="bg-surface p-3 min-w-0">
              <div className="text-xs text-slate-500 truncate">{x.l}</div>
              <div className={`font-mono text-base font-semibold ${x.tone}`}>{x.v}</div>
              <div className="font-mono text-xs text-slate-500 truncate">{x.sub}</div>
            </div>
          ))}
        </div>
      )}

      <div className="p-4 border-b border-line">
        <h4 className="text-xs font-semibold text-slate-300 mb-2">{gold ? t('Setup checklist', 'Checklist du setup', 'شروط الإعداد') : t('GPA confluences (10% each)', 'Confluences GPA (10 % chacune)', 'نقاط GPA (10% لكل وحدة)')}</h4>
        <ul className="space-y-1.5">
          {result.checklist.map(c => (
            <li key={c.key} className="flex gap-2 text-xs">
              <span className={`mt-0.5 w-4 h-4 shrink-0 rounded-full flex items-center justify-center ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
                {c.passed ? <Check className="w-3 h-3" aria-label={t('passed', 'validé', 'محقق')} /> : <X className="w-3 h-3" aria-label={t('failed', 'non validé', 'ما محققش')} />}
              </span>
              <span className="min-w-0">
                <span className="text-slate-200">{ar && c.ruleAr ? c.ruleAr : c.rule}</span>
                {c.required && <span className="text-slate-500"> · {t('required', 'obligatoire', 'ضروري')}</span>}
                <span className="block text-slate-500 break-words" dir="ltr">{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="px-4 py-3 border-b border-line text-xs space-y-2">
        <div className="flex gap-2 text-slate-400">
          <CalendarClock className="w-4 h-4 shrink-0 text-gold-400" aria-hidden="true" />
          <span className="min-w-0 break-words">
            {result.news.blocked ? `${t('Blocked by news', 'Bloqué par une news', 'محبوس بخبر')}: ${result.news.detail}`
              : result.news.next ? `${t('Next high-impact news', 'Prochaine news forte', 'الخبر القوي الجاي')}: ${result.news.next}`
                : t('No high-impact news scheduled', 'Aucune news forte prévue', 'ما كاين حتى خبر قوي')} <span className="text-slate-600">({result.news.source})</span>
          </span>
        </div>
        {explanation && <p className="text-slate-400 leading-relaxed break-words" dir="ltr">{explanation}</p>}
      </div>

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
        <p role="status" className={`text-xs ${sendState === 'error' ? 'text-rose-300' : sendState === 'sent' ? 'text-emerald-300' : 'text-slate-500'}`}>
          {sendMsg || <span className="inline-flex items-center gap-1"><Clock className="w-3.5 h-3.5" aria-hidden="true" />
            {gold ? t('Telegram fires automatically once per signal (score ≥ 75, all rules passed).', 'Telegram part automatiquement une fois par signal (score ≥ 75, toutes les règles validées).', 'التيليغرام كيتصيفط أوتوماتيكياً مرة لكل إشارة (النقطة ≥ 75، كل الشروط محققة).')
              : t('Telegram fires automatically once per signal (grade C+ 60% or better).', 'Telegram part automatiquement une fois par signal (note C+ 60 % ou mieux).', 'التيليغرام كيتصيفط أوتوماتيكياً مرة لكل إشارة (تقييم C+ 60% أو أحسن).')}</span>}
        </p>
      </div>
    </div>
  );
};
