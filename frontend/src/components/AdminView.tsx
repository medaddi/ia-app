import React, { useEffect, useState } from 'react';
import { ArrowLeft, Settings2, ShieldCheck, UserPlus, Users } from 'lucide-react';
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
          right={<span className="text-xs text-slate-500">{detail.user.role} · {t('daily loss limit', 'perte jour max', 'الخسارة اليومية')} {detail.user.dailyLossLimit ? fmtMoney(detail.user.dailyLossLimit) : '—'}</span>}>
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
            <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className={inputCls(isLight)}><option value="user">user</option><option value="admin">admin</option></select>
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
              t('Last login', 'Connexion', 'آخر دخول'), t('New code', 'Nouveau code', 'رمز جديد'), ''].map(h => <th key={h} className="px-1.5 py-1.5 font-medium whitespace-nowrap">{h}</th>)}
          </tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className={`border-t ${isLight ? 'border-paper-line' : 'border-line'} ${u.active === false ? 'opacity-40' : ''}`}>
                <td className="px-1.5 py-1.5 whitespace-nowrap">
                  <button onClick={() => run(async () => setDetail(await apiJson(`/api/users/${u.id}`)))} className="font-semibold text-gold-500 hover:underline cursor-pointer">{u.username}</button>
                  <span className="ms-1 text-slate-500">{u.role}</span>
                </td>
                <td className="px-1.5 py-1.5 font-mono">{u.stats.total} ({u.stats.open})</td>
                <td className="px-1.5 py-1.5 font-mono">{u.stats.totalLots.toFixed(2)}</td>
                <td className="px-1.5 py-1.5 font-mono">{fmtPct(u.stats.winRate)}</td>
                <td className={`px-1.5 py-1.5 font-mono ${u.stats.totalPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>{fmtMoney(u.stats.totalPnl)}</td>
                <td className={`px-1.5 py-1.5 font-mono whitespace-nowrap ${u.today.reached ? 'text-rose-500' : ''}`}>
                  {fmtMoney(u.today.pnl)}{u.today.limit ? ` / -${fmtMoney(u.today.limit)}` : ''}{u.today.reached ? ' ⛔' : ''}
                </td>
                <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(u.lastLoginAt)}</td>
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
          {t('Each user records the lot they took on every signal; their P&L, win rate and daily loss limit are their own. Click a name to see that user’s statistics and history.',
            'Chaque utilisateur indique le lot pris sur chaque signal ; son P&L, son taux de réussite et sa perte journalière max lui sont propres. Cliquez un nom pour voir ses statistiques.',
            'كل مستخدم كيدخل اللوت لي دخل بيه فكل صفقة، والأرباح ونسبة النجاح والخسارة اليومية ديالو بوحدو. اضغط على الاسم لرؤية الإحصائيات ديالو.')}
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
