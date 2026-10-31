import { apiFetch, setToken } from '../api';
import React, { useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useAnimationControls, useReducedMotion } from 'motion/react';
import { AlertCircle, ArrowRight, Check, CheckCircle2, Eye, EyeOff, IdCard, KeyRound, Languages, Lock, ShieldCheck, User, UserPlus, X } from 'lucide-react';
import { Language } from '../types';
import type { AppUser } from './AccountView';

interface LoginScreenProps {
  onLoginSuccess: (user: AppUser, token: string) => void;
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

export function LoginScreen({ onLoginSuccess, lang, setLang }: LoginScreenProps) {
  const isAr = lang === 'ar';
  const li = isAr ? 2 : lang === 'fr' ? 1 : 0;
  const t = (en: string, fr: string, ar: string) => [en, fr, ar][li];
  const reduce = useReducedMotion();
  const card = useAnimationControls();
  const codeRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [first, setFirst] = useState('');
  const [last, setLast] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [welcome, setWelcome] = useState('');

  const rules = useMemo(() => passwordRules(accessCode, username), [accessCode, username]);
  const strength = rules.filter(r => r.ok).length;
  const strong = strength === rules.length;

  const switchMode = (m: Mode) => { setMode(m); setPhase('idle'); setError(null); setConfirm(''); };

  const fail = async (msg: string) => {
    setError(msg);
    setPhase('error');
    if (!reduce) await card.start({ x: [0, -12, 11, -8, 6, -3, 0], transition: { duration: 0.45, ease: 'easeOut' } });
  };

  const done = (data: { token: string; user: AppUser }) => {
    setToken(data.token);
    setWelcome(data.user?.firstName || data.user?.username || username.trim());
    setPhase('success');
    // Let the success animation play, then open the desk (or the waiting page of a new account)
    setTimeout(() => onLoginSuccess(data.user, data.token), reduce ? 150 : 1100);
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
    if (!/^[a-zA-Z0-9._-]{3,32}$/.test(username.trim())) {
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
  const inputCls = (invalid: boolean, icon = true) =>
    `w-full ${icon ? 'ps-11' : 'ps-4'} pe-4 h-12 rounded-2xl text-sm border outline-none transition-[border-color,box-shadow,background-color] duration-200 bg-canvas/60 text-white placeholder:text-slate-600 focus:ring-4 ${
      invalid ? 'border-rose-500/70 focus:border-rose-400 focus:ring-rose-500/15' : 'border-line-2 focus:border-gold-500 focus:ring-gold-500/15'
    }`;
  const label = 'block text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500 mb-1.5';

  return (
    <div className="relative min-h-dvh flex items-center justify-center p-4 sm:p-6 pt-[calc(env(safe-area-inset-top,0px)+16px)] pb-[calc(env(safe-area-inset-bottom,0px)+16px)] px-safe bg-canvas text-slate-100 overflow-hidden" dir={isAr ? 'rtl' : 'ltr'}>
      {/* Ambient background: warm gold glow + the emblem's faint geometry (static) */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[12%] -translate-x-1/2 w-[720px] h-[720px] max-w-[150vw] rounded-full bg-gold-500/[0.08] blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-[520px] h-[520px] rounded-full bg-gold-700/[0.10] blur-3xl" />
        <svg className="absolute inset-0 w-full h-full opacity-[0.06]" preserveAspectRatio="xMidYMid slice" viewBox="0 0 800 800">
          <g fill="none" stroke="#D6AE57" strokeWidth="0.8">
            <polygon points="400,90 668,245 668,555 400,710 132,555 132,245" />
            <polygon points="400,170 598,285 598,515 400,630 202,515 202,285" />
            <path d="M400 90 L400 710 M132 245 L668 555 M668 245 L132 555" />
          </g>
        </svg>
      </div>

      {setLang && (
        <div style={{ top: 'calc(env(safe-area-inset-top, 0px) + 12px)' }} className="absolute end-4 flex items-center gap-1 rounded-2xl border border-white/[0.06] bg-surface-2/80 backdrop-blur-xl p-1" role="radiogroup" aria-label={t('Language', 'Langue', 'اللغة')}>
          <Languages className="w-4 h-4 text-gold-500 mx-1.5" aria-hidden="true" />
          {(['fr', 'en', 'ar'] as const).map(c => (
            <button key={c} role="radio" aria-checked={lang === c} onClick={() => setLang(c)}
              className={`h-8 px-2.5 rounded-xl text-xs font-mono font-semibold uppercase cursor-pointer transition-colors ${lang === c ? 'bg-gold-500/15 text-gold-200' : 'text-zinc-400 hover:text-white'}`}>{c}</button>
          ))}
        </div>
      )}

      <motion.div className="relative w-full max-w-[460px]" initial={reduce ? false : { opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.55, ease: EASE }}>
        <motion.div animate={card} layout={!reduce}
          className={`relative rounded-[32px] border bg-gradient-to-b from-surface-2 to-surface p-6 sm:p-8 shadow-[0_40px_90px_-30px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.05)] transition-colors duration-300 ${
            bad ? 'border-rose-500/40' : phase === 'success' ? 'border-emerald-500/40' : 'border-white/[0.07]'}`}>
          <div aria-hidden="true" className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-gold-400/70 to-transparent" />

          {/* Brand card, the same as the sidebar's */}
          <motion.div className="flex items-center gap-3.5" initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE, delay: reduce ? 0 : 0.1 }}>
            <span className="relative shrink-0">
              <span aria-hidden="true" className={`absolute -inset-2.5 rounded-full blur-xl transition-colors duration-500 ${phase === 'success' ? 'bg-emerald-400/30' : bad ? 'bg-rose-500/25' : 'bg-gold-500/25'}`} />
              <img src="/brand/emblem-192.webp" alt="" width={56} height={56} className="relative w-14 h-14 rounded-full ring-2 ring-gold-500/30 object-cover" />
            </span>
            <span className="min-w-0 leading-tight">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">{t('Private desk', 'Desk privé', 'المكتب الخاص')}</span>
              <span className="block mt-0.5 text-lg font-bold text-white">
                Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span>
              </span>
            </span>
          </motion.div>

          <AnimatePresence mode="wait">
            {phase === 'success' ? (
              <motion.div key="ok" role="status" aria-live="polite" className="mt-8 flex flex-col items-center text-center py-6"
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.35, ease: EASE }}>
                <motion.div initial={reduce ? false : { scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 320, damping: 18 }}
                  className="w-16 h-16 rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/40 flex items-center justify-center">
                  <CheckCircle2 className="w-9 h-9 text-emerald-400" aria-hidden="true" />
                </motion.div>
                <p className="mt-4 text-base font-semibold text-white">
                  {mode === 'signup' ? t('Account created', 'Compte créé', 'تصاوب الحساب') : `${t('Welcome', 'Bienvenue', 'مرحبا')} ${welcome}`}
                </p>
                <p className="mt-1 text-xs text-slate-400">{mode === 'signup' ? t('Sending it to the admin for approval…', 'Envoi à l’admin pour validation…', 'كيتصيفط للأدمين باش يفاليديه…') : t('Opening your desk…', 'Ouverture de votre desk…', 'كيتحل المكتب ديالك…')}</p>
                <div className="mt-4 h-1 w-40 rounded-full bg-surface-3 overflow-hidden" aria-hidden="true">
                  <motion.div className="h-full bg-gradient-to-r from-gold-400 to-emerald-400" initial={{ width: 0 }} animate={{ width: '100%' }} transition={{ duration: reduce ? 0.1 : 1, ease: 'easeInOut' }} />
                </div>
              </motion.div>
            ) : (
              <motion.div key="forms" initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.4, ease: EASE, delay: reduce ? 0 : 0.2 }}>
                {/* Sign in / create account */}
                <div role="tablist" aria-label={t('Account', 'Compte', 'الحساب')} className="mt-7 grid grid-cols-2 p-1 rounded-2xl bg-canvas/60 border border-line">
                  {([['login', t('Sign in', 'Se connecter', 'دخول'), KeyRound], ['signup', t('Create account', 'Créer un compte', 'حساب جديد'), UserPlus]] as const).map(([m, l, Icon]) => (
                    <button key={m} role="tab" aria-selected={mode === m} type="button" onClick={() => switchMode(m)}
                      className={`relative h-10 rounded-xl text-[13px] font-semibold cursor-pointer transition-colors ${mode === m ? 'text-white' : 'text-zinc-400 hover:text-zinc-200'}`}>
                      {mode === m && <motion.span layoutId="auth-tab" transition={{ duration: reduce ? 0 : 0.25, ease: EASE }} className="absolute inset-0 rounded-xl bg-white/[0.07] ring-1 ring-inset ring-white/[0.08]" />}
                      <span className="relative inline-flex items-center gap-2"><Icon className={`w-4 h-4 ${mode === m ? 'text-gold-400' : ''}`} aria-hidden="true" />{l}</span>
                    </button>
                  ))}
                </div>

                <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-4">
                  <AnimatePresence initial={false}>
                    {mode === 'signup' && (
                      <motion.div key="names" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: reduce ? 0 : 0.25, ease: EASE }} className="overflow-hidden">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label htmlFor="su-first" className={label}>{t('First name', 'Prénom', 'الاسم')}</label>
                            <input id="su-first" autoComplete="given-name" value={first} maxLength={64} onChange={e => { setFirst(e.target.value); clear(); }} placeholder={t('Salma', 'Salma', 'سلمى')} className={inputCls(false, false)} />
                          </div>
                          <div>
                            <label htmlFor="su-last" className={label}>{t('Last name', 'Nom', 'النسب')}</label>
                            <input id="su-last" autoComplete="family-name" value={last} maxLength={64} onChange={e => { setLast(e.target.value); clear(); }} placeholder={t('El Amrani', 'El Amrani', 'العمراني')} className={inputCls(false, false)} />
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div>
                    <label htmlFor="login-username" className={label}>{t('Username', 'Identifiant', 'اسم المستخدم')}</label>
                    <div className="relative">
                      <User className="w-4 h-4 text-gold-500 absolute start-4 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                      <input id="login-username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus maxLength={32}
                        value={username} onChange={e => { setUsername(e.target.value); clear(); }}
                        aria-invalid={bad && mode === 'login'} aria-describedby={bad ? 'login-error' : undefined}
                        placeholder={mode === 'signup' ? t('e.g. salma.trader', 'ex. salma.trader', 'مثلا salma.trader') : t('your username', 'votre identifiant', 'اسم المستخدم ديالك')} className={inputCls(bad && mode === 'login')} />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="login-access" className={label}>{mode === 'signup' ? t('Password', 'Mot de passe', 'كلمة السر') : t('Password or access code', 'Mot de passe ou code d’accès', 'كلمة السر أو الكود')}</label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-gold-500 absolute start-4 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                      <input ref={codeRef} id="login-access" type={showCode ? 'text' : 'password'} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} spellCheck={false} maxLength={128}
                        value={accessCode} onChange={e => { setAccessCode(e.target.value); clear(); }}
                        onKeyUp={e => setCapsLock(e.getModifierState?.('CapsLock') ?? false)}
                        aria-invalid={bad && mode === 'login'} aria-describedby={mode === 'signup' ? 'pw-rules' : bad ? 'login-error' : undefined}
                        placeholder="••••••••••" className={`${inputCls(bad && mode === 'login')} font-mono tracking-wider pe-12`} />
                      <button type="button" onClick={() => setShowCode(v => !v)} aria-label={showCode ? t('Hide the password', 'Masquer le mot de passe', 'خبي كلمة السر') : t('Show the password', 'Afficher le mot de passe', 'بين كلمة السر')}
                        className="absolute end-1.5 top-1/2 -translate-y-1/2 w-10 h-10 rounded-xl flex items-center justify-center text-slate-400 hover:text-gold-300 cursor-pointer transition-colors duration-150">
                        {showCode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {capsLock && <p className="mt-1.5 text-[11px] text-amber-300">{t('Caps Lock is on', 'Verr. Maj activé', 'Caps Lock مشعل')}</p>}

                    {mode === 'signup' && (
                      <div id="pw-rules" className="mt-2.5">
                        <div className="flex gap-1" aria-hidden="true">
                          {rules.map((_, i) => (
                            <span key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${i < strength ? (strong ? 'bg-emerald-400' : strength >= 4 ? 'bg-gold-400' : 'bg-rose-400') : 'bg-surface-3'}`} />
                          ))}
                        </div>
                        <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1" aria-label={t('Password rules', 'Règles du mot de passe', 'شروط كلمة السر')}>
                          {rules.map(r => (
                            <li key={r.key} className={`flex items-center gap-1.5 text-[11px] transition-colors ${r.ok ? 'text-emerald-300' : 'text-zinc-500'}`}>
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
                      <motion.div key="confirm" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: reduce ? 0 : 0.25, ease: EASE }} className="overflow-hidden">
                        <label htmlFor="su-confirm" className={label}>{t('Confirm the password', 'Confirmer le mot de passe', 'عاود كلمة السر')}</label>
                        <div className="relative">
                          <ShieldCheck className={`w-4 h-4 absolute start-4 top-1/2 -translate-y-1/2 pointer-events-none ${confirm && confirm === accessCode ? 'text-emerald-400' : 'text-gold-500'}`} aria-hidden="true" />
                          <input id="su-confirm" type={showCode ? 'text' : 'password'} autoComplete="new-password" spellCheck={false} maxLength={128}
                            value={confirm} onChange={e => { setConfirm(e.target.value); clear(); }} placeholder="••••••••••"
                            aria-invalid={!!confirm && confirm !== accessCode} className={`${inputCls(!!confirm && confirm !== accessCode)} font-mono tracking-wider`} />
                        </div>
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

                  <motion.button type="submit" disabled={phase === 'loading'} whileTap={reduce ? undefined : { scale: 0.985 }}
                    className="w-full h-12 px-5 rounded-2xl font-bold text-sm text-ink-strong bg-gradient-to-b from-gold-300 to-gold-600 shadow-[0_14px_34px_-12px_rgba(214,174,87,0.85)] hover:brightness-110 flex items-center justify-center gap-2 disabled:opacity-70 cursor-pointer transition">
                    {phase === 'loading' ? (
                      <>
                        <span className="w-5 h-5 border-2 border-ink-strong/25 border-t-ink-strong rounded-full animate-spin" aria-hidden="true" />
                        <span>{mode === 'signup' ? t('Creating…', 'Création…', 'كيتصاوب…') : t('Checking…', 'Vérification…', 'كنتحقق…')}</span>
                      </>
                    ) : mode === 'signup' ? (
                      <><UserPlus className="w-4 h-4" aria-hidden="true" /><span>{t('Create my account', 'Créer mon compte', 'صاوب الحساب ديالي')}</span></>
                    ) : (
                      <><span>{t('Enter the desk', 'Entrer dans le desk', 'دخول للمكتب')}</span><ArrowRight className={`w-4 h-4 ${isAr ? 'rotate-180' : ''}`} aria-hidden="true" /></>
                    )}
                  </motion.button>
                </form>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-6 rounded-2xl border border-white/[0.05] bg-white/[0.02] px-4 py-3 flex items-start gap-2.5 text-[11px] leading-relaxed text-slate-400">
            {mode === 'signup' ? <IdCard className="w-4 h-4 shrink-0 text-gold-500 mt-px" aria-hidden="true" /> : <Lock className="w-4 h-4 shrink-0 text-gold-500 mt-px" aria-hidden="true" />}
            <span>{mode === 'signup'
              ? t('New accounts are checked by the admin before they can see the signals. You can sign in now and will be let in as soon as it is approved.',
                'Chaque nouveau compte est vérifié par l’admin avant d’accéder aux signaux. Vous pouvez vous connecter tout de suite, l’accès s’ouvre dès la validation.',
                'كل حساب جديد كيراجعو الأدمين قبل ما يشوف الإشارات. تقدر تدخل دابا، والدخول كيتحل غير يتفاليدا.')
              : t('Passwords and access codes are stored hashed, never in clear.', 'Mots de passe et codes d’accès stockés chiffrés (hash), jamais en clair.', 'كلمات السر والكودات محفوظة مشفرة، عمرها ما كتبان.')}</span>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
