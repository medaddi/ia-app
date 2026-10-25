import React, { useEffect, useMemo, useState } from 'react';
import { History, Plus, Settings2, ShieldCheck, Target, UserPlus, Users, Wallet } from 'lucide-react';
import { apiJson } from '../api';
import { AISignal, Language, MarketAsset } from '../types';
import { Button, Card, Field, Notice, Stat, fmtDate, fmtMoney, fmtPct, fmtR, inputCls, tr } from './ui';

export interface AppUser { id: number; username: string; role: 'admin' | 'user'; capital: number; riskPct: number; active?: boolean; lastLoginAt?: string | null }

interface Trade {
  id: number; symbol: string; direction: 'BUY' | 'SELL'; entry: number; sl: number; tp1: number | null; tp2: number | null; tp3: number | null;
  lots: number; capital: number; riskPct: number; riskAmount: number; status: 'OPEN' | 'CLOSED'; result: string | null; exitPrice: number | null;
  pnl: number | null; rMultiple: number | null; breakeven: boolean; source: string; notes: string; openedAt: string; closedAt: string | null; signalId: string | null;
}
interface Stats {
  total: number; open: number; closed: number; cancelledOrExpired: number; wins: number; losses: number; breakevens: number; winRate: number | null;
  totalR: number; profitFactor: number | null; totalPnl: number; startingCapital: number; currentCapital: number; returnPct: number | null;
  maxDrawdown: number; equityCurve: { time: string; equity: number }[];
}
interface AdminUserRow extends AppUser { stats: { total: number; open: number; closed: number; wins: number; losses: number; winRate: number | null; totalPnl: number; currentCapital: number } }

interface AccountViewProps {
  lang: Language;
  theme?: 'light' | 'dark';
  user: AppUser;
  onUserChange: (u: AppUser) => void;
  signals: AISignal[];
  assets: MarketAsset[];
}

const EMPTY = { symbol: 'XAU/USD', direction: 'BUY' as 'BUY' | 'SELL', entry: '', sl: '', tp1: '', tp2: '', lots: '', signalId: '' };
const num = (v: string) => (v.trim() === '' ? undefined : Number(v));

function EquityLine({ points, start }: { points: { equity: number }[]; start: number }) {
  if (points.length < 1) return null;
  const vals = [start, ...points.map(p => p.equity)];
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const d = vals.map((v, i) => `${(i / (vals.length - 1)) * 100},${30 - ((v - min) / span) * 28 - 1}`).join(' ');
  const up = vals[vals.length - 1] >= start;
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-16" role="img" aria-label="Equity curve">
      <polyline points={d} fill="none" strokeWidth="1.5" vectorEffect="non-scaling-stroke" className={up ? 'stroke-emerald-500' : 'stroke-rose-500'} />
    </svg>
  );
}

export const AccountView: React.FC<AccountViewProps> = ({ lang, theme = 'dark', user, onUserChange, signals, assets }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [profile, setProfile] = useState({ capital: String(user.capital), riskPct: String(user.riskPct) });
  const [form, setForm] = useState(EMPTY);
  const [exitPrices, setExitPrices] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [newUser, setNewUser] = useState({ username: '', accessCode: '', role: 'user', capital: '1000' });
  const [appSettings, setAppSettings] = useState<{ app: any; risk: any } | null>(null);
  const isAdmin = user.role === 'admin';

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
      const [s, tl] = await Promise.all([apiJson<Stats>('/api/stats'), apiJson<{ trades: Trade[] }>('/api/trades')]);
      setStats(s);
      setTrades(tl.trades);
      if (isAdmin) {
        const [u, st] = await Promise.all([apiJson<{ users: AdminUserRow[] }>('/api/users'), apiJson('/api/settings')]);
        setUsers(u.users);
        setAppSettings(st);
      }
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  useEffect(() => { load(); }, [user.id]);

  const priceOf = (sym: string) => assets.find(a => a.symbol === sym)?.price;
  const liveSignal = signals.find(s => s.isActionableNow && s.entryPrice > 0);
  const open = trades.filter(x => x.status === 'OPEN');
  const closed = trades.filter(x => x.status === 'CLOSED');

  const preview = useMemo(() => {
    const entry = num(form.entry), sl = num(form.sl);
    if (!entry || !sl || entry === sl) return null;
    const contract = form.symbol === 'XAU/USD' ? 100 : 100000;
    const lots = num(form.lots) ?? Math.floor(((user.capital * user.riskPct) / 100) / (Math.abs(entry - sl) * contract) / 0.01 + 1e-9) * 0.01;
    return { lots: Math.max(lots, 0), risk: Math.abs(entry - sl) * contract * Math.max(lots, 0) };
  }, [form, user.capital, user.riskPct]);

  const fromSignal = (s: AISignal) => setForm({
    symbol: s.symbol, direction: s.signalType === 'SELL' ? 'SELL' : 'BUY', entry: String(s.entryPrice), sl: String(s.stopLoss),
    tp1: String(s.target1 || ''), tp2: String(s.target2 || ''), lots: '', signalId: s.id,
  });

  const head = (cols: string[]) => (
    <thead className="text-slate-500 text-left"><tr>{cols.map(h => <th key={h} className="px-1.5 py-1.5 font-medium whitespace-nowrap">{h}</th>)}</tr></thead>
  );
  const rowCls = `border-t ${isLight ? 'border-paper-line' : 'border-line'}`;
  const resultTone = (r: string | null) => (r === 'WIN' ? 'text-emerald-500' : r === 'LOSS' ? 'text-rose-500' : 'text-slate-400');

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      <Card isLight={isLight} icon={<Wallet className="w-4 h-4" />} title={t('My capital', 'Mon capital', 'رأس مالي')}
        right={<span className="text-xs text-slate-500">{user.username} · {user.role}</span>}>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 mb-4">
          <Stat isLight={isLight} label={t('Starting capital', 'Capital initial', 'رأس المال')} value={fmtMoney(stats?.startingCapital)} />
          <Stat isLight={isLight} label={t('Current capital', 'Capital actuel', 'الرصيد الحالي')} value={fmtMoney(stats?.currentCapital)} tone="gold" />
          <Stat isLight={isLight} label="P&L" value={fmtMoney(stats?.totalPnl)} tone={(stats?.totalPnl ?? 0) >= 0 ? 'good' : 'bad'} />
          <Stat isLight={isLight} label={t('Return', 'Rendement', 'العائد')} value={fmtPct(stats?.returnPct)} />
          <Stat isLight={isLight} label={t('Trades', 'Trades', 'الصفقات')} value={stats ? `${stats.total} (${stats.open} ${t('open', 'ouverts', 'مفتوحة')})` : '—'} />
          <Stat isLight={isLight} label={t('Wins / losses', 'Gains / pertes', 'ربح / خسارة')} value={stats ? `${stats.wins} / ${stats.losses}` : '—'} />
          <Stat isLight={isLight} label={t('Win rate', 'Taux de réussite', 'نسبة النجاح')} value={fmtPct(stats?.winRate)} tone="gold" />
          <Stat isLight={isLight} label={t('Max drawdown', 'Drawdown max', 'أقصى تراجع')} value={fmtMoney(stats?.maxDrawdown)} tone="bad" />
        </div>
        {stats && stats.equityCurve.length > 0 && <EquityLine points={stats.equityCurve} start={stats.startingCapital} />}
        <div className="flex flex-wrap items-end gap-2 mt-3">
          <Field label={t('Capital ($)', 'Capital ($)', 'رأس المال ($)')}><input inputMode="decimal" value={profile.capital} onChange={e => setProfile({ ...profile, capital: e.target.value })} className={inputCls(isLight)} /></Field>
          <Field label={t('Risk per trade (%)', 'Risque par trade (%)', 'المخاطرة لكل صفقة (%)')}><input inputMode="decimal" value={profile.riskPct} onChange={e => setProfile({ ...profile, riskPct: e.target.value })} className={inputCls(isLight)} /></Field>
          <Button disabled={busy} onClick={() => run(async () => {
            const r = await apiJson('/api/me', { method: 'PUT', body: JSON.stringify({ capital: Number(profile.capital), riskPct: Number(profile.riskPct) }) });
            onUserChange(r.user);
            await load();
            return t('Saved. Lot sizes now use this capital and risk.', 'Enregistré. Les lots utilisent ce capital et ce risque.', 'تم الحفظ. اللوت يحسب الآن بهذا الرأسمال والمخاطرة.');
          })}>{t('Save', 'Enregistrer', 'حفظ')}</Button>
        </div>
      </Card>

      <Card isLight={isLight} icon={<Plus className="w-4 h-4" />} title={t('Record a trade I took', 'Enregistrer un trade pris', 'تسجيل صفقة دخلتها')}
        right={liveSignal && <Button variant="ghost" onClick={() => fromSignal(liveSignal)}><Target className="w-3.5 h-3.5" />{t(`Use ${liveSignal.symbol} signal`, `Signal ${liveSignal.symbol}`, `إشارة ${liveSignal.symbol}`)}</Button>}>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          <Field label={t('Pair', 'Paire', 'الزوج')}>
            <select value={form.symbol} onChange={e => setForm({ ...form, symbol: e.target.value })} className={inputCls(isLight)}>
              <option>XAU/USD</option><option>EUR/USD</option>
            </select>
          </Field>
          <Field label={t('Side', 'Sens', 'الاتجاه')}>
            <select value={form.direction} onChange={e => setForm({ ...form, direction: e.target.value as 'BUY' | 'SELL' })} className={inputCls(isLight)}>
              <option>BUY</option><option>SELL</option>
            </select>
          </Field>
          {(['entry', 'sl', 'tp1', 'tp2', 'lots'] as const).map(k => (
            <Field key={k} label={k === 'entry' ? 'Entry' : k === 'sl' ? 'Stop loss' : k === 'lots' ? t('Lots (auto)', 'Lots (auto)', 'اللوت (تلقائي)') : k.toUpperCase()}>
              <input inputMode="decimal" value={form[k]} onChange={e => setForm({ ...form, [k]: e.target.value })} placeholder={k === 'entry' && priceOf(form.symbol) ? String(priceOf(form.symbol)) : ''} className={inputCls(isLight)} />
            </Field>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
          <span className="text-xs text-slate-500">
            {preview ? t(`${preview.lots.toFixed(2)} lot · risk ${fmtMoney(preview.risk)} (${user.riskPct}% of ${fmtMoney(user.capital)})`, `${preview.lots.toFixed(2)} lot · risque ${fmtMoney(preview.risk)}`, `${preview.lots.toFixed(2)} لوت · مخاطرة ${fmtMoney(preview.risk)}`) : t('Lot size is computed from your capital and risk when left empty.', 'Le lot est calculé depuis votre capital et risque si vide.', 'يحسب اللوت من رأس مالك ونسبة المخاطرة إذا ترك فارغاً.')}
          </span>
          <Button disabled={busy || !num(form.entry) || !num(form.sl)} onClick={() => run(async () => {
            await apiJson('/api/trades', { method: 'POST', body: JSON.stringify({ symbol: form.symbol, direction: form.direction, entry: num(form.entry), sl: num(form.sl), tp1: num(form.tp1), tp2: num(form.tp2), lots: num(form.lots), signalId: form.signalId || undefined }) });
            setForm(EMPTY);
            await load();
            return t('Trade recorded', 'Trade enregistré', 'تم تسجيل الصفقة');
          })}>{t('Add trade', 'Ajouter', 'إضافة')}</Button>
        </div>
      </Card>

      <Card isLight={isLight} icon={<Target className="w-4 h-4" />} title={`${t('Open trades', 'Trades ouverts', 'الصفقات المفتوحة')} (${open.length})`}>
        {!open.length ? <p className="text-xs text-slate-500">{t('No open trade.', 'Aucun trade ouvert.', 'لا توجد صفقات مفتوحة.')}</p> : (
          <div className="overflow-x-auto"><table className="w-full text-xs tabular-nums">
            {head([t('Opened', 'Ouvert', 'الفتح'), t('Pair', 'Paire', 'الزوج'), t('Side', 'Sens', 'الاتجاه'), 'Entry', 'SL', 'TP2', 'Lots', t('Risk', 'Risque', 'المخاطرة'), t('Exit price', 'Prix de sortie', 'سعر الخروج'), ''])}
            <tbody>
              {open.map(x => (
                <tr key={x.id} className={rowCls}>
                  <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(x.openedAt)}</td>
                  <td className="px-1.5 py-1.5">{x.symbol}{x.signalId && <span className="ms-1 text-gold-500" title={t('Tracked automatically from the strategy signal', 'Suivi automatique du signal', 'متابعة تلقائية من الإشارة')}>●</span>}</td>
                  <td className={`px-1.5 py-1.5 font-semibold ${x.direction === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{x.direction}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.entry}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.breakeven ? <span className="text-gold-500">BE</span> : x.sl}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.tp2 ?? '—'}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.lots}</td>
                  <td className="px-1.5 py-1.5 font-mono">{fmtMoney(x.riskAmount)}</td>
                  <td className="px-1.5 py-1.5"><input inputMode="decimal" aria-label="exit price" value={exitPrices[x.id] ?? ''} placeholder={String(priceOf(x.symbol) ?? '')}
                    onChange={e => setExitPrices({ ...exitPrices, [x.id]: e.target.value })} className={`${inputCls(isLight)} w-24 py-1`} /></td>
                  <td className="px-1.5 py-1.5 whitespace-nowrap space-x-1">
                    <Button className="py-1" disabled={busy} onClick={() => run(async () => {
                      const exit = Number(exitPrices[x.id] || priceOf(x.symbol));
                      await apiJson(`/api/trades/${x.id}/close`, { method: 'POST', body: JSON.stringify({ exitPrice: exit }) });
                      await load();
                    })}>{t('Close', 'Clôturer', 'إغلاق')}</Button>
                    {!x.breakeven && <Button variant="ghost" className="py-1" disabled={busy} onClick={() => run(async () => { await apiJson(`/api/trades/${x.id}/breakeven`, { method: 'POST' }); await load(); })}>BE</Button>}
                    <Button variant="danger" className="py-1" disabled={busy} onClick={() => run(async () => { await apiJson(`/api/trades/${x.id}`, { method: 'DELETE' }); await load(); })}>✕</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      <Card isLight={isLight} icon={<History className="w-4 h-4" />} title={`${t('History', 'Historique', 'السجل')} (${closed.length})`}>
        {!closed.length ? <p className="text-xs text-slate-500">{t('Closed trades appear here.', 'Les trades clôturés apparaissent ici.', 'تظهر الصفقات المغلقة هنا.')}</p> : (
          <div className="overflow-x-auto"><table className="w-full text-xs tabular-nums">
            {head([t('Closed', 'Clôturé', 'الإغلاق'), t('Pair', 'Paire', 'الزوج'), t('Side', 'Sens', 'الاتجاه'), 'Entry', t('Exit', 'Sortie', 'الخروج'), 'Lots', t('Result', 'Résultat', 'النتيجة'), 'R', 'P&L'])}
            <tbody>
              {closed.map(x => (
                <tr key={x.id} className={rowCls}>
                  <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(x.closedAt)}</td>
                  <td className="px-1.5 py-1.5">{x.symbol}</td>
                  <td className={`px-1.5 py-1.5 font-semibold ${x.direction === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{x.direction}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.entry}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.exitPrice ?? '—'}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.lots}</td>
                  <td className={`px-1.5 py-1.5 font-semibold ${resultTone(x.result)}`}>{x.result}</td>
                  <td className={`px-1.5 py-1.5 font-mono ${resultTone(x.result)}`}>{fmtR(x.rMultiple)}</td>
                  <td className={`px-1.5 py-1.5 font-mono ${resultTone(x.result)}`}>{fmtMoney(x.pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      {isAdmin && (
        <>
          <Card isLight={isLight} icon={<Users className="w-4 h-4" />} title={`${t('Users', 'Utilisateurs', 'المستخدمون')} (${users.length})`}>
            <div className="overflow-x-auto mb-3"><table className="w-full text-xs tabular-nums">
              {head([t('User', 'Utilisateur', 'المستخدم'), t('Role', 'Rôle', 'الدور'), t('Capital', 'Capital', 'رأس المال'), t('Trades', 'Trades', 'الصفقات'), t('Win rate', 'Réussite', 'النجاح'), 'P&L', t('Last login', 'Dernière connexion', 'آخر دخول'), ''])}
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className={`${rowCls} ${u.active === false ? 'opacity-40' : ''}`}>
                    <td className="px-1.5 py-1.5 font-semibold">{u.username}</td>
                    <td className="px-1.5 py-1.5">{u.role}</td>
                    <td className="px-1.5 py-1.5 font-mono">{fmtMoney(u.stats.currentCapital)}</td>
                    <td className="px-1.5 py-1.5 font-mono">{u.stats.total} ({u.stats.open})</td>
                    <td className="px-1.5 py-1.5 font-mono">{fmtPct(u.stats.winRate)}</td>
                    <td className={`px-1.5 py-1.5 font-mono ${u.stats.totalPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>{fmtMoney(u.stats.totalPnl)}</td>
                    <td className="px-1.5 py-1.5 font-mono">{fmtDate(u.lastLoginAt)}</td>
                    <td className="px-1.5 py-1.5 whitespace-nowrap">
                      {u.id !== user.id && (
                        <Button variant="ghost" className="py-1" disabled={busy} onClick={() => run(async () => { await apiJson(`/api/users/${u.id}`, { method: 'PATCH', body: JSON.stringify({ active: u.active === false }) }); await load(); })}>
                          {u.active === false ? t('Enable', 'Activer', 'تفعيل') : t('Disable', 'Désactiver', 'تعطيل')}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <div className="flex flex-wrap items-end gap-2">
              <Field label={t('Username', "Nom d'utilisateur", 'اسم المستخدم')}><input value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })} className={inputCls(isLight)} /></Field>
              <Field label={t('Access code (min 6)', "Code d'accès (min 6)", 'رمز الدخول (6 على الأقل)')}><input value={newUser.accessCode} onChange={e => setNewUser({ ...newUser, accessCode: e.target.value })} className={inputCls(isLight)} /></Field>
              <Field label={t('Capital ($)', 'Capital ($)', 'رأس المال')}><input inputMode="decimal" value={newUser.capital} onChange={e => setNewUser({ ...newUser, capital: e.target.value })} className={inputCls(isLight)} /></Field>
              <Field label={t('Role', 'Rôle', 'الدور')}>
                <select value={newUser.role} onChange={e => setNewUser({ ...newUser, role: e.target.value })} className={inputCls(isLight)}><option value="user">user</option><option value="admin">admin</option></select>
              </Field>
              <Button disabled={busy || newUser.username.length < 2 || newUser.accessCode.length < 6} onClick={() => run(async () => {
                await apiJson('/api/users', { method: 'POST', body: JSON.stringify({ ...newUser, capital: Number(newUser.capital) }) });
                setNewUser({ username: '', accessCode: '', role: 'user', capital: '1000' });
                await load();
                return t('User created', 'Utilisateur créé', 'تم إنشاء المستخدم');
              })}><UserPlus className="w-3.5 h-3.5" />{t('Create', 'Créer', 'إنشاء')}</Button>
            </div>
          </Card>

          {appSettings && (
            <Card isLight={isLight} icon={<Settings2 className="w-4 h-4" />} title={t('App parameters', "Paramètres de l'app", 'إعدادات التطبيق')}>
              <div className="flex flex-wrap items-end gap-2">
                <Field label={t('App name', "Nom de l'app", 'اسم التطبيق')}><input value={appSettings.app.appName} onChange={e => setAppSettings({ ...appSettings, app: { ...appSettings.app, appName: e.target.value } })} className={inputCls(isLight)} /></Field>
                <Field label={t('Default language', 'Langue par défaut', 'اللغة الافتراضية')}>
                  <select value={appSettings.app.defaultLanguage} onChange={e => setAppSettings({ ...appSettings, app: { ...appSettings.app, defaultLanguage: e.target.value } })} className={inputCls(isLight)}>
                    <option value="fr">Français</option><option value="en">English</option><option value="ar">العربية</option>
                  </select>
                </Field>
                <Field label={t('Default capital for new users', 'Capital par défaut', 'رأس المال الافتراضي')}><input inputMode="decimal" value={appSettings.risk.defaultCapital} onChange={e => setAppSettings({ ...appSettings, risk: { ...appSettings.risk, defaultCapital: Number(e.target.value) } })} className={inputCls(isLight)} /></Field>
                <Field label={t('Default risk %', 'Risque par défaut %', 'المخاطرة الافتراضية %')}><input inputMode="decimal" value={appSettings.risk.defaultRiskPct} onChange={e => setAppSettings({ ...appSettings, risk: { ...appSettings.risk, defaultRiskPct: Number(e.target.value) } })} className={inputCls(isLight)} /></Field>
                <Button disabled={busy} onClick={() => run(async () => {
                  setAppSettings(await apiJson('/api/settings', { method: 'PUT', body: JSON.stringify(appSettings) }));
                  return t('Saved', 'Enregistré', 'تم الحفظ');
                })}><ShieldCheck className="w-3.5 h-3.5" />{t('Save', 'Enregistrer', 'حفظ')}</Button>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
};
