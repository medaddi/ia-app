import { apiFetch } from '../api';
import React, { useState } from 'react';
import type { InstrumentSymbol } from '../instruments';
import { ArrowUpRight, ArrowDownRight, Send, Copy, Check, X, Clock, CalendarClock } from 'lucide-react';
import type { StrategyResult } from '../strategyTypes';

interface ExunuActiveSetupProps {
  symbol: InstrumentSymbol;
  result: StrategyResult | null;
  explanation?: string;
}

const STATUS: Record<string, { label: string; tone: string }> = {
  SIGNAL: { label: 'Signal · score ≥ 75', tone: 'text-emerald-300 bg-emerald-500/15 ring-emerald-500/30' },
  WATCH: { label: 'Watch · score 60–74, no signal', tone: 'text-gold-200 bg-gold-500/15 ring-gold-500/30' },
  IGNORE: { label: 'Ignored · score < 60', tone: 'text-slate-300 bg-slate-500/15 ring-slate-500/30' },
  NO_TRADE: { label: 'No trade', tone: 'text-slate-300 bg-slate-500/15 ring-slate-500/30' },
};
const ORDER: Record<string, string> = {
  PENDING: 'Order pending', OPEN: 'In trade', TP1_HIT: 'TP1 hit · stop at breakeven', TP2_HIT: 'TP2 hit · runner open',
  CLOSED: 'Closed', CANCELLED: 'Cancelled (TP1 before fill)', EXPIRED: 'Expired (not filled)',
};

/** Side panel: bias, setup checklist (✔/✘), confluence score, levels and the reason for entry or rejection. */
export const ExunuActiveSetup: React.FC<ExunuActiveSetupProps> = ({ symbol, result, explanation }) => {
  const [copied, setCopied] = useState(false);
  const [sendState, setSendState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [sendMsg, setSendMsg] = useState('');

  if (!result) {
    return <div className="p-6 bg-surface border border-line rounded-[var(--radius-card)] min-h-[320px] flex items-center justify-center text-sm text-slate-400">Loading strategy…</div>;
  }
  const s = result.setup;
  const d = result.spec.decimals;
  const f = (v: number) => v.toFixed(d);
  const buy = s?.direction === 'BUY';
  const st = STATUS[result.status];
  const canSend = result.status === 'SIGNAL' && !!s && ['PENDING', 'OPEN'].includes(s.lifecycle.state);

  const copy = () => {
    if (!s) return;
    navigator.clipboard?.writeText(`${result.symbol} ${s.direction} ${s.entryType} ${f(s.entry)}\nSL ${f(s.sl)} (${s.slPips} pips)\nTP1 ${f(s.tp1)}\nTP2 ${f(s.tp2)} (1:${s.rrTp2.toFixed(1)})\nTP3 ${f(s.tp3)}\nScore ${result.score}/100`).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  const send = async () => {
    setSendState('sending');
    try {
      const res = await apiFetch('/api/exunu/dispatch-telegram', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol }) });
      const data = await res.json();
      setSendState(data.success ? 'sent' : 'error');
      setSendMsg(data.success ? 'Sent to Telegram' : data.error || 'Not sent');
    } catch {
      setSendState('error');
      setSendMsg('Server unreachable');
    }
    setTimeout(() => { setSendState('idle'); setSendMsg(''); }, 5000);
  };

  return (
    <div className="flex flex-col bg-surface border border-line rounded-[var(--radius-card)] overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-line">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-slate-400 truncate">{result.strategyName}</span>
          {s && <span className="font-mono text-slate-400 shrink-0">Score <span className={result.score >= 75 ? 'text-emerald-300' : 'text-gold-300'}>{result.score}</span>/100</span>}
        </div>
        <div className="mt-3 flex items-center gap-3">
          {s && (
            <div className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center ${buy ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
              {buy ? <ArrowUpRight className="w-5 h-5" aria-hidden="true" /> : <ArrowDownRight className="w-5 h-5" aria-hidden="true" />}
            </div>
          )}
          <div className="min-w-0">
            <div className="text-lg font-semibold text-white leading-tight">{s ? `${s.direction} ${symbol} · Setup ${s.setup}` : `No trade · ${symbol}`}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <span className={`inline-flex px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${st.tone}`}>{st.label}</span>
              {s && <span className="inline-flex px-2 py-0.5 rounded-md text-xs ring-1 ring-inset ring-line text-slate-300">{ORDER[s.lifecycle.state] ?? s.lifecycle.state}</span>}
            </div>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-400 break-words">{result.rejection ? `Missing: ${result.rejection}` : result.headline}</p>
      </div>

      {/* Bias */}
      <div className="px-4 py-3 border-b border-line text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Bias ({result.timeframes.bias})</span>
          <span className={`font-semibold ${result.bias.direction === 'BULLISH' ? 'text-emerald-300' : result.bias.direction === 'BEARISH' ? 'text-rose-300' : 'text-slate-300'}`}>{result.bias.direction}</span>
        </div>
        <p className="mt-1 text-slate-500 break-words">{result.bias.detail}</p>
      </div>

      {/* Levels */}
      {s && (
        <div className="grid grid-cols-2 gap-px bg-line border-b border-line">
          {[
            { l: `Entry (${s.entryType})`, v: f(s.entry), sub: s.expiresAt ? `valid until ${new Date(s.expiresAt * 1000).toISOString().slice(11, 16)} UTC` : '', tone: 'text-gold-200' },
            { l: 'Stop loss', v: f(s.sl), sub: `${s.slPips} pips`, tone: 'text-rose-300' },
            { l: 'TP1 · 1R · close 50%', v: f(s.tp1), sub: 'then stop to breakeven', tone: 'text-emerald-300' },
            { l: `TP2 · 1:${s.rrTp2.toFixed(1)}`, v: f(s.tp2), sub: s.tp2Source, tone: 'text-emerald-300' },
            { l: 'TP3', v: f(s.tp3), sub: s.tp3Source, tone: 'text-emerald-300' },
            { l: 'Stop distance', v: f(s.slDistance), sub: `${s.slPips} pips`, tone: 'text-white' },
          ].map(x => (
            <div key={x.l} className="bg-surface p-3 min-w-0">
              <div className="text-xs text-slate-500 truncate">{x.l}</div>
              <div className={`font-mono text-base font-semibold ${x.tone}`}>{x.v}</div>
              <div className="font-mono text-xs text-slate-500 truncate">{x.sub}</div>
            </div>
          ))}
        </div>
      )}
      {/* Checklist */}
      <div className="p-4 border-b border-line">
        <h4 className="text-xs font-semibold text-slate-300 mb-2">Setup checklist</h4>
        <ul className="space-y-1.5">
          {result.checklist.map(c => (
            <li key={c.key} className="flex gap-2 text-xs">
              <span className={`mt-0.5 w-4 h-4 shrink-0 rounded-full flex items-center justify-center ${c.passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
                {c.passed ? <Check className="w-3 h-3" aria-label="passed" /> : <X className="w-3 h-3" aria-label="failed" />}
              </span>
              <span className="min-w-0">
                <span className="text-slate-200">{c.rule}</span>
                {!c.required && <span className="text-slate-500"> (score only)</span>}
                <span className="block text-slate-500 break-words">{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* News + explanation */}
      <div className="px-4 py-3 border-b border-line text-xs space-y-2">
        <div className="flex gap-2 text-slate-400">
          <CalendarClock className="w-4 h-4 shrink-0 text-gold-400" aria-hidden="true" />
          <span className="min-w-0 break-words">{result.news.blocked ? `Blocked: ${result.news.detail}` : result.news.next ? `Next high-impact: ${result.news.next}` : 'No high-impact news scheduled'} <span className="text-slate-600">({result.news.source})</span></span>
        </div>
        {explanation && <p className="text-slate-400 leading-relaxed break-words">{explanation}</p>}
      </div>

      {/* Actions */}
      <div className="p-4 flex flex-col gap-2">
        <div className="flex gap-2">
          <button onClick={copy} disabled={!s} className="flex-1 h-10 inline-flex items-center justify-center gap-1.5 rounded-lg border border-line text-xs font-medium text-slate-200 hover:bg-surface-2 disabled:opacity-40">
            {copied ? <Check className="w-4 h-4 text-emerald-300" /> : <Copy className="w-4 h-4" />}{copied ? 'Copied' : 'Copy levels'}
          </button>
          <button onClick={send} disabled={!canSend || sendState === 'sending'} title={canSend ? 'Send this signal to Telegram' : 'Only a valid SIGNAL can be sent'}
            className="flex-1 h-10 inline-flex items-center justify-center gap-1.5 rounded-lg bg-gold-gradient bg-gold-gradient-hover text-ink-strong text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed">
            <Send className="w-4 h-4" />{sendState === 'sending' ? 'Sending…' : 'Send to Telegram'}
          </button>
        </div>
        <p role="status" className={`text-xs ${sendState === 'error' ? 'text-rose-300' : sendState === 'sent' ? 'text-emerald-300' : 'text-slate-500'}`}>
          {sendMsg || <span className="inline-flex items-center gap-1"><Clock className="w-3.5 h-3.5" aria-hidden="true" />Telegram fires automatically once per signal (score ≥ 75, all rules passed).</span>}
        </p>
      </div>
    </div>
  );
};
