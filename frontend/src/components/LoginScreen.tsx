import { apiFetch, setToken } from '../api';
import React, { useRef, useState } from 'react';
import { AnimatePresence, motion, useAnimationControls, useReducedMotion } from 'motion/react';
import { AlertCircle, ArrowRight, CheckCircle2, Eye, EyeOff, KeyRound, Lock, User } from 'lucide-react';
import { Language } from '../types';
import type { AppUser } from './AccountView';

interface LoginScreenProps {
  onLoginSuccess: (user: AppUser, token: string) => void;
  lang: Language;
  theme: 'light' | 'dark';
}

const EASE = [0.22, 1, 0.36, 1] as const;
type Phase = 'idle' | 'loading' | 'error' | 'success';

export function LoginScreen({ onLoginSuccess, lang }: LoginScreenProps) {
  const isAr = lang === 'ar';
  const t = (en: string, fr: string, ar: string) => (isAr ? ar : lang === 'fr' ? fr : en);
  const reduce = useReducedMotion();
  const card = useAnimationControls();
  const codeRef = useRef<HTMLInputElement>(null);

  const [username, setUsername] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [welcome, setWelcome] = useState('');

  const fail = async (msg: string) => {
    setError(msg);
    setPhase('error');
    if (!reduce) await card.start({ x: [0, -12, 11, -8, 6, -3, 0], transition: { duration: 0.45, ease: 'easeOut' } });
    codeRef.current?.focus();
    codeRef.current?.select();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (phase === 'loading' || phase === 'success') return;
    if (!username.trim() || !accessCode.trim()) {
      fail(t('Enter your username and your access code.', 'Saisissez votre identifiant et votre code d’accès.', 'دخل اسم المستخدم وكود الدخول.'));
      return;
    }
    setPhase('loading');
    setError(null);
    try {
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), accessCode: accessCode.trim() }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setToken(data.token);
        setWelcome(data.user?.username || username.trim());
        setPhase('success');
        // Let the success animation play, then open the desk
        setTimeout(() => onLoginSuccess(data.user, data.token), reduce ? 150 : 1100);
      } else {
        fail(res.status === 401
          ? t('Wrong username or access code.', 'Identifiant ou code d’accès incorrect.', 'اسم المستخدم أو الكود غلط.')
          : data.error || data.detail || t('Login refused.', 'Connexion refusée.', 'تم رفض الدخول.'));
      }
    } catch {
      // Free hosting puts the API to sleep when idle: the first request can take ~30-60 s
      fail(t('Server unreachable. If it was asleep, try again in a minute.', 'Serveur injoignable. S’il était en veille, réessayez dans une minute.', 'السيرفر ما جاوبش. إلا كان ناعس، عاود من بعد دقيقة.'));
    }
  };

  const bad = phase === 'error';
  const inputCls = (invalid: boolean) =>
    `w-full ps-11 pe-4 py-3.5 rounded-xl text-sm border outline-none transition-[border-color,box-shadow,background-color] duration-200 bg-surface-2/80 text-white placeholder:text-slate-600 focus:ring-4 ${
      invalid ? 'border-rose-500/70 focus:border-rose-400 focus:ring-rose-500/15' : 'border-line-2 focus:border-gold-500 focus:ring-gold-500/15'
    }`;

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 sm:p-6 bg-canvas text-slate-100 overflow-hidden" dir={isAr ? 'rtl' : 'ltr'}>
      {/* Ambient background: gold glow + the emblem's faint geometry (static) */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[18%] -translate-x-1/2 w-[640px] h-[640px] max-w-[140vw] rounded-full bg-gold-500/[0.07] blur-3xl" />
        <svg className="absolute inset-0 w-full h-full opacity-[0.07]" preserveAspectRatio="xMidYMid slice" viewBox="0 0 800 800">
          <g fill="none" stroke="#D6AE57" strokeWidth="0.8">
            <polygon points="400,90 668,245 668,555 400,710 132,555 132,245" />
            <polygon points="400,170 598,285 598,515 400,630 202,515 202,285" />
            <path d="M400 90 L400 710 M132 245 L668 555 M668 245 L132 555" />
          </g>
        </svg>
      </div>

      <motion.div className="relative w-full max-w-md" initial={reduce ? false : { opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.55, ease: EASE }}>
        <motion.div animate={card}
          className={`relative rounded-3xl border bg-surface/90 backdrop-blur-xl p-6 sm:p-9 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)] transition-colors duration-300 ${
            bad ? 'border-rose-500/40' : phase === 'success' ? 'border-emerald-500/40' : 'border-line'}`}>
          <div aria-hidden="true" className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-gold-400/70 to-transparent" />

          {/* Logo */}
          <div className="flex flex-col items-center text-center">
            <motion.div className="relative" initial={reduce ? false : { opacity: 0, scale: 0.85, rotate: -4 }} animate={{ opacity: 1, scale: phase === 'success' ? 1.06 : 1, rotate: 0 }}
              transition={{ duration: 0.6, ease: EASE, delay: reduce ? 0 : 0.1 }}>
              <div aria-hidden="true" className={`absolute -inset-4 rounded-[30%] blur-2xl transition-colors duration-500 ${phase === 'success' ? 'bg-emerald-400/25' : bad ? 'bg-rose-500/20' : 'bg-gold-500/20'}`} />
              <img src="/brand/emblem-512.webp" alt="LiquidityDissection" width={112} height={112} className="relative w-24 h-24 sm:w-28 sm:h-28 rounded-[24%] ring-1 ring-gold-500/30 object-cover" />
            </motion.div>
            <motion.div initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE, delay: reduce ? 0 : 0.22 }}>
              <h1 className="mt-5 text-xl sm:text-2xl font-black uppercase tracking-[0.16em] text-white">
                Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span>
              </h1>
              <p className="mt-1 text-xs font-mono font-semibold uppercase tracking-[0.32em] text-gold-500">- Private Desk -</p>
            </motion.div>
          </div>

          <AnimatePresence mode="wait">
            {phase === 'success' ? (
              <motion.div key="ok" role="status" aria-live="polite" className="mt-8 flex flex-col items-center text-center py-6"
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.35, ease: EASE }}>
                <motion.div initial={reduce ? false : { scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 320, damping: 18 }}
                  className="w-16 h-16 rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/40 flex items-center justify-center">
                  <CheckCircle2 className="w-9 h-9 text-emerald-400" aria-hidden="true" />
                </motion.div>
                <p className="mt-4 text-base font-semibold text-white">{t('Welcome', 'Bienvenue', 'مرحبا')} {welcome}</p>
                <p className="mt-1 text-xs text-slate-400">{t('Opening your desk…', 'Ouverture de votre desk…', 'كيتحل المكتب ديالك…')}</p>
                <div className="mt-4 h-1 w-40 rounded-full bg-surface-3 overflow-hidden" aria-hidden="true">
                  <motion.div className="h-full bg-gradient-to-r from-gold-400 to-emerald-400" initial={{ width: 0 }} animate={{ width: '100%' }} transition={{ duration: reduce ? 0.1 : 1, ease: 'easeInOut' }} />
                </div>
              </motion.div>
            ) : (
              <motion.form key="form" onSubmit={handleSubmit} noValidate className="mt-8 space-y-4"
                initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.4, ease: EASE, delay: reduce ? 0 : 0.3 }}>
                <div>
                  <label htmlFor="login-username" className="block text-xs font-semibold text-slate-300 mb-1.5">{t('Username', 'Identifiant', 'اسم المستخدم')}</label>
                  <div className="relative">
                    <User className="w-4 h-4 text-gold-500 absolute start-4 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                    <input id="login-username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus
                      value={username} onChange={e => { setUsername(e.target.value); if (bad) setPhase('idle'); }}
                      aria-invalid={bad} aria-describedby={bad ? 'login-error' : undefined}
                      placeholder={t('your username', 'votre identifiant', 'اسم المستخدم ديالك')} className={inputCls(bad)} />
                  </div>
                </div>

                <div>
                  <label htmlFor="login-access" className="block text-xs font-semibold text-slate-300 mb-1.5">{t('Access code', 'Code d’accès', 'كود الدخول')}</label>
                  <div className="relative">
                    <KeyRound className="w-4 h-4 text-gold-500 absolute start-4 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                    <input ref={codeRef} id="login-access" type={showCode ? 'text' : 'password'} autoComplete="current-password" spellCheck={false}
                      value={accessCode} onChange={e => { setAccessCode(e.target.value); if (bad) setPhase('idle'); }}
                      onKeyUp={e => setCapsLock(e.getModifierState?.('CapsLock') ?? false)}
                      aria-invalid={bad} aria-describedby={bad ? 'login-error' : undefined}
                      placeholder="••••••••" className={`${inputCls(bad)} font-mono tracking-wider pe-12`} />
                    <button type="button" onClick={() => setShowCode(v => !v)} aria-label={showCode ? t('Hide the code', 'Masquer le code', 'خبي الكود') : t('Show the code', 'Afficher le code', 'بين الكود')}
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 w-10 h-10 rounded-lg flex items-center justify-center text-slate-400 hover:text-gold-300 cursor-pointer transition-colors duration-150">
                      {showCode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {capsLock && <p className="mt-1.5 text-[11px] text-amber-300">{t('Caps Lock is on', 'Verr. Maj activé', 'Caps Lock مشعل')}</p>}
                </div>

                <AnimatePresence>
                  {error && bad && (
                    <motion.p id="login-error" role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                      className="flex items-center gap-2 text-xs text-rose-300 overflow-hidden">
                      <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />{error}
                    </motion.p>
                  )}
                </AnimatePresence>

                <motion.button type="submit" disabled={phase === 'loading'} whileTap={reduce ? undefined : { scale: 0.985 }}
                  className="w-full min-h-[52px] px-5 rounded-xl font-semibold text-sm text-ink-strong bg-gold-gradient bg-gold-gradient-hover shadow-lg shadow-gold-500/20 flex items-center justify-center gap-2 disabled:opacity-70 cursor-pointer transition-[filter,box-shadow] duration-200 hover:shadow-gold-500/35">
                  {phase === 'loading' ? (
                    <>
                      <span className="w-5 h-5 border-2 border-ink-strong/25 border-t-ink-strong rounded-full animate-spin" aria-hidden="true" />
                      <span>{t('Checking…', 'Vérification…', 'كنتحقق…')}</span>
                    </>
                  ) : (
                    <>
                      <span>{t('Enter the desk', 'Entrer dans le desk', 'دخول للمكتب')}</span>
                      <ArrowRight className={`w-4 h-4 ${isAr ? 'rotate-180' : ''}`} aria-hidden="true" />
                    </>
                  )}
                </motion.button>
              </motion.form>
            )}
          </AnimatePresence>

          <p className="mt-6 flex items-center justify-center gap-1.5 text-[11px] text-slate-500">
            <Lock className="w-3 h-3 text-gold-500" aria-hidden="true" />
            {t('Accounts are created by the admin · access codes are stored hashed', 'Comptes créés par l’admin · codes stockés chiffrés (hash)', 'الحسابات كيديرها الأدمين · الكودات محفوظة مشفرة')}
          </p>
        </motion.div>
      </motion.div>
    </div>
  );
}
