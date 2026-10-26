import React, { useEffect, useState } from 'react';
import { INSTRUMENT_SYMBOLS } from '../instruments';
import { History, OctagonAlert, Plus, ShieldOff, Target, Wallet, Zap } from 'lucide-react';
import { apiJson } from '../api';
import { AISignal, Language, MarketAsset } from '../types';
import { Button, Card, Field, Notice, Stat, fmtDate, fmtMoney, fmtPct, fmtR, inputCls, tr } from './ui';

export interface AppUser {
  id: number; username: string; role: 'admin' | 'user'; dailyLossLimit?: number | null; active?: boolean; lastLoginAt?: string | null;
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

export const AccountView: React.FC<AccountViewProps> = ({ lang, theme = 'dark', user, onUserChange, signals, assets }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [lossLimit, setLossLimit] = useState(user.dailyLossLimit ? String(user.dailyLossLimit) : '');
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

      <Card isLight={isLight} icon={<ShieldOff className="w-4 h-4" />} title={t('Daily loss limit', 'Perte journalière max', 'الخسارة اليومية القصوى')}>
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t('Max loss per day ($, empty = none)', 'Perte max par jour ($, vide = aucune)', 'أقصى خسارة فالنهار ($، فارغ = بلا حد)')}>
            <input inputMode="decimal" value={lossLimit} placeholder="—" onChange={e => setLossLimit(e.target.value)} className={inputCls(isLight)} />
          </Field>
          <Button disabled={busy} onClick={() => run(async () => {
            const r = await apiJson('/api/me', { method: 'PUT', body: JSON.stringify({ dailyLossLimit: lossLimit ? Number(lossLimit) : 0 }) });
            onUserChange(r.user);
            await load();
            return t('Saved', 'Enregistré', 'تم الحفظ');
          })}>{t('Save', 'Enregistrer', 'حفظ')}</Button>
          <p className="text-xs text-slate-500 basis-full">
            {t('When your closed trades of the day lose this amount, no new trade can be added until the next trading day (17:00 New York).',
              "Quand vos trades clôturés du jour perdent ce montant, plus aucun trade ne peut être ajouté jusqu'au jour de trading suivant (17:00 New York).",
              'ملي توصل الخسارة ديال الصفقات المسدودة اليوم لهاد المبلغ، ما تقدرش تزيد حتى صفقة حتى النهار الجاي (17:00 نيويورك).')}
          </p>
        </div>
      </Card>

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
                const lot = signalLots[s.id] ?? '';
                return (
                  <div key={s.id} className={`flex flex-wrap items-end justify-between gap-3 rounded-xl border p-3 ${isLight ? 'border-paper-line' : 'border-line'}`}>
                    <div className="text-xs">
                      <div className={`font-semibold ${s.signalType === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{s.signalType} {s.entryType} · {s.symbol}</div>
                      <div className="font-mono text-slate-400">Entry {s.entryPrice} · SL {s.stopLoss} · TP1 {s.target1} · TP2 {s.target2} · score {s.confidence}</div>
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
