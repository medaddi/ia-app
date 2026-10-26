import { apiFetch } from '../api';
import React, { useEffect, useRef, useState } from 'react';
import { Bot, Check, Send, X } from 'lucide-react';

interface AgentPanelProps {
  isOpen: boolean;
  onClose: () => void;
  lang: string;
}

interface Msg {
  role: 'user' | 'agent';
  text: string;
  source?: string;
  note?: string;
}

const QUICK: Record<string, string[]> = {
  fr: ['Analyse XAUUSD maintenant', 'Pourquoi pas de trade sur EURUSD ?', 'Quel est le biais du gold ?'],
  en: ['Analyse XAUUSD now', 'Why no trade on EURUSD?', 'What is the gold bias?'],
  ar: ['حلل الذهب الآن', 'لماذا لا توجد صفقة على اليورو؟', 'ما هو اتجاه الذهب؟'],
};

/** Minimal formatting: **bold** and line breaks. Text is rendered as React nodes (no HTML injection). */
function Formatted({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => {
        // Checklist lines get real icons (the ✔/✘ glyphs are missing from many fonts)
        const pass = line.startsWith('✔'), fail = line.startsWith('✘');
        const body = pass || fail ? line.slice(1).trimStart() : line;
        return (
          <p key={i} className={pass || fail ? 'flex gap-1.5 text-slate-400' : ''}>
            {pass && <Check className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-300" aria-label="passed" />}
            {fail && <X className="w-3.5 h-3.5 mt-0.5 shrink-0 text-rose-300" aria-label="failed" />}
            <span>{body.split(/(\*\*[^*]+\*\*)/g).map((part, j) => (part.startsWith('**') && part.endsWith('**') ? <strong key={j} className="text-white">{part.slice(2, -2)}</strong> : <React.Fragment key={j}>{part}</React.Fragment>))}</span>
          </p>
        );
      })}
    </>
  );
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ isOpen, onClose, lang }) => {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [msgs, busy]);
  useEffect(() => { if (isOpen) setTimeout(() => inputRef.current?.focus(), 50); }, [isOpen]);
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setMsgs(m => [...m, { role: 'user', text: question }]);
    setInput('');
    setBusy(true);
    try {
      const res = await apiFetch('/api/agent/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
      const j = await res.json();
      setMsgs(m => [...m, j.success ? { role: 'agent', text: j.answer, source: j.source, note: j.note } : { role: 'agent', text: j.error || 'Agent error' }]);
    } catch {
      setMsgs(m => [...m, { role: 'agent', text: 'Agent unreachable.' }]);
    } finally {
      setBusy(false);
    }
  };

  if (!isOpen) return null;
  const quick = QUICK[lang] || QUICK.en;

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button className="absolute inset-0 bg-black/60" aria-label="Close agent" onClick={onClose} />
      <section role="dialog" aria-modal="true" aria-label="LiquidityDissection agent" className="relative w-full sm:w-[460px] h-full flex flex-col bg-surface border-s border-line shadow-[var(--shadow-float)]">
        <header className="flex items-center justify-between gap-2 px-4 h-14 border-b border-line shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-8 h-8 rounded-lg bg-gold-500/15 text-gold-300 flex items-center justify-center"><Bot className="w-4 h-4" aria-hidden="true" /></span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">LiquidityDissection Agent</div>
              <div className="text-xs text-slate-500 truncate">Answers only from the XAUUSD and EURUSD strategy data</div>
            </div>
          </div>
          <button onClick={onClose} className="h-9 w-9 flex items-center justify-center rounded-lg border border-line text-slate-400 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 text-sm">
          {msgs.length === 0 && (
            <div className="space-y-3">
              <p className="text-slate-400 text-xs leading-relaxed">Ask about either instrument in Darija, French or English. The agent reads the strategies' live checklist and levels; it never invents prices and cannot place orders.</p>
              <div className="flex flex-wrap gap-2">
                {quick.map(q => (
                  <button key={q} onClick={() => ask(q)} className="px-3 h-8 rounded-full border border-line text-xs text-slate-300 hover:border-gold-500/50 hover:text-gold-200">{q}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
              <div className={`max-w-[92%] rounded-xl px-3 py-2 space-y-1 text-xs leading-relaxed break-words ${m.role === 'user' ? 'bg-gold-500/15 text-gold-100' : 'bg-surface-2 border border-line text-slate-200'}`} dir="auto">
                <Formatted text={m.text} />
                {m.role === 'agent' && m.source && (
                  <p className="pt-1 text-[11px] text-slate-500">{m.source === 'gemini' ? 'Gemini · checked against strategy data' : 'Deterministic answer from strategy data'}{m.note ? ` · ${m.note}` : ''}</p>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="text-xs text-slate-500">Reading the strategies…</div>}
          <div ref={endRef} />
        </div>

        <form className="p-3 border-t border-line flex gap-2 shrink-0" onSubmit={e => { e.preventDefault(); ask(input); }}>
          <label htmlFor="agent-input" className="sr-only">Question</label>
          <textarea id="agent-input" ref={inputRef} rows={2} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input); } }}
            placeholder="chno kayn f gold daba? · Pourquoi pas de trade ?" dir="auto"
            className="flex-1 resize-none rounded-lg bg-surface-2 border border-line px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-gold-500/60" />
          <button type="submit" disabled={busy || !input.trim()} className="h-auto px-4 rounded-lg bg-gold-gradient text-ink-strong disabled:opacity-40" aria-label="Send">
            <Send className="w-4 h-4" />
          </button>
        </form>
      </section>
    </div>
  );
};
