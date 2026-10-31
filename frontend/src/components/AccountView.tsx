import React, { useEffect, useState } from 'react';
import { INSTRUMENT_SYMBOLS } from '../instruments';
import { Check, Copy, History, KeyRound, OctagonAlert, Plus, Send, ShieldOff, Target, Wallet, Zap } from 'lucide-react';
import { apiJson } from '../api';
import { AISignal, Language, MarketAsset } from '../types';
import { Button, Card, Field, Notice, Stat, fmtDate, fmtMoney, fmtPct, fmtR, inputCls, tr } from './ui';

export interface AppUser {
  id: number; username: string; role: 'admin' | 'user'; dailyLossLimit?: number | null; riskUsd?: number | null; telegramChatId?: string | null;
  capital?: number | null; riskPct?: number | null; effectiveRisk?: number | null; telegramLinked?: boolean;
  active?: boolean; lastLoginAt?: string | null; createdAt?: string;
  firstName?: string | null; lastName?: string | null; status?: 'approved' | 'pending';  // self sign-ups wait for an admin
}

export interface Trade {
  id: number; symbol: string; direction: 'BUY' | 'SELL'; entry: number; sl: number; tp1: number | null; tp2: number | null; tp3: number | null;
  lots: number; riskAmount: number; status: 'OPEN' | 'CLOSED'; result: string | null; exitPrice: number | null;
  pnl: number | null; rMultiple: number | null; breakeven: boolean; source: string; notes: string; openedAt: string; closedAt: string | null; signalId: string | null;
}

export interface Today { day: string; pnl: number; trades: number; limit: number | null; reached: boolean; remaining: number | null }

export interface Stats {
  total: number; open: number; closed: number; cancelledOrExpired: number; wins: number; losses: number; breakevens: number; winRate: number | null;
  totalR: number; profitFactor: number | null; totalPnl: number; totalLots: number; bestPnl: number | null; worstPnl: number | null;
  maxDrawdown: number; pnlCurve: { time: string; pnl: number }[]; today: Today;
}

const num = (v: string) => (v.trim() === '' ? undefined : Number(v));

function PnlLine({ points }: { points: { pnl: number }[] }) {
  if (points.length < 1) return null;
  const vals = [0, ...points.map(p => p.pnl)];
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const d = vals.map((v, i) => `${(i / (vals.length - 1)) * 100},${30 - ((v - min) / span) * 28 - 1}`).join(' ');
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-16 mt-3" role="img" aria-label="Cumulative P&L">
      <polyline points={d} fill="none" strokeWidth="1.5" vectorEffect="non-scaling-stroke" className={vals[vals.length - 1] >= 0 ? 'stroke-emerald-500' : 'stroke-rose-500'} />
    </svg>
  );
}

/** One user's statistics, computed from the lots they took (own page and admin user detail). */
export function StatsGrid({ isLight, lang, stats }: { isLight: boolean; lang: Language; stats: Stats | null }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const s = stats;
  const today = s?.today;
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        <Stat isLight={isLight} label="P&L" value={fmtMoney(s?.totalPnl)} tone={(s?.totalPnl ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat isLight={isLight} label={t('Today', "Aujourd'hui", 'اليوم')} value={today ? `${fmtMoney(today.pnl)}${today.limit ? ` / -${fmtMoney(today.limit)}` : ''}` : '—'} tone={today?.reached ? 'bad' : undefined} />
        <Stat isLight={isLight} label={t('Trades', 'Trades', 'الصفقات')} value={s ? `${s.total} (${s.open} ${t('open', 'ouverts', 'مفتوحة')})` : '—'} />
        <Stat isLight={isLight} label={t('Wins / losses', 'Gains / pertes', 'ربح / خسارة')} value={s ? `${s.wins} / ${s.losses}` : '—'} />
        <Stat isLight={isLight} label={t('Win rate', 'Taux de réussite', 'نسبة النجاح')} value={fmtPct(s?.winRate)} tone="gold" />
        <Stat isLight={isLight} label={t('Total lots', 'Lots au total', 'مجموع اللوت')} value={s ? s.totalLots.toFixed(2) : '—'} />
        <Stat isLight={isLight} label={t('Profit factor', 'Profit factor', 'معامل الربح')} value={s?.profitFactor ?? '—'} />
        <Stat isLight={isLight} label={t('Max drawdown', 'Drawdown max', 'أقصى تراجع')} value={fmtMoney(s?.maxDrawdown)} tone="bad" />
      </div>
      {s && s.pnlCurve.length > 0 && <PnlLine points={s.pnlCurve} />}
    </>
  );
}

/** Read-only trade list used for history. */
export function TradesTable({ isLight, lang, trades }: { isLight: boolean; lang: Language; trades: Trade[] }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  if (!trades.length) return <p className="text-xs text-slate-500">{t('No trades yet.', 'Aucun trade.', 'لا توجد صفقات بعد.')}</p>;
  const tone = (r: string | null) => (r === 'WIN' ? 'text-emerald-500' : r === 'LOSS' ? 'text-rose-500' : 'text-slate-400');
  return (
    <div className="overflow-x-auto"><table className="w-full text-xs tabular-nums">
      <thead className="text-slate-500 text-left"><tr>
        {[t('Opened', 'Ouvert', 'الفتح'), t('Closed', 'Clôturé', 'الإغلاق'), t('Pair', 'Paire', 'الزوج'), t('Side', 'Sens', 'الاتجاه'), 'Entry', 'SL', t('Exit', 'Sortie', 'الخروج'), 'Lot', t('Result', 'Résultat', 'النتيجة'), 'R', 'P&L']
          .map(h => <th key={h} className="px-1.5 py-1.5 font-medium whitespace-nowrap">{h}</th>)}
      </tr></thead>
      <tbody>
        {trades.map(x => (
          <tr key={x.id} className={`border-t ${isLight ? 'border-paper-line' : 'border-line'}`}>
            <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(x.openedAt)}</td>
            <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{x.status === 'OPEN' ? <span className="text-gold-500">{t('open', 'ouvert', 'مفتوحة')}</span> : fmtDate(x.closedAt)}</td>
            <td className="px-1.5 py-1.5">{x.symbol}{x.signalId && <span className="ms-1 text-gold-500" title="signal">●</span>}</td>
            <td className={`px-1.5 py-1.5 font-semibold ${x.direction === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{x.direction}</td>
            <td className="px-1.5 py-1.5 font-mono">{x.entry}</td>
            <td className="px-1.5 py-1.5 font-mono">{x.sl}</td>
            <td className="px-1.5 py-1.5 font-mono">{x.exitPrice ?? '—'}</td>
            <td className="px-1.5 py-1.5 font-mono">{x.lots}</td>
            <td className={`px-1.5 py-1.5 font-semibold ${tone(x.result)}`}>{x.result ?? '—'}</td>
            <td className={`px-1.5 py-1.5 font-mono ${tone(x.result)}`}>{fmtR(x.rMultiple)}</td>
            <td className={`px-1.5 py-1.5 font-mono ${tone(x.result)}`}>{fmtMoney(x.pnl)}</td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

interface AccountViewProps {
  lang: Language;
  theme?: 'light' | 'dark';
  user: AppUser;
  onUserChange: (u: AppUser) => void;
  signals: AISignal[];
  assets: MarketAsset[];
}

const EMPTY = { symbol: 'XAU/USD', direction: 'BUY' as 'BUY' | 'SELL', entry: '', sl: '', tp1: '', tp2: '', lots: '' };

function TelegramLinkCard({ isLight, lang, user, onUserChange }: { isLight: boolean; lang: Language; user: AppUser; onUserChange: (u: AppUser) => void }) {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [link, setLink] = useState<{ code: string; expiresAt: number; bot: string | null; deepLink: string | null } | null>(null);
  const [now, setNow] = useState(Date.now());
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!link) return; const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, [link]);
  // While a code is waiting, check every 3 s whether the bot received it
  useEffect(() => {
    if (!link || user.telegramLinked) return;
    const id = setInterval(async () => {
      try { const r = await apiJson<{ user: AppUser }>('/api/me'); if (r.user.telegramLinked) { onUserChange(r.user); setLink(null); } } catch { /* retry */ }
    }, 3000);
    return () => clearInterval(id);
  }, [link, user.telegramLinked]);
  const left = link ? Math.max(0, link.expiresAt - Math.floor(now / 1000)) : 0;
  const generate = async () => {
    setErr(null);
    try { setLink(await apiJson('/api/me/telegram-link', { method: 'POST' })); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Card isLight={isLight} icon={<Send className="w-4 h-4" />} title={t('Telegram bot', 'Bot Telegram', 'بوت تيليغرام')}
      right={user.telegramLinked ? <span className="text-xs font-semibold text-emerald-500">● {t('Linked', 'Connecté', 'مربوط')}</span> : undefined}>
      {user.telegramLinked ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <p className="text-slate-400">{t('The bot knows this account: every signal comes with your own lot', 'Le bot connaît ce compte : chaque signal arrive avec votre lot', 'البوت كيعرف هاد الحساب: كل إشارة كتجيك باللوت ديالك')}
            {user.effectiveRisk ? ` ($${user.effectiveRisk} / trade)` : ''}. Chat <span className="font-mono">{user.telegramChatId}</span></p>
          <Button variant="ghost" onClick={async () => { const r = await apiJson<{ user: AppUser }>('/api/me/telegram-link', { method: 'DELETE' }); onUserChange(r.user); }}>
            {t('Unlink', 'Déconnecter', 'فك الربط')}
          </Button>
        </div>
      ) : link && left > 0 ? (
        <div className="space-y-3">
          <p className="text-xs text-slate-400">{t('Send this code to the bot (or tap "Open the bot"). It works once, for 15 minutes.', 'Envoyez ce code au bot (ou touchez « Ouvrir le bot »). Il marche une fois, pendant 15 minutes.', 'صيفط هاد الكود للبوت (ولا كليكي "حل البوت"). كيخدم مرة وحدة، 15 دقيقة.')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className={`px-4 py-2.5 rounded-xl text-xl font-mono font-bold tracking-[0.2em] border ${isLight ? 'bg-paper border-paper-line-2 text-ink-strong' : 'bg-surface border-gold-500/40 text-gold-200'}`}>{link.code}</code>
            <Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(link.code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {}); }}>
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}{copied ? t('Copied', 'Copié', 'تنسخ') : t('Copy', 'Copier', 'نسخ')}
            </Button>
            {link.deepLink && <a href={link.deepLink} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold text-ink-strong bg-gold-gradient cursor-pointer"><Send className="w-3.5 h-3.5" />{t('Open the bot', 'Ouvrir le bot', 'حل البوت')}{link.bot ? ` @${link.bot}` : ''}</a>}
          </div>
          <p className="text-[11px] text-slate-500 font-mono">{t('Expires in', 'Expire dans', 'كيسالي من بعد')} {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')} · {t('waiting for the bot…', 'en attente du bot…', 'كنتسناو البوت…')}</p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-400 max-w-xl">{t('Link your account to the Telegram bot: it will send you the signals with the lot for your capital and risk, and /risk, /capital in the bot change this account.',
            "Liez votre compte au bot Telegram : il vous envoie les signaux avec le lot pour votre capital et votre risque, et /risk, /capital dans le bot modifient ce compte.",
            'اربط الحساب ديالك بالبوت: غادي يصيفط ليك الإشارات باللوت على حساب الرأسمال والمخاطرة ديالك، و /risk و /capital ف البوت كيبدلو هاد الحساب.')}</p>
          <Button onClick={generate}><KeyRound className="w-3.5 h-3.5" />{t('Get my link code', 'Obtenir mon code', 'عطيني الكود ديالي')}</Button>
          {err && <p className="text-xs text-rose-500 basis-full">{err}</p>}
        </div>
      )}
    </Card>
  );
}

export const AccountView: React.FC<AccountViewProps> = ({ lang, theme = 'dark', user, onUserChange, signals, assets }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [lossLimit, setLossLimit] = useState(user.dailyLossLimit ? String(user.dailyLossLimit) : '');
  const [capital, setCapital] = useState(user.capital ? String(user.capital) : '');
  const [riskMode, setRiskMode] = useState<'usd' | 'pct'>(user.riskUsd || !user.capital ? 'usd' : 'pct');
  const [riskValue, setRiskValue] = useState(user.riskUsd ? String(user.riskUsd) : user.capital && user.riskPct ? String(user.riskPct) : '');
  // Lot for my $ risk on each live signal, computed by the backend with the signal's own stop
  const [lotFor, setLotFor] = useState<Record<string, { lots: number; actualRisk: number; tooSmall: boolean }>>({});
  const [form, setForm] = useState(EMPTY);
  const [signalLots, setSignalLots] = useState<Record<string, string>>({});
  const [exitPrices, setExitPrices] = useState<Record<number, string>>({});
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
      const [s, tl] = await Promise.all([apiJson<Stats>('/api/stats'), apiJson<{ trades: Trade[] }>('/api/trades')]);
      setStats(s);
      setTrades(tl.trades);
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  useEffect(() => { load(); }, [user.id]);

  const blocked = !!stats?.today.reached;
  const priceOf = (sym: string) => assets.find(a => a.symbol === sym)?.price;
  const live = signals.filter(s => s.isActionableNow && s.entryPrice > 0);
  const liveKey = live.map(s => `${s.id}:${s.stopLoss}`).join('|');
  useEffect(() => {
    if (!user.effectiveRisk || !live.length) { setLotFor({}); return; }
    let stop = false;
    Promise.all(live.map(s => apiJson<{ lots: number; actualRisk: number; tooSmall: boolean }>(
      `/api/lot?symbol=${encodeURIComponent(s.symbol)}&entry=${s.entryPrice}&sl=${s.stopLoss}`).then(r => [s.id, r] as const).catch(() => null)))
      .then(rows => { if (!stop) setLotFor(Object.fromEntries(rows.filter(Boolean) as [string, any][])); });
    return () => { stop = true; };
  }, [liveKey, user.effectiveRisk]);
  const takenSignalIds = new Set(trades.map(x => x.signalId).filter(Boolean).map(id => `sig-${id}`));
  const open = trades.filter(x => x.status === 'OPEN');
  const closed = trades.filter(x => x.status === 'CLOSED');

  const addTrade = (body: Record<string, unknown>, okText: string) => run(async () => {
    await apiJson('/api/trades', { method: 'POST', body: JSON.stringify(body) });
    await load();
    return okText;
  });

  const rowCls = `border-t ${isLight ? 'border-paper-line' : 'border-line'}`;

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      <Card isLight={isLight} icon={<Wallet className="w-4 h-4" />} title={t('My statistics', 'Mes statistiques', 'الإحصائيات ديالي')}
        right={<span className="text-xs text-slate-500">{user.username} · {user.role}</span>}>
        <StatsGrid isLight={isLight} lang={lang} stats={stats} />
      </Card>

      <Card isLight={isLight} icon={<ShieldOff className="w-4 h-4" />} title={t('My capital & risk', 'Mon capital & risque', 'الرأسمال والمخاطرة ديالي')}
        right={user.effectiveRisk ? <span className="text-xs font-mono text-gold-500">{t('Risk', 'Risque', 'المخاطرة')} ${user.effectiveRisk} / trade</span> : undefined}>
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t('Capital ($)', 'Capital ($)', 'الرأسمال ($)')}>
            <input inputMode="decimal" value={capital} placeholder="5000" onChange={e => setCapital(e.target.value)} className={inputCls(isLight)} />
          </Field>
          <Field label={t('Risk per trade', 'Risque par trade', 'المخاطرة ف كل صفقة')}>
            <div className="flex gap-1.5">
              <input inputMode="decimal" value={riskValue} placeholder={riskMode === 'usd' ? '80' : '1'} onChange={e => setRiskValue(e.target.value)} className={`${inputCls(isLight)} w-24`} />
              <div role="radiogroup" aria-label={t('Risk unit', 'Unité du risque', 'وحدة المخاطرة')} className={`flex rounded-lg border p-0.5 ${isLight ? 'border-paper-line-2' : 'border-line-2'}`}>
                {(['usd', 'pct'] as const).map(m => (
                  <button key={m} type="button" role="radio" aria-checked={riskMode === m} onClick={() => setRiskMode(m)}
                    className={`px-2.5 rounded-md text-xs font-semibold whitespace-nowrap cursor-pointer transition-colors duration-150 ${riskMode === m ? 'bg-gold-500/15 text-gold-500' : 'text-slate-500 hover:text-slate-300'}`}>
                    {m === 'usd' ? '$' : t('% capital', '% capital', '% الرأسمال')}
                  </button>
                ))}
              </div>
            </div>
          </Field>
          <Field label={t('Max loss per day ($, empty = none)', 'Perte max par jour ($, vide = aucune)', 'أقصى خسارة فالنهار ($، فارغ = بلا حد)')}>
            <input inputMode="decimal" value={lossLimit} placeholder="—" onChange={e => setLossLimit(e.target.value)} className={inputCls(isLight)} />
          </Field>
          <Button disabled={busy || (riskMode === 'pct' && !(Number(capital) > 0) && !!riskValue)} onClick={() => run(async () => {
            const v = Number(riskValue) || 0;
            const r = await apiJson('/api/me', { method: 'PUT', body: JSON.stringify({
              dailyLossLimit: lossLimit ? Number(lossLimit) : 0, capital: Number(capital) || 0,
              ...(riskMode === 'usd' ? { riskUsd: v } : { riskUsd: 0, riskPct: v || 1 }),
            }) });
            onUserChange(r.user);
            await load();
            return t('Saved: the app and the Telegram bot use this risk', 'Enregistré : l’app et le bot Telegram utilisent ce risque', 'تحفظ: التطبيق والبوت كيستعملو هاد المخاطرة');
          })}>{t('Save', 'Enregistrer', 'حفظ')}</Button>
          <p className="text-xs text-slate-500 basis-full">
            {t('Each signal gives you the lot that loses exactly your risk if the stop is hit; the stop stays where the strategy puts it (structure). Risk in % = % of your capital. ',
              "Chaque signal vous donne le lot qui perd exactement votre risque si le stop est touché ; le stop reste où la stratégie le place (structure). Risque en % = % de votre capital. ",
              'كل إشارة كتعطيك اللوت لي كيخسر بالضبط المخاطرة ديالك إلا ضرب الستوب؛ الستوب كيبقى فين حطاتو الاستراتيجية (الهيكل). المخاطرة ب % = % من الرأسمال. ')}
            {t('When your closed trades of the day lose the daily maximum, no new trade can be added until 17:00 New York.',
              "Quand vos trades clôturés du jour perdent le maximum journalier, plus aucun trade jusqu'à 17:00 New York.",
              'ملي توصل الخسارة ديال اليوم للحد، ما تقدرش تزيد حتى صفقة حتى 17:00 نيويورك.')}
          </p>
        </div>
      </Card>

      <TelegramLinkCard isLight={isLight} lang={lang} user={user} onUserChange={onUserChange} />

      {blocked && (
        <Notice kind="error">
          <span className="inline-flex items-center gap-1.5"><OctagonAlert className="w-3.5 h-3.5" />
            {t(`Daily loss limit reached (${fmtMoney(stats!.today.pnl)} / -${fmtMoney(stats!.today.limit)}). No more trades today.`,
              `Perte journalière max atteinte (${fmtMoney(stats!.today.pnl)} / -${fmtMoney(stats!.today.limit)}). Plus de trades aujourd'hui.`,
              `وصلتي للخسارة اليومية القصوى (${fmtMoney(stats!.today.pnl)} / -${fmtMoney(stats!.today.limit)}). ما كاين حتى صفقة اليوم.`)}
          </span>
        </Notice>
      )}

      {!blocked && (
        <Card isLight={isLight} icon={<Zap className="w-4 h-4" />} title={t('Live signals', 'Signaux en cours', 'الإشارات الحالية')}>
          {!live.length ? (
            <p className="text-xs text-slate-500">{t('No live signal right now. When a strategy gives a signal it appears here: enter the lot you took and it goes into your history.',
              "Aucun signal en cours. Quand une stratégie donne un signal, il apparaît ici : indiquez le lot pris et il entre dans votre historique.",
              'لا توجد إشارة حالياً. ملي تطلع صفقة كتبان هنا: دخل اللوت لي دخلتي بيه وكتمشي للسجل ديالك.')}</p>
          ) : (
            <div className="space-y-2">
              {live.map(s => {
                const rec = lotFor[s.id];
                const lot = signalLots[s.id] ?? (rec ? rec.lots.toFixed(2) : '');
                return (
                  <div key={s.id} className={`flex flex-wrap items-end justify-between gap-3 rounded-xl border p-3 ${isLight ? 'border-paper-line' : 'border-line'}`}>
                    <div className="text-xs">
                      <div className={`font-semibold ${s.signalType === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{s.signalType} {s.entryType} · {s.symbol}</div>
                      <div className="font-mono text-slate-400">
                        {/* Forex (FXAlexG set & forget) has one target; gold has TP1 / TP2 / TP3 */}
                        Entry {s.entryPrice} · SL {s.stopLoss} · {`TP ${s.target3 ?? s.target2}`} · score {s.confidence}
                      </div>
                      {rec ? (
                        <div className="font-mono text-gold-500 mt-0.5">
                          {t(`Your lot: ${rec.lots.toFixed(2)} (risk $${rec.actualRisk})`, `Votre lot : ${rec.lots.toFixed(2)} (risque $${rec.actualRisk})`, `اللوت ديالك: ${rec.lots.toFixed(2)} (مخاطرة $${rec.actualRisk})`)}
                          {rec.tooSmall && t(' · minimum lot, above your risk', ' · lot minimum, au-dessus de votre risque', ' · أقل لوت، فوق المخاطرة ديالك')}
                        </div>
                      ) : !user.effectiveRisk && (
                        <div className="text-slate-500 mt-0.5">{t('Set your risk per trade above to get your lot.', 'Indiquez votre risque par trade ci-dessus pour avoir votre lot.', 'دخل شحال كتخاطر فوق باش تاخد اللوت ديالك.')}</div>
                      )}
                    </div>
                    {takenSignalIds.has(s.id) ? <span className="text-xs text-gold-500">{t('In your trades', 'Dans vos trades', 'مسجلة في صفقاتك')}</span> : (
                      <div className="flex items-end gap-2">
                        <Field label={t('Lot I took', 'Lot pris', 'اللوت لي دخلت بيه')}>
                          <input inputMode="decimal" value={lot} placeholder="0.10" onChange={e => setSignalLots({ ...signalLots, [s.id]: e.target.value })} className={`${inputCls(isLight)} w-24`} />
                        </Field>
                        <Button disabled={busy || !(Number(lot) > 0)} onClick={() => addTrade({
                          symbol: s.symbol, direction: s.signalType, entry: s.entryPrice, sl: s.stopLoss, tp1: s.target1, tp2: s.target2, tp3: s.target3,
                          lots: Number(lot), signalId: s.id,
                        }, t('Trade recorded: its result follows the signal automatically.', 'Trade enregistré : son résultat suit le signal automatiquement.', 'تم تسجيل الصفقة: النتيجة كتتبع الإشارة أوتوماتيكياً.'))}>
                          <Target className="w-3.5 h-3.5" />{t('I took it', "Je l'ai pris", 'دخلت الصفقة')}
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {!blocked && (
        <Card isLight={isLight} icon={<Plus className="w-4 h-4" />} title={t('Record another trade', 'Enregistrer un autre trade', 'تسجيل صفقة أخرى')}>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
            <Field label={t('Pair', 'Paire', 'الزوج')}>
              <select value={form.symbol} onChange={e => setForm({ ...form, symbol: e.target.value })} className={inputCls(isLight)}>{INSTRUMENT_SYMBOLS.map(x => <option key={x}>{x}</option>)}</select>
            </Field>
            <Field label={t('Side', 'Sens', 'الاتجاه')}>
              <select value={form.direction} onChange={e => setForm({ ...form, direction: e.target.value as 'BUY' | 'SELL' })} className={inputCls(isLight)}><option>BUY</option><option>SELL</option></select>
            </Field>
            {(['entry', 'sl', 'tp1', 'tp2', 'lots'] as const).map(k => (
              <Field key={k} label={k === 'entry' ? 'Entry' : k === 'sl' ? 'Stop loss' : k === 'lots' ? t('Lot taken', 'Lot pris', 'اللوت') : k.toUpperCase()}>
                <input inputMode="decimal" value={form[k]} onChange={e => setForm({ ...form, [k]: e.target.value })} placeholder={k === 'entry' && priceOf(form.symbol) ? String(priceOf(form.symbol)) : ''} className={inputCls(isLight)} />
              </Field>
            ))}
          </div>
          <div className="flex justify-end mt-3">
            <Button disabled={busy || !num(form.entry) || !num(form.sl) || !(Number(form.lots) > 0)} onClick={async () => {
              await addTrade({ symbol: form.symbol, direction: form.direction, entry: num(form.entry), sl: num(form.sl), tp1: num(form.tp1), tp2: num(form.tp2), lots: num(form.lots) },
                t('Trade recorded', 'Trade enregistré', 'تم تسجيل الصفقة'));
              setForm(EMPTY);
            }}>{t('Add trade', 'Ajouter', 'إضافة')}</Button>
          </div>
        </Card>
      )}

      <Card isLight={isLight} icon={<Target className="w-4 h-4" />} title={`${t('Open trades', 'Trades ouverts', 'الصفقات المفتوحة')} (${open.length})`}>
        {!open.length ? <p className="text-xs text-slate-500">{t('No open trade.', 'Aucun trade ouvert.', 'لا توجد صفقات مفتوحة.')}</p> : (
          <div className="overflow-x-auto"><table className="w-full text-xs tabular-nums">
            <thead className="text-slate-500 text-left"><tr>
              {[t('Opened', 'Ouvert', 'الفتح'), t('Pair', 'Paire', 'الزوج'), t('Side', 'Sens', 'الاتجاه'), 'Entry', 'SL', 'TP2', 'Lot', t('At stop', 'Au stop', 'عند الوقف'), t('Exit price', 'Prix de sortie', 'سعر الخروج'), '']
                .map(h => <th key={h} className="px-1.5 py-1.5 font-medium whitespace-nowrap">{h}</th>)}
            </tr></thead>
            <tbody>
              {open.map(x => (
                <tr key={x.id} className={rowCls}>
                  <td className="px-1.5 py-1.5 font-mono whitespace-nowrap">{fmtDate(x.openedAt)}</td>
                  <td className="px-1.5 py-1.5">{x.symbol}{x.signalId && <span className="ms-1 text-gold-500" title={t('Closed automatically with the signal', 'Clôturé automatiquement avec le signal', 'كيتسد أوتوماتيكياً مع الإشارة')}>●</span>}</td>
                  <td className={`px-1.5 py-1.5 font-semibold ${x.direction === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{x.direction}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.entry}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.breakeven ? <span className="text-gold-500">BE</span> : x.sl}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.tp2 ?? '—'}</td>
                  <td className="px-1.5 py-1.5 font-mono">{x.lots}</td>
                  <td className="px-1.5 py-1.5 font-mono text-rose-500">-{fmtMoney(x.riskAmount)}</td>
                  <td className="px-1.5 py-1.5"><input inputMode="decimal" aria-label="exit price" value={exitPrices[x.id] ?? ''} placeholder={String(priceOf(x.symbol) ?? '')}
                    onChange={e => setExitPrices({ ...exitPrices, [x.id]: e.target.value })} className={`${inputCls(isLight)} w-24 py-1`} /></td>
                  <td className="px-1.5 py-1.5 whitespace-nowrap space-x-1">
                    <Button className="py-1" disabled={busy} onClick={() => run(async () => {
                      await apiJson(`/api/trades/${x.id}/close`, { method: 'POST', body: JSON.stringify({ exitPrice: Number(exitPrices[x.id] || priceOf(x.symbol)) }) });
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
        <TradesTable isLight={isLight} lang={lang} trades={closed} />
      </Card>
    </div>
  );
};
