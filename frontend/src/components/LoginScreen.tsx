import { apiFetch, setToken } from '../api';
import React, { useState } from 'react';
import { ShieldCheck, Lock, User, Key, ArrowRight, Sparkles, CheckCircle2, AlertCircle, Building2, Terminal } from 'lucide-react';
import { Language } from '../types';
import { LiquidityDissectionLogo } from './LiquidityDissectionLogo';
import type { AppUser } from './AccountView';

interface LoginScreenProps {
  onLoginSuccess: (user: AppUser, token: string) => void;
  lang: Language;
  theme: 'light' | 'dark';
}

export function LoginScreen({ onLoginSuccess, lang, theme }: LoginScreenProps) {
  const isAr = lang === 'ar';
  const isLight = theme === 'light';

  const [username, setUsername] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !accessCode.trim()) {
      setErrorMessage(isAr ? 'يرجى إدخال اسم المشغل ومفتاح الترخيص الخاص' : 'Please enter operator username and Private Desk access key');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.trim(),
          accessCode: accessCode.trim(),
        }),
      });

      const data = await res.json();

      if (res.ok && data.success) {
        setToken(data.token);
        onLoginSuccess(data.user, data.token);
      } else {
        setErrorMessage(data.detail || data.message || (isAr ? 'بيانات الدخول غير صحيحة أو ترخيص غير مفعّل' : 'Invalid credentials or inactive VIP license key'));
      }
    } catch (err: any) {
      // Free hosting puts the API to sleep when idle: the first request can take ~30-60 s
      setErrorMessage(isAr ? 'تعذر الاتصال بالخادم. إذا كان في وضع السكون، أعد المحاولة بعد دقيقة.' : 'Server unreachable. If it was asleep, try again in a minute.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className={`min-h-screen flex items-center justify-center p-4 sm:p-6 transition-colors duration-300 ${
        isLight
          ? 'bg-paper text-ink-strong'
          : 'bg-canvas text-slate-100'
      }`}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      <div className="w-full max-w-lg">
        {/* Desk Header Container */}
        <div
          className={`rounded-2xl border p-6 sm:p-10 relative overflow-hidden transition-colors duration-300 ${
            isLight
              ? 'bg-white border-paper-line-2 shadow-xl shadow-gold-500/10'
              : 'bg-surface border-line shadow-[var(--shadow-float)]'
          }`}
        >
          {/* Subtle Champagne Gold Ambient Glows */}
          <div aria-hidden="true" className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold-400/60 to-transparent pointer-events-none" />
          <div aria-hidden="true" className="absolute -top-24 left-1/2 -translate-x-1/2 w-72 h-48 bg-gold-500/10 rounded-full blur-3xl pointer-events-none" />

          {/* Institutional Top Bar Badge */}
          <div className="flex items-center justify-between pb-6 mb-6 border-b border-paper-line-2 dark:border-line">
            <div className="flex items-center gap-2">
              <span aria-hidden="true" className="w-2 h-2 rounded-full bg-emerald-500 ring-4 ring-emerald-500/15" />
              <span className="text-xs font-semibold uppercase tracking-[0.14em] font-mono text-gold-700 dark:text-gold-400">
                INSTITUTIONAL GATEWAY
              </span>
            </div>
            <div className="text-xs font-mono font-bold text-slate-400">
              v2.5 • SMC FLOW
            </div>
          </div>

          {/* Logo & Headline */}
          <div className="flex flex-col items-center text-center mb-8 relative z-10">
            <LiquidityDissectionLogo size="xl" layout="vertical" withText={true} className="mb-2" />
            <p className="text-xs text-zinc-400 mt-2 max-w-sm leading-relaxed">
              {isAr
                ? 'منصة تفكيك السيولة المؤسساتية (Smart Money Concepts) وتوجيه الصفقات المباشرة'
                : 'Smart Money Concepts & Order Flow Execution Desk for Accredited Desks'}
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
            {/* Username field */}
            <div>
              <label htmlFor="login-username" className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-gold-500" />
                <span>{isAr ? 'مشغل الحساب (Operator ID / Username)' : 'Operator Username / ID'}</span>
              </label>
              <div className="relative">
                <input
                  id="login-username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={isAr ? 'مثال: admin أو trader' : 'e.g. admin or trader'}
                  className={`w-full px-4 py-3.5 rounded-xl text-sm font-medium border outline-none transition focus:ring-4 focus:ring-gold-500/15 ${
                    isLight
                      ? 'bg-paper border-paper-line-2 text-ink-strong focus:bg-white focus:border-gold-500'
                      : 'bg-surface-2 border-line-2 text-white placeholder:text-slate-600 focus:border-gold-500'
                  }`}
                  required
                />
              </div>
            </div>

            {/* Access Code field */}
            <div>
              <label htmlFor="login-access" className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-gold-500" />
                <span>{isAr ? 'كود الدخول الحصري (Private Desk Pass)' : 'Private Desk Access Pass'}</span>
              </label>
              <div className="relative">
                <input
                  id="login-access"
                  type="password"
                  autoComplete="current-password"
                  spellCheck={false}
                  value={accessCode}
                  onChange={(e) => setAccessCode(e.target.value)}
                  placeholder="••••••••"
                  className={`w-full px-4 py-3.5 rounded-xl text-sm font-mono font-bold tracking-wider uppercase border outline-none transition focus:ring-2 focus:ring-gold-500/40 ${
                    isLight
                      ? 'bg-paper border-paper-line-2 text-ink-strong focus:bg-white focus:border-gold-500'
                      : 'bg-surface-2 border-line-2 text-white placeholder:text-slate-600 focus:border-gold-500'
                  }`}
                  required
                />
              </div>
            </div>

            {/* Error banner */}
            {errorMessage && (
              <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full min-h-[52px] py-3.5 px-5 rounded-xl font-semibold text-sm text-ink-strong bg-gold-gradient bg-gold-gradient-hover active:scale-[0.99] transition shadow-lg shadow-gold-500/20 flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-ink-strong/25 border-t-ink-strong rounded-full animate-spin" />
              ) : (
                <>
                  <span>
                    {isAr ? 'فتح منصة تفكيك السيولة' : 'Enter Private Trading Desk'}
                  </span>
                  <ArrowRight className={`w-4 h-4 ${isAr ? 'rotate-180' : ''}`} />
                </>
              )}
            </button>
          </form>

          {/* Security Guarantee */}
          <div className="mt-6 text-center">
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-400 font-medium">
              <Lock className="w-3 h-3 text-gold-500" />
              <span>{isAr ? 'تشفير آمن للبيانات ومعايير حماية مؤسساتية' : 'End-to-End Encrypted Session & Local DB Storage'}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
