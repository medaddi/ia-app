import { apiFetch, setSessionExpiry, setToken } from '../api';
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useAnimationControls, useReducedMotion } from 'motion/react';
import { AlertCircle, ArrowRight, Check, Clock, Eye, EyeOff, Languages, Lock, User, UserPlus, X } from 'lucide-react';
import { Language } from '../types';
import type { AppUser } from './AccountView';

interface LoginScreenProps {
  onLoginSuccess: (user: AppUser, token: string) => void;
  sessionEnded?: boolean;  // came back here because the one-hour login ended
  lang: Language;
  setLang?: (lang: Language) => void;
  theme: 'light' | 'dark';
}

const EASE = [0.22, 1, 0.36, 1] as const;
type Phase = 'idle' | 'loading' | 'error' | 'success';
type Mode = 'login' | 'signup';

/** The sign-up password rules (the server checks the same ones). */
function passwordRules(p: string, username: string) {
  const u = username.trim().toLowerCase();
  return [
    { key: 'len', ok: p.length >= 10, label: ['10+ characters', '10 caractères ou plus', '10 حروف أو أكثر'] },
    { key: 'lower', ok: /[a-z]/.test(p), label: ['a lowercase letter', 'une minuscule', 'حرف صغير'] },
    { key: 'upper', ok: /[A-Z]/.test(p), label: ['an uppercase letter', 'une majuscule', 'حرف كبير'] },
    { key: 'digit', ok: /\d/.test(p), label: ['a digit', 'un chiffre', 'رقم'] },
    { key: 'symbol', ok: /[^A-Za-z0-9]/.test(p) && !/\s/.test(p), label: ['a symbol, no space', 'un symbole, sans espace', 'رمز، بلا فراغ'] },
    { key: 'user', ok: !p || u.length < 3 || !p.toLowerCase().includes(u), label: ['not your username', 'pas votre identifiant', 'ماشي اسم المستخدم'] },
  ] as const;
}

/** An underline field: label above, icon on the right that turns into a tick once the value is valid. */
function Field({ id, label, value, onChange, valid, invalid, icon, type = 'text', autoComplete, placeholder, inputRef, right, autoFocus, maxLength }: {
  id: string; label: string; value: string; onChange: (v: string) => void; valid: boolean; invalid?: boolean; icon: React.ReactNode;
  type?: string; autoComplete?: string; placeholder?: string; inputRef?: React.Ref<HTMLInputElement>; right?: React.ReactNode; autoFocus?: boolean; maxLength?: number;
}) {
  const ok = valid && !invalid;  // a refused login takes the ticks away
  return (
    <div className="group">
      <label htmlFor={id} className="block text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500 group-focus-within:text-gold-300 transition-colors">{label}</label>
      <div className={`relative flex items-center border-b transition-colors duration-300 ${invalid ? 'border-rose-400/70' : ok ? 'border-gold-400/70' : 'border-white/15 group-focus-within:border-gold-400'}`}>
        <input id={id} ref={inputRef} type={type} value={value} onChange={e => onChange(e.target.value)} autoComplete={autoComplete} placeholder={placeholder}
          autoCapitalize="none" spellCheck={false} autoFocus={autoFocus} maxLength={maxLength} aria-invalid={invalid}
          className="peer w-full h-11 bg-transparent text-[15px] text-white placeholder:text-zinc-600 outline-none pe-16 tracking-wide" />
        <span className="absolute end-0 flex items-center gap-1.5">
          {right}
          <span className="relative w-5 h-5 flex items-center justify-center">
            <AnimatePresence initial={false} mode="wait">
              {ok ? (
                <motion.span key="ok" initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0 }} transition={{ type: 'spring', stiffness: 420, damping: 18 }}
                  className="w-5 h-5 rounded-full bg-gold-400 text-ink-strong flex items-center justify-center"><Check className="w-3 h-3" strokeWidth={3} /></motion.span>
              ) : (
                <motion.span key="ic" initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }} transition={{ duration: 0.15 }}
                  className="text-zinc-500 group-focus-within:text-gold-300">{icon}</motion.span>
              )}
            </AnimatePresence>
          </span>
        </span>
      </div>
    </div>
  );
}

export function LoginScreen({ onLoginSuccess, sessionEnded = false, lang, setLang }: LoginScreenProps) {
  const isAr = lang === 'ar';
  const li = isAr ? 2 : lang === 'fr' ? 1 : 0;
  const t = (en: string, fr: string, ar: string) => [en, fr, ar][li];
  const reduce = useReducedMotion();
  const form = useAnimationControls();
  const codeRef = useRef<HTMLInputElement>(null);

  // Intro: only the emblem and the name, in the middle of the page; after 2 s they move up and the login form appears
  const INTRO_MS = 2000;
  const brandRef = useRef<HTMLDivElement>(null);
  const [centre, setCentre] = useState<number | null>(null);  // how far down the brand sits from its place to reach the middle
  const [opened, setOpened] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  useLayoutEffect(() => {
    const r = brandRef.current?.getBoundingClientRect();
    if (r) setCentre(window.innerHeight / 2 - (r.top + r.height / 2));
  }, []);
  useEffect(() => { if (opened) return; const id = setTimeout(() => setOpened(true), INTRO_MS); return () => clearTimeout(id); }, []);


  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [first, setFirst] = useState('');
  const [last, setLast] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);

  const rules = useMemo(() => passwordRules(accessCode, username), [accessCode, username]);
  const strength = rules.filter(r => r.ok).length;
  const strong = strength === rules.length;
  const userOk = /^[a-zA-Z0-9._-]{3,32}$/.test(username.trim());
  const nameOk = (v: string) => v.trim().length >= 1 && /^[\p{L}][\p{L} '\-]*$/u.test(v.trim());

  const switchMode = (m: Mode) => { setMode(m); setPhase('idle'); setError(null); setConfirm(''); };

  const fail = async (msg: string) => {
    setError(msg);
    setPhase('error');
    if (!reduce) await form.start({ x: [0, -12, 11, -8, 6, -3, 0], transition: { duration: 0.45, ease: 'easeOut' } });
  };

  const done = (data: { token: string; expiresAt?: string; user: AppUser }) => {
    setToken(data.token);
    setSessionExpiry(data.expiresAt ?? null);
    setPhase('success');
    // The spinner grows into the page, then the desk (or the waiting page of a new account) opens
    setTimeout(() => onLoginSuccess(data.user, data.token), reduce ? 150 : 900);
  };

  const call = async (path: string, body: object) => {
    setPhase('loading');
    setError(null);
    try {
      const res = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      return { res, data };
    } catch {
      // Free hosting puts the API to sleep when idle: the first request can take ~30-60 s
      fail(t('Server unreachable. If it was asleep, try again in a minute.', 'Serveur injoignable. S’il était en veille, réessayez dans une minute.', 'السيرفر ما جاوبش. إلا كان ناعس، عاود من بعد دقيقة.'));
      return null;
    }
  };

  const submitLogin = async () => {
    if (!username.trim() || !accessCode.trim()) {
      fail(t('Enter your username and your password.', 'Saisissez votre identifiant et votre mot de passe.', 'دخل اسم المستخدم وكلمة السر.'));
      return;
    }
    const out = await call('/api/auth/login', { username: username.trim(), accessCode: accessCode.trim() });
    if (!out) return;
    if (out.res.ok && out.data.success) done(out.data);
    else {
      await fail(out.res.status === 401
        ? t('Wrong username or password.', 'Identifiant ou mot de passe incorrect.', 'اسم المستخدم أو كلمة السر غلط.')
        : out.data.error || out.data.detail || t('Login refused.', 'Connexion refusée.', 'تم رفض الدخول.'));
      codeRef.current?.focus();
      codeRef.current?.select();
    }
  };

  const submitSignup = async () => {
    if (!first.trim() || !last.trim() || !username.trim()) {
      fail(t('Fill in your first name, last name and username.', 'Renseignez prénom, nom et identifiant.', 'عمر الاسم، النسب واسم المستخدم.'));
      return;
    }
    if (!userOk) {
      fail(t('Username: 3 to 32 letters, digits, dot, dash or underscore.', 'Identifiant : 3 à 32 lettres, chiffres, point, tiret ou underscore.', 'اسم المستخدم: من 3 حتى 32 حرف، أرقام، نقطة، - أو _.'));
      return;
    }
    if (!strong) {
      fail(t('The password does not meet every rule below.', 'Le mot de passe ne respecte pas toutes les règles ci-dessous.', 'كلمة السر ما فيهاش كاع الشروط لي لتحت.'));
      return;
    }
    if (confirm !== accessCode) {
      fail(t('The two passwords differ.', 'Les deux mots de passe sont différents.', 'جوج كلمات السر ماشي بحال بحال.'));
      return;
    }
    const out = await call('/api/auth/register', { firstName: first.trim(), lastName: last.trim(), username: username.trim(), password: accessCode });
    if (!out) return;
    if (out.res.ok && out.data.success) done(out.data);
    else fail(out.res.status === 409 ? t('This username is taken.', 'Cet identifiant est déjà pris.', 'اسم المستخدم هذا محجوز.')
      : out.data.error || out.data.detail || t('Sign-up refused.', 'Inscription refusée.', 'تم رفض التسجيل.'));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (phase === 'loading' || phase === 'success') return;
    (mode === 'login' ? submitLogin : submitSignup)();
  };

  const bad = phase === 'error';
  const clear = () => { if (bad) setPhase('idle'); };
  const busy = phase === 'loading' || phase === 'success';
  const pwValid = mode === 'login' ? accessCode.length >= 6 : strong;

  return (
    <div className="app-screen overflow-x-hidden overflow-y-auto overscroll-contain bg-canvas text-slate-100" dir={isAr ? 'rtl' : 'ltr'}>
      {/* Moving gold-on-black gradient: the page "breathes" slowly, like the reference */}
      <div aria-hidden="true" className="login-gradient absolute inset-0" />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="login-orb absolute -top-32 -left-24 w-[520px] h-[520px] rounded-full bg-gold-500/[0.14] blur-3xl" />
        <div className="login-orb-2 absolute -bottom-40 -right-24 w-[560px] h-[560px] rounded-full bg-gold-700/[0.16] blur-3xl" />
      </div>

      {/* Success: the spinner grows into a gold wash that opens the desk */}
      <AnimatePresence>
        {phase === 'success' && !reduce && (
          <motion.div aria-hidden="true" className="absolute inset-0 z-30 bg-gradient-to-b from-gold-400/90 to-gold-700/90"
            initial={{ clipPath: 'circle(0% at 50% 70%)' }} animate={{ clipPath: 'circle(150% at 50% 70%)' }} transition={{ duration: 0.8, ease: EASE }} />
        )}
      </AnimatePresence>

      {setLang && (
        <div style={{ top: 'calc(env(safe-area-inset-top, 0px) + 12px)' }} className={`absolute z-10 end-4 flex items-center gap-1 rounded-2xl border border-white/[0.06] bg-black/30 backdrop-blur-xl p-1 transition-opacity duration-500 ${opened ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} role="radiogroup" aria-label={t('Language', 'Langue', 'اللغة')}>
          <Languages className="w-4 h-4 text-gold-500 mx-1.5" aria-hidden="true" />
          {(['fr', 'en', 'ar'] as const).map(c => (
            <button key={c} role="radio" aria-checked={lang === c} onClick={() => setLang(c)}
              className={`h-8 px-2.5 rounded-xl text-xs font-mono font-semibold uppercase cursor-pointer transition-colors ${lang === c ? 'bg-gold-500/15 text-gold-200' : 'text-zinc-400 hover:text-white'}`}>{c}</button>
          ))}
        </div>
      )}

      <div className="relative z-10 min-h-full flex flex-col items-center justify-center px-6 pt-[calc(env(safe-area-inset-top,0px)+56px)] pb-[calc(env(safe-area-inset-bottom,0px)+24px)]">
        <div className="w-full max-w-[380px]">
          {/* Emblem and name: alone in the middle first, then they move up to their place above the form */}
          <div ref={brandRef} className={`${opened ? 'intro-brand' : ''} flex flex-col items-center text-center`}
            style={{ transform: opened || centre === null ? 'none' : `translateY(${centre}px) scale(1.18)`, visibility: centre === null && !opened ? 'hidden' : 'visible' }}>
            <span className="relative intro-pop">
              <span aria-hidden="true" className={`intro-glow absolute -inset-3 rounded-full blur-xl transition-colors duration-500 ${bad ? 'bg-rose-500/25' : 'bg-gold-500/25'}`} />
              <img src="/brand/emblem-192.webp" alt="LiquidityDissection" width={76} height={76} className="relative w-[76px] h-[76px] rounded-full ring-2 ring-gold-500/40 object-cover" />
            </span>
            <h1 className="intro-rise mt-4 text-xl font-bold tracking-wide text-white" style={{ animationDelay: '0.45s' }}>
              Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span>
            </h1>
            <p className="intro-rise mt-0.5 text-[10px] font-semibold uppercase tracking-[0.32em] text-gold-500/90" style={{ animationDelay: '0.7s' }}>{t('Private desk', 'Desk privé', 'المكتب الخاص')}</p>
          </div>

          {opened && sessionEnded && mode === 'login' && (
            <motion.p initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} role="status"
              className="mt-6 flex items-center justify-center gap-2 text-xs text-gold-200">
              <Clock className="w-4 h-4" aria-hidden="true" />{t('Your session ended: sign in again.', 'Votre session a pris fin : reconnectez-vous.', 'السيشن سالات: دخل من جديد.')}
            </motion.p>
          )}

          <motion.form animate={form} onSubmit={handleSubmit} noValidate className={`intro-form mt-8 space-y-6 ${opened ? 'is-open' : 'pointer-events-none'}`} aria-hidden={!opened}>
            <AnimatePresence initial={false}>
              {mode === 'signup' && (
                <motion.div key="names" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: reduce ? 0 : 0.3, ease: EASE }} className="overflow-hidden">
                  <div className="grid grid-cols-2 gap-5 pb-1">
                    <Field id="su-first" label={t('First name', 'Prénom', 'الاسم')} value={first} onChange={v => { setFirst(v); clear(); }} valid={nameOk(first)} icon={<User className="w-4 h-4" />} autoComplete="given-name" maxLength={64} />
                    <Field id="su-last" label={t('Last name', 'Nom', 'النسب')} value={last} onChange={v => { setLast(v); clear(); }} valid={nameOk(last)} icon={<User className="w-4 h-4" />} autoComplete="family-name" maxLength={64} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <Field id="login-username" label={t('Username', 'Identifiant', 'اسم المستخدم')} value={username} onChange={v => { setUsername(v); clear(); }} valid={userOk} invalid={bad && mode === 'login'}
              icon={<User className="w-4 h-4" />} autoComplete="username" autoFocus maxLength={32} placeholder={mode === 'signup' ? 'salma.trader' : ''} />

            <div>
              <Field id="login-access" label={mode === 'signup' ? t('Password', 'Mot de passe', 'كلمة السر') : t('Password or access code', 'Mot de passe ou code', 'كلمة السر أو الكود')}
                value={accessCode} onChange={v => { setAccessCode(v); clear(); }} valid={pwValid} invalid={bad && mode === 'login'} inputRef={codeRef}
                icon={<Lock className="w-4 h-4" />} type={showCode ? 'text' : 'password'} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} maxLength={128}
                right={<button type="button" onClick={() => setShowCode(v => !v)} aria-label={showCode ? t('Hide the password', 'Masquer le mot de passe', 'خبي كلمة السر') : t('Show the password', 'Afficher le mot de passe', 'بين كلمة السر')}
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-500 hover:text-gold-300 cursor-pointer">{showCode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>} />
              {mode === 'signup' && (
                <div className="mt-3">
                  <div className="flex gap-1" aria-hidden="true">
                    {rules.map((_, i) => <span key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${i < strength ? (strong ? 'bg-gold-300' : strength >= 4 ? 'bg-gold-500' : 'bg-rose-400') : 'bg-white/10'}`} />)}
                  </div>
                  <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1" aria-label={t('Password rules', 'Règles du mot de passe', 'شروط كلمة السر')}>
                    {rules.map(r => (
                      <li key={r.key} className={`flex items-center gap-1.5 text-[11px] transition-colors ${r.ok ? 'text-gold-200' : 'text-zinc-500'}`}>
                        {r.ok ? <Check className="w-3.5 h-3.5 shrink-0" aria-hidden="true" /> : <X className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />}
                        <span>{r.label[li]}</span><span className="sr-only">{r.ok ? t('done', 'ok', 'محقق') : t('missing', 'manquant', 'ناقص')}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <AnimatePresence initial={false}>
              {mode === 'signup' && (
                <motion.div key="confirm" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: reduce ? 0 : 0.3, ease: EASE }} className="overflow-hidden">
                  <Field id="su-confirm" label={t('Confirm the password', 'Confirmer le mot de passe', 'عاود كلمة السر')} value={confirm} onChange={v => { setConfirm(v); clear(); }}
                    valid={!!confirm && confirm === accessCode && strong} invalid={!!confirm && confirm !== accessCode} icon={<Lock className="w-4 h-4" />}
                    type={showCode ? 'text' : 'password'} autoComplete="new-password" maxLength={128} />
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {error && bad && (
                <motion.p id="login-error" role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-2 text-xs text-rose-300 overflow-hidden">
                  <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />{error}
                </motion.p>
              )}
            </AnimatePresence>

            {/* The button shrinks into a spinning circle while the server checks, like the reference */}
            <div className="flex justify-center pt-2">
              <motion.button type="submit" disabled={busy} aria-busy={busy}
                animate={{ width: busy ? 52 : '100%', borderRadius: 999 }} transition={{ duration: reduce ? 0 : 0.4, ease: EASE }}
                whileTap={busy || reduce ? undefined : { scale: 0.98 }}
                className="h-[52px] max-w-full overflow-hidden bg-gradient-to-b from-gold-300 to-gold-600 text-ink-strong font-bold text-sm shadow-[0_16px_40px_-14px_rgba(214,174,87,0.9)] flex items-center justify-center gap-2 cursor-pointer disabled:cursor-default">
                <AnimatePresence mode="wait" initial={false}>
                  {busy ? (
                    <motion.span key="spin" initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                      className="w-6 h-6 rounded-full border-[3px] border-ink-strong/25 border-t-ink-strong animate-spin" aria-label={t('Checking…', 'Vérification…', 'كنتحقق…')} />
                  ) : (
                    <motion.span key="txt" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-2 whitespace-nowrap px-6">
                      {mode === 'signup' ? <><UserPlus className="w-4 h-4" aria-hidden="true" />{t('Create my account', 'Créer mon compte', 'صاوب الحساب ديالي')}</>
                        : <>{t('Sign in', 'Se connecter', 'دخول')}<ArrowRight className={`w-4 h-4 ${isAr ? 'rotate-180' : ''}`} aria-hidden="true" /></>}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            </div>

            <div className="text-center">
              <button type="button" onClick={() => switchMode(mode === 'login' ? 'signup' : 'login')} disabled={busy}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-gold-200 cursor-pointer transition-colors">
                {mode === 'login' ? t('New account', 'Nouveau compte', 'حساب جديد') : t('I already have an account', 'J’ai déjà un compte', 'عندي حساب')}
                <ArrowRight className={`w-3.5 h-3.5 ${isAr ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
              {mode === 'signup' && (
                <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">{t('New accounts are approved by the admin before they see the signals.', 'Chaque nouveau compte est validé par l’admin avant d’accéder aux signaux.', 'كل حساب جديد كيوافق عليه الأدمين قبل ما يشوف الإشارات.')}</p>
              )}
            </div>
          </motion.form>
        </div>
      </div>
    </div>
  );
}
