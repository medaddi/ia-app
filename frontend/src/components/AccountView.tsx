import React, { useEffect, useState } from 'react';
import { Bell, KeyRound, Send, UserRound } from 'lucide-react';
import { apiJson } from '../api';
import { disableNotifications, enableNotifications, needsInstall, notifyEnabled, notifyPermission, notifySupported, testPush } from '../notifications';
import type { Language } from '../types';
import { Button, Card, Field, Notice, fmtDate, inputCls, tr } from './ui';
import { ImportCard, RiskCard } from './RiskSizing';

/** My account: who I am, the Telegram link, the notifications of this device and my password. No trades: they are being rebuilt. */
export interface AppUser {
  id: number; username: string; role: 'admin' | 'user'; telegramChatId?: string | null; telegramLinked?: boolean; telegramName?: string | null;
  active?: boolean; lastLoginAt?: string | null; createdAt?: string;
  firstName?: string | null; lastName?: string | null; status?: 'approved' | 'pending';  // self sign-ups wait for an admin
}

interface AccountViewProps {
  lang: Language;
  theme?: 'light' | 'dark';
  user: AppUser;
  onUserChange: (u: AppUser) => void;
}

function TelegramLinkCard({ isLight, lang, user, onUserChange }: { isLight: boolean; lang: Language; user: AppUser; onUserChange: (u: AppUser) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [bot, setBot] = useState<{ bot: string | null; link: string | null } | null>(null);
  useEffect(() => { if (!user.telegramLinked) apiJson('/api/telegram/bot').then(setBot).catch(() => setBot(null)); }, [user.telegramLinked]);
  const steps = [
    t('Open the bot', 'Ouvrez le bot', 'حل البوت'),
    t('Press Start: it sends you an invitation link', 'Appuyez sur Démarrer : il vous envoie un lien d’invitation', 'ضغط Start: كيصيفط ليك رابط دعوة'),
    t('The link opens the app: tap Accept', 'Le lien ouvre l’app : touchez Accepter', 'الرابط كيحل التطبيق: ضغط قبول'),
  ];
  return (
    <Card isLight={isLight} icon={<Send className="w-4 h-4" />} title={t('Telegram bot', 'Bot Telegram', 'بوت تيليغرام')}
      right={user.telegramLinked ? <span className="text-xs font-semibold text-emerald-500">● {user.telegramName || t('Linked', 'Lié', 'مربوط')}</span> : undefined}>
      {user.telegramLinked ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <p className="text-slate-400">{t('This Telegram is linked to your account.', 'Ce Telegram est lié à votre compte.', 'هاد التيليغرام مربوط بالحساب ديالك.')} {t('One Telegram per account.', 'Un Telegram par compte.', 'تيليغرام واحد لكل حساب.')}</p>
          <Button variant="ghost" onClick={async () => { const r = await apiJson<{ user: AppUser }>('/api/me/telegram-link', { method: 'DELETE' }); onUserChange(r.user); }}>
            {t('Unlink', 'Délier', 'فك الربط')}
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-4">
          <ol className="space-y-1.5 text-xs text-slate-300">
            {steps.map((st, k) => (
              <li key={k} className="flex items-center gap-2"><span className="w-5 h-5 shrink-0 rounded-full bg-gold-500/15 text-gold-300 font-semibold flex items-center justify-center text-[11px]">{k + 1}</span>{st}</li>
            ))}
          </ol>
          {bot?.link
            ? <a href={bot.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-ink-strong bg-gold-gradient cursor-pointer"><Send className="w-3.5 h-3.5" />{t('Open the bot', 'Ouvrir le bot', 'حل البوت')} @{bot.bot}</a>
            : <span className="text-xs text-slate-500">{t('The bot is not set up yet', 'Le bot n’est pas encore configuré', 'البوت مازال ما تعدل')}</span>}
        </div>
      )}
    </Card>
  );
}

function NotificationsCard({ isLight, lang }: { isLight: boolean; lang: Language }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [on, setOn] = useState(notifyEnabled());
  const [note, setNote] = useState<{ kind: 'ok' | 'error' | 'info'; text: string } | null>(null);
  useEffect(() => { const f = () => setOn(notifyEnabled()); window.addEventListener('ld-notify-change', f); return () => window.removeEventListener('ld-notify-change', f); }, []);
  const blocked = notifyPermission() === 'denied';
  return (
    <Card isLight={isLight} icon={<Bell className="w-4 h-4" />} title={t('Notifications', 'Notifications', 'الإشعارات')}
      right={on ? <span className="text-xs font-semibold text-emerald-500">● {t('On', 'Activées', 'مفعلة')}</span> : undefined}>
      {!notifySupported() ? <p className="text-xs text-slate-400">{t('This browser has no notifications.', 'Ce navigateur n’a pas de notifications.', 'هاد المتصفح ما فيهش الإشعارات.')}</p>
        : needsInstall() ? <p className="text-xs text-slate-400">{t('On iPhone, add the app to the home screen first.', 'Sur iPhone, ajoutez d’abord l’app à l’écran d’accueil.', 'ف الآيفون، زيد التطبيق للشاشة الرئيسية الأول.')}</p>
        : (
          <div className="flex flex-wrap items-center gap-2">
            {on ? (
              <>
                <Button variant="ghost" onClick={async () => setNote((await testPush()) ? { kind: 'ok', text: t('Test sent.', 'Test envoyé.', 'التجربة تصيفطات.') } : { kind: 'error', text: t('The test did not reach this device.', 'Le test n’est pas arrivé.', 'التجربة ما وصلاتش.') })}>
                  {t('Send a test', 'Envoyer un test', 'صيفط تجربة')}
                </Button>
                <Button variant="ghost" onClick={async () => { await disableNotifications(); setOn(false); }}>{t('Turn off', 'Désactiver', 'وقف')}</Button>
              </>
            ) : (
              <Button disabled={blocked} onClick={async () => setOn(await enableNotifications())}>{t('Turn on', 'Activer', 'فعل')}</Button>
            )}
            {blocked && <span className="text-xs text-amber-300">{t('Blocked in the browser settings.', 'Bloquées dans les réglages du navigateur.', 'محبوسين ف إعدادات المتصفح.')}</span>}
          </div>
        )}
      {note && <div className="mt-2"><Notice kind={note.kind}>{note.text}</Notice></div>}
    </Card>
  );
}

export const AccountView: React.FC<AccountViewProps> = ({ lang, theme = 'dark', user, onUserChange }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const full = [user.firstName, user.lastName].filter(Boolean).join(' ');

  const savePassword = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await apiJson<{ user: AppUser }>('/api/me', { method: 'PUT', body: JSON.stringify({ accessCode: code }) });
      onUserChange(r.user);
      setCode('');
      setMsg({ kind: 'ok', text: t('Password changed.', 'Mot de passe changé.', 'كلمة السر تبدلات.') });
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      <Card isLight={isLight} icon={<UserRound className="w-4 h-4" />} title={t('My account', 'Mon compte', 'حسابي')}>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <dt className="text-slate-500">{t('Username', 'Identifiant', 'اسم المستخدم')}</dt><dd className="font-mono text-slate-200">{user.username}</dd>
          {full && <><dt className="text-slate-500">{t('Name', 'Nom', 'الاسم')}</dt><dd className="text-slate-200">{full}</dd></>}
          <dt className="text-slate-500">{t('Role', 'Rôle', 'الدور')}</dt><dd className="text-slate-200">{user.role === 'admin' ? t('Admin', 'Admin', 'مسؤول') : t('Member', 'Membre', 'عضو')}</dd>
          {user.createdAt && <><dt className="text-slate-500">{t('Since', 'Depuis', 'من')}</dt><dd className="font-mono text-slate-300">{fmtDate(user.createdAt)}</dd></>}
        </dl>
      </Card>
      <RiskCard isLight={isLight} lang={lang} />
      <ImportCard isLight={isLight} lang={lang} />
      <TelegramLinkCard isLight={isLight} lang={lang} user={user} onUserChange={onUserChange} />
      <NotificationsCard isLight={isLight} lang={lang} />
      <Card isLight={isLight} icon={<KeyRound className="w-4 h-4" />} title={t('Password', 'Mot de passe', 'كلمة السر')}>
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t('New password', 'Nouveau mot de passe', 'كلمة سر جديدة')}>
            <input type="password" autoComplete="new-password" value={code} onChange={e => setCode(e.target.value)} className={inputCls(isLight)} minLength={6} />
          </Field>
          <Button disabled={busy || code.length < 6} onClick={savePassword}>{t('Change', 'Changer', 'بدل')}</Button>
        </div>
        {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      </Card>
    </div>
  );
};
