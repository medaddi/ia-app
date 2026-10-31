import React, { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Check, Clock, LogOut, RefreshCw, UserCheck } from 'lucide-react';
import { apiFetch } from '../api';
import type { Language } from '../types';
import type { AppUser } from './AccountView';

const CHECK_MS = 20000;  // the page asks every 20 s whether the admin approved the account

/** What a self-signed-up account sees until an admin approves it: the steps left, and it opens by itself once approved. */
export function PendingApproval({ user, lang, onApproved, onLogout }: { user: AppUser; lang: Language; onApproved: (u: AppUser) => void; onLogout: () => void }) {
  const li = lang === 'ar' ? 2 : lang === 'fr' ? 1 : 0;
  const t = (en: string, fr: string, ar: string) => [en, fr, ar][li];
  const reduce = useReducedMotion();
  const [checking, setChecking] = useState(false);
  const [lastCheck, setLastCheck] = useState<number>(Date.now());

  const check = async () => {
    setChecking(true);
    try {
      const res = await apiFetch('/api/auth/me');
      if (res.ok) {
        const u = (await res.json()).user as AppUser;
        if (u.status !== 'pending') onApproved(u);
      } else if (res.status === 401) onLogout();  // refused: the account was deleted
    } catch { /* offline: next check retries */ }
    setChecking(false);
    setLastCheck(Date.now());
  };
  useEffect(() => {
    const id = setInterval(() => { if (!document.hidden) check(); }, CHECK_MS);
    const onVisible = () => { if (!document.hidden) check(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  const name = [user.firstName, user.lastName].filter(Boolean).join(' ') || user.username;
  const steps = [
    { done: true, title: t('Account created', 'Compte créé', 'الحساب تصاوب'), text: `@${user.username}` },
    { done: false, now: true, title: t('Review by the admin', 'Vérification par l’admin', 'المراجعة عند الأدمين'), text: t('Your request is in the admin’s list. Nothing to do on your side.', 'Votre demande est dans la liste de l’admin. Rien à faire de votre côté.', 'الطلب ديالك عند الأدمين. ما خاصك دير والو.') },
    { done: false, title: t('Access to the desk', 'Accès au desk', 'الدخول للمكتب'), text: t('This page opens the app by itself as soon as it is approved.', 'Cette page ouvre l’app d’elle-même dès la validation.', 'هاد الصفحة غادي تحل التطبيق بوحدها غير يتفاليدا.') },
  ];

  return (
    <div className="relative min-h-dvh flex items-center justify-center p-4 sm:p-6 bg-canvas text-slate-100 overflow-hidden" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-[12%] -translate-x-1/2 w-[720px] h-[720px] max-w-[150vw] rounded-full bg-gold-500/[0.07] blur-3xl" />
      <motion.section initial={reduce ? false : { opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-[480px] rounded-[32px] border border-white/[0.07] bg-gradient-to-b from-surface-2 to-surface p-6 sm:p-8 shadow-[0_40px_90px_-30px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.05)]"
        aria-labelledby="pending-title">
        <div aria-hidden="true" className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-gold-400/70 to-transparent" />
        <div className="flex items-center gap-3.5">
          <img src="/brand/emblem-192.webp" alt="" width={56} height={56} className="w-14 h-14 rounded-full ring-2 ring-gold-500/30 object-cover" />
          <div className="min-w-0 leading-tight">
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">{t('Private desk', 'Desk privé', 'المكتب الخاص')}</div>
            <div className="mt-0.5 text-lg font-bold text-white">Liquidity <span className="bg-gradient-to-r from-[#F9E5B6] via-gold-400 to-gold-600 bg-clip-text text-transparent">Dissection</span></div>
          </div>
        </div>

        <div className="mt-7 flex flex-col items-center text-center">
          <span className="relative w-16 h-16 rounded-full bg-gold-500/10 ring-1 ring-gold-500/30 flex items-center justify-center">
            {!reduce && <span className="absolute inset-0 rounded-full ring-2 ring-gold-400/40 animate-ping" aria-hidden="true" />}
            <Clock className="w-8 h-8 text-gold-300" aria-hidden="true" />
          </span>
          <h1 id="pending-title" className="mt-4 text-xl font-bold text-white">{t(`Almost there, ${name}`, `Presque prêt, ${name}`, `قربتي، ${name}`)}</h1>
          <p className="mt-1.5 text-sm text-slate-400">{t('Your account is waiting for the admin’s approval.', 'Votre compte attend la validation de l’admin.', 'الحساب ديالك كيتسنى الموافقة ديال الأدمين.')}</p>
        </div>

        <ol className="mt-7 space-y-0">
          {steps.map((s, i) => (
            <li key={i} className="relative flex gap-3.5 pb-5 last:pb-0">
              {i < steps.length - 1 && <span className="absolute start-[15px] top-8 bottom-0 w-px bg-line-2" aria-hidden="true" />}
              <span className={`relative shrink-0 w-8 h-8 rounded-full flex items-center justify-center ring-1 ${s.done ? 'bg-emerald-500/15 ring-emerald-500/40 text-emerald-300' : s.now ? 'bg-gold-500/15 ring-gold-500/40 text-gold-300' : 'bg-surface-3 ring-line-2 text-zinc-500'}`}>
                {s.done ? <Check className="w-4 h-4" aria-hidden="true" /> : s.now ? <UserCheck className="w-4 h-4" aria-hidden="true" /> : <span className="text-xs font-mono">{i + 1}</span>}
              </span>
              <div className="min-w-0 pt-1">
                <div className={`text-sm font-semibold ${s.now ? 'text-gold-200' : s.done ? 'text-white' : 'text-zinc-400'}`}>{s.title}</div>
                <div className="mt-0.5 text-xs text-slate-500">{s.text}</div>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-7 grid grid-cols-2 gap-2.5">
          <button onClick={check} disabled={checking}
            className="h-11 rounded-2xl bg-gradient-to-b from-gold-300 to-gold-600 text-ink-strong text-sm font-bold inline-flex items-center justify-center gap-2 shadow-[0_12px_30px_-12px_rgba(214,174,87,0.85)] hover:brightness-110 cursor-pointer transition disabled:opacity-70">
            <RefreshCw className={`w-4 h-4 ${checking ? 'animate-spin' : ''}`} aria-hidden="true" />{t('Check now', 'Vérifier', 'تحقق دابا')}
          </button>
          <button onClick={onLogout}
            className="h-11 rounded-2xl border border-line-2 text-slate-300 text-sm font-semibold inline-flex items-center justify-center gap-2 hover:bg-white/[0.05] hover:text-rose-300 cursor-pointer transition-colors">
            <LogOut className="w-4 h-4" aria-hidden="true" />{t('Log out', 'Se déconnecter', 'خروج')}
          </button>
        </div>
        <p className="mt-3 text-center text-[11px] text-slate-500" aria-live="polite">
          {t('Checked automatically every 20 s · last check', 'Vérifié automatiquement toutes les 20 s · dernier contrôle', 'كيتحقق بوحدو كل 20 ثانية · آخر تحقق')} {new Date(lastCheck).toLocaleTimeString(lang === 'ar' ? 'ar-MA' : lang === 'fr' ? 'fr-FR' : 'en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </p>
      </motion.section>
    </div>
  );
}
