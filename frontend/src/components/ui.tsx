import React from 'react';
import { Language } from '../types';

/** Small shared building blocks in the app's token palette (index.css). */

export const tr = (lang: Language, en: string, fr: string, ar: string) => (lang === 'ar' ? ar : lang === 'fr' ? fr : en);

export function Card({ isLight, title, icon, right, children, className = '' }: {
  isLight: boolean; title?: React.ReactNode; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-2xl border p-4 sm:p-5 ${isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'} ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 mb-4">
          <h3 className={`flex items-center gap-2 text-sm font-semibold ${isLight ? 'text-ink-strong' : 'text-white'}`}>
            {icon && <span className={`icon-tile w-8 h-8 ${isLight ? 'text-gold-600' : 'text-gold-400'}`}>{icon}</span>}
            {title}
          </h3>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ isLight, label, value, tone }: { isLight: boolean; label: string; value: React.ReactNode; tone?: 'good' | 'bad' | 'gold' }) {
  const color = tone === 'good' ? 'text-emerald-500' : tone === 'bad' ? 'text-rose-500' : tone === 'gold' ? 'text-gold-500' : isLight ? 'text-ink-strong' : 'text-white';
  return (
    <div className={`rounded-xl border px-3 py-2.5 ${isLight ? 'bg-paper border-paper-line' : 'bg-surface border-line'}`}>
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-base font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

export const inputCls = (isLight: boolean) =>
  `w-full px-3 py-2 rounded-lg text-sm border outline-none transition focus:ring-2 focus:ring-gold-500/40 ${
    isLight ? 'bg-paper border-paper-line-2 text-ink-strong focus:border-gold-500' : 'bg-surface border-line-2 text-white placeholder:text-slate-600 focus:border-gold-500'
  }`;

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-500 mb-1">{label}</span>
      {children}
    </label>
  );
}

export function Button({ variant = 'gold', className = '', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'gold' | 'ghost' | 'danger' }) {
  const v = variant === 'gold'
    ? 'text-ink-strong bg-gold-gradient bg-gold-gradient-hover shadow-sm shadow-gold-500/20'
    : variant === 'danger'
      ? 'text-rose-500 border border-rose-500/30 hover:bg-rose-500/10'
      : 'text-slate-400 border border-line-2 hover:text-gold-400 hover:border-gold-500/50';
  return <button {...props} className={`inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-50 cursor-pointer ${v} ${className}`} />;
}

export function Notice({ kind, children }: { kind: 'ok' | 'error' | 'info'; children: React.ReactNode }) {
  const c = kind === 'ok' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500' : kind === 'error' ? 'bg-rose-500/10 border-rose-500/30 text-rose-500' : 'bg-sky-500/10 border-sky-500/30 text-sky-400';
  return <div role={kind === 'error' ? 'alert' : 'status'} className={`px-3 py-2 rounded-lg border text-xs ${c}`}>{children}</div>;
}

export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v}%`);
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);
export const fmtR = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v}R`);
export const fmtDate = (iso: string | null | undefined) => (iso ? new Date(iso).toISOString().slice(0, 16).replace('T', ' ') : '—');
