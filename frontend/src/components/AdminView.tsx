import React, { useEffect, useState } from 'react';
import { ArrowLeft, Check, Copy, Send, Settings2, ShieldCheck, UserPlus, Users } from 'lucide-react';
import { apiJson } from '../api';
import { Language } from '../types';
import type { AppUser, Stats, Today, Trade } from './AccountView';
import { StatsGrid, TradesTable } from './AccountView';
import { Button, Card, Field, Notice, fmtDate, fmtMoney, fmtPct, inputCls, tr } from './ui';

interface UserRow extends AppUser {
  createdAt: string;
  stats: { total: number; open: number; closed: number; wins: number; losses: number; winRate: number | null; totalPnl: number; totalLots: number };
  today: Today;
}

interface AdminViewProps {
  lang: Language;
  theme?: 'light' | 'dark';
  me: AppUser;
}

const NEW_USER = { username: '', accessCode: '', role: 'user' };

/** Admin page: creates and manages accounts. Each user records their own trades and lots and has their own statistics. */
export const AdminView: React.FC<AdminViewProps> = ({ lang, theme = 'dark', me }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [form, setForm] = useState(NEW_USER);
  const [codes, setCodes] = useState<Record<number, string>>({});
  // Telegram link codes made by the admin, per user (valid 24 h, one use)
  const [tgCodes, setTgCodes] = useState<Record<number, { code: string; expiresAt: number; deepLink: string | null }>>({});
  const [copied, setCopied] = useState<number | null>(null);
  const roleLabel = (r: string) => (r === 'admin' ? t('Admin', 'Admin', 'مدير') : t('Trader', 'Trader', 'متداول'));
  const [detail, setDetail] = useState<{ user: AppUser; stats: Stats; trades: Trade[] } | null>(null);
  const [appSettings, setAppSettings] = useState<{ app: any } | null>(null);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<string | void>) => {
    setBusy(true);
    setMsg(null);
    try {
      const text = await fn();
      if (text) setMsg({ kind: 'ok', text });
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const load = async () => {
    try {
      const [u, s] = await Promise.all([apiJson<{ users: UserRow[] }>('/api/users'), apiJson('/api/settings')]);
      setUsers(u.users);
      setAppSettings(s);
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  useEffect(() => { load(); }, []);

  if (detail) {
    return (
      <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
        <Button variant="ghost" onClick={() => setDetail(null)}><ArrowLeft className="w-3.5 h-3.5" />{t('All users', 'Tous les utilisateurs', 'كل المستخدمين')}</Button>
        <Card isLight={isLight} icon={<Users className="w-4 h-4" />} title={detail.user.username}
          right={<span className="text-xs text-slate-500">{roleLabel(detail.user.role)} · {t('daily loss limit', 'perte jour max', 'الخسارة اليومية')} {detail.user.dailyLossLimit ? fmtMoney(detail.user.dailyLossLimit) : '—'}</span>}>
          <StatsGrid isLight={isLight} lang={lang} stats={detail.stats} />
        </Card>
        <Card isLight={isLight} title={`${t('Trades', 'Trades', 'الصفقات')} (${detail.trades.length})`}>
          <TradesTable isLight={isLight} lang={lang} trades={detail.trades} />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      <Card isLight={isLight} icon={<UserPlus className="w-4 h-4" />} title={t('New account', 'Nouveau compte', 'حساب جديد')}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
          <Field label={t('Username', "Nom d'utilisateur", 'اسم المستخدم')}><input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} className={inputCls(isLight)} /></Field>
          <Field label={t('Access code (min 6)', "Code d'accès (min 6)", 'رمز الدخول (6 على الأقل)')}><input value={form.accessCode} onChange={e => setForm({ ...form, accessCode: e.target.value })} className={inputCls(isLight)} /></Field>
          <Field label={t('Role', 'Rôle', 'الدور')}>
            <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className={inputCls(isLight)}><option value="user">{roleLabel('user')}</option><option value="admin">{roleLabel('admin')}</option></select>
          </Field>
          <Button disabled={busy || form.username.trim().length < 2 || form.accessCode.length < 6} onClick={() => run(async () => {
            await apiJson('/api/users', { method: 'POST', body: JSON.stringify(form) });
            const name = form.username;
            setForm(NEW_USER);
            await load();
            return t(`Account ${name} created. They log in with this username and access code.`, `Compte ${name} créé.`, `تم إنشاء الحساب ${name}.`);
          })}>{t('Create', 'Créer', 'إنشاء')}</Button>
        </div>
      </Card>

      <Card isLight={isLight} icon={<Users className="w-4 h-4" />} title={`${t('Accounts', 'Comptes', 'الحسابات')} (${users.length})`}>
        <div className="overflow-x-auto"><table className="w-full text-xs tabular-nums">
          <thead className="text-slate-500 text-left"><tr>
            {[t('User', 'Utilisateur', 'المستخدم'), t('Trades', 'Trades', 'الصفقات'), 'Lots', t('Win rate', 'Réussite', 'النجاح'), 'P&L', t('Today', "Aujourd'hui", 'اليوم'),
              t('Last login', 'Connexion', 'آخر دخول'), 'Telegram', t('New access code', 'Nouveau code d’accès', 'رمز دخول جديد'), ''].map(h => <th key={h} className="px-1.5 py-1.5 font-medium whitespace-nowrap">{h}</th>)}
          </tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className={`border-t ${isLight ? 'border-paper-line' : 'border-line'} ${u.active === false ? 'opacity-40' : ''}`}>
                <td className="px-1.5 py-1.5 whitespace-nowrap">
                  <button onClick={() => run(async () => setDetail(await apiJson(`/api/users/${u.id}`)))} className="font-semibold text-gold-500 hover:underline cursor-pointer">{u.username}</button>
                  <span className="ms-1 text-slate-500">{roleLabel(u.role)}</span>
                </td>
                <td className="px-1.5 py-1.5 font-mono">{u.stats.total} ({u.stats.open})</td>
                <td className="px-1.5 py-1.5 font-mono">{u.stats.totalLots.toFixed(2)}</td>
                <td className="px-1.5 py-1.5 font-mono">{fmtPct(u.stats.winRate)}</td>
                <td className={`px-1.5 py-1.5 font-mono ${u.stats.totalPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>{fmtMoney(u.stats.totalPnl)}</td>
                <td className={`px-1.5 py-1.5 font-mono whitespace-nowrap ${u.today.reached ? 'text-rose-500' : ''}`}>
                  {fmtMoney(u.today.pnl)}{u.today.limit ? ` / -${fmtMoney(u.today.limit)}` : ''}{u.today.reached ? ' ⛔' : ''}
                </td>
                <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(u.lastLoginAt)}</td>
                <td className="px-1.5 py-1 whitespace-nowrap">
                  {u.telegramLinked ? (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="text-emerald-500 font-semibold">● {t('Linked', 'Lié', 'مربوط')}</span>
                      <Button variant="ghost" className="py-1" disabled={busy} onClick={() => run(async () => {
                        await apiJson(`/api/users/${u.id}/telegram-link`, { method: 'DELETE' }); await load();
                        return t(`${u.username} unlinked from Telegram`, `${u.username} délié de Telegram`, `تم فك ربط ${u.username}`);
                      })}>{t('Unlink', 'Délier', 'فك')}</Button>
                    </span>
                  ) : tgCodes[u.id] && tgCodes[u.id].expiresAt * 1000 > Date.now() ? (
                    <span className="inline-flex items-center gap-1.5">
                      <code className={`px-2 py-1 rounded-md font-mono font-bold tracking-wider border ${isLight ? 'border-paper-line-2' : 'border-gold-500/40 text-gold-200'}`}>{tgCodes[u.id].code}</code>
                      <button aria-label={t('Copy the code', 'Copier le code', 'نسخ الكود')} className="p-1 text-slate-400 hover:text-gold-400 cursor-pointer"
                        onClick={() => navigator.clipboard?.writeText(tgCodes[u.id].code).then(() => { setCopied(u.id); setTimeout(() => setCopied(null), 1500); }).catch(() => {})}>
                        {copied === u.id ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                      {tgCodes[u.id].deepLink && (
                        <button aria-label={t('Copy the bot link', 'Copier le lien du bot', 'نسخ رابط البوت')} title={tgCodes[u.id].deepLink!} className="p-1 text-slate-400 hover:text-gold-400 cursor-pointer"
                          onClick={() => navigator.clipboard?.writeText(tgCodes[u.id].deepLink!).catch(() => {})}><Send className="w-3.5 h-3.5" /></button>
                      )}
                    </span>
                  ) : (
                    <Button variant="ghost" className="py-1" disabled={busy} onClick={() => run(async () => {
                      const r = await apiJson<{ code: string; expiresAt: number; deepLink: string | null }>(`/api/users/${u.id}/telegram-link`, { method: 'POST' });
                      setTgCodes({ ...tgCodes, [u.id]: r });
                      return t(`Code for ${u.username}: ${r.code} (24 h, one use). They send it to the bot from their Telegram.`,
                        `Code pour ${u.username} : ${r.code} (24 h, une fois). Il l’envoie au bot depuis son Telegram.`,
                        `الكود ديال ${u.username}: ${r.code} (24 ساعة، مرة وحدة). كيصيفطو للبوت من التيليغرام ديالو.`);
                    })}><Send className="w-3.5 h-3.5" />{t('Make code', 'Créer un code', 'صاوب كود')}</Button>
                  )}
                </td>
                <td className="px-1.5 py-1"><input aria-label="new access code" value={codes[u.id] ?? ''} placeholder="••••••" onChange={x => setCodes({ ...codes, [u.id]: x.target.value })} className={`${inputCls(isLight)} w-24 py-1`} /></td>
                <td className="px-1.5 py-1 whitespace-nowrap space-x-1">
                  <Button className="py-1" disabled={busy || (codes[u.id] ?? '').length < 6} onClick={() => run(async () => {
                    await apiJson(`/api/users/${u.id}`, { method: 'PATCH', body: JSON.stringify({ accessCode: codes[u.id] }) });
                    setCodes({ ...codes, [u.id]: '' });
                    return t(`New access code saved for ${u.username}`, `Nouveau code enregistré pour ${u.username}`, `تم حفظ الرمز الجديد لـ ${u.username}`);
                  })}>{t('Set code', 'Changer le code', 'تغيير الرمز')}</Button>
                  {u.id !== me.id && (
                    <>
                      <Button variant="ghost" className="py-1" disabled={busy} onClick={() => run(async () => { await apiJson(`/api/users/${u.id}`, { method: 'PATCH', body: JSON.stringify({ active: u.active === false }) }); await load(); })}>
                        {u.active === false ? t('Enable', 'Activer', 'تفعيل') : t('Disable', 'Désactiver', 'تعطيل')}
                      </Button>
                      <Button variant="danger" className="py-1" disabled={busy} onClick={() => {
                        if (window.confirm(t(`Delete ${u.username}?`, `Supprimer ${u.username} ?`, `حذف ${u.username}؟`)))
                          run(async () => { await apiJson(`/api/users/${u.id}`, { method: 'DELETE' }); await load(); });
                      }}>✕</Button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <p className="mt-3 text-xs text-slate-500">
          {t('Each user records the lot they took on every signal; their P&L, win rate and daily loss limit are their own. Click a name to see that user’s statistics and history. Telegram: make a code for a user and send it to them; the Telegram account that sends it to the bot becomes theirs and gets the signals with their own capital and risk.',
            'Chaque utilisateur indique le lot pris sur chaque signal ; son P&L, son taux de réussite et sa perte journalière max lui sont propres. Cliquez un nom pour voir ses statistiques. Telegram : créez un code pour un utilisateur et envoyez-le-lui ; le compte Telegram qui l’envoie au bot devient le sien et reçoit les signaux avec son capital et son risque.',
            'كل مستخدم كيدخل اللوت لي دخل بيه فكل صفقة، والأرباح ونسبة النجاح والخسارة اليومية ديالو بوحدو. اضغط على الاسم لرؤية الإحصائيات ديالو. تيليغرام: صاوب كود لمستخدم وصيفطو ليه؛ حساب التيليغرام لي يصيفطو للبوت كيولي ديالو وكتوصلو الإشارات على حساب الرأسمال والمخاطرة ديالو.')}
        </p>
      </Card>

      {appSettings && (
        <Card isLight={isLight} icon={<Settings2 className="w-4 h-4" />} title={t('App parameters', "Paramètres de l'app", 'إعدادات التطبيق')}>
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t('App name', "Nom de l'app", 'اسم التطبيق')}><input value={appSettings.app.appName} onChange={e => setAppSettings({ app: { ...appSettings.app, appName: e.target.value } })} className={inputCls(isLight)} /></Field>
            <Field label={t('Default language', 'Langue par défaut', 'اللغة الافتراضية')}>
              <select value={appSettings.app.defaultLanguage} onChange={e => setAppSettings({ app: { ...appSettings.app, defaultLanguage: e.target.value } })} className={inputCls(isLight)}>
                <option value="fr">Français</option><option value="en">English</option><option value="ar">العربية</option>
              </select>
            </Field>
            <Button disabled={busy} onClick={() => run(async () => {
              setAppSettings(await apiJson('/api/settings', { method: 'PUT', body: JSON.stringify(appSettings) }));
              return t('Saved', 'Enregistré', 'تم الحفظ');
            })}><ShieldCheck className="w-3.5 h-3.5" />{t('Save', 'Enregistrer', 'حفظ')}</Button>
          </div>
        </Card>
      )}
    </div>
  );
};
