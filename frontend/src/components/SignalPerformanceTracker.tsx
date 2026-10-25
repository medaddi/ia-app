import React, { useEffect, useState } from 'react';
import { BarChart3, RefreshCw, Send, Trophy } from 'lucide-react';
import { apiJson } from '../api';
import { Language } from '../types';
import { Button, Card, Notice, Stat, fmtDate, fmtPct, fmtR, tr } from './ui';

interface SignalPerformanceTrackerProps {
  lang: Language;
  theme?: 'light' | 'dark';
  onOpenTelegram?: () => void;
}

interface SignalRow {
  id: string; symbol: string; setup: string; direction: 'BUY' | 'SELL'; entryType: string; entry: number; sl: number; tp2: number;
  rrTp2: number; score: number; signalTime: number; sentAt: string; recipients: number; latencyMs: number | null;
  state: string; outcome: 'WIN' | 'LOSS' | 'BREAKEVEN' | null; rMultiple: number | null;
}

interface Perf {
  stats: { total: number; open: number; closed: number; cancelledOrExpired: number; wins: number; losses: number; breakevens: number;
    winRate: number | null; totalR: number; avgR: number | null; profitFactor: number | null;
    bySymbol: Record<string, { closed: number; wins: number; losses: number; totalR: number; winRate: number | null }> };
  signals: SignalRow[];
}

/** Every signal the two strategies sent to Telegram, followed candle by candle with the strategy's own order lifecycle. */
export const SignalPerformanceTracker: React.FC<SignalPerformanceTrackerProps> = ({ lang, theme = 'dark', onOpenTelegram }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [data, setData] = useState<Perf | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      setData(await apiJson<Perf>('/api/signals/performance'));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const s = data?.stats;
  const stateLabel = (r: SignalRow) => (r.state === 'CLOSED' ? r.outcome || 'CLOSED' : r.state);
  const tone = (r: SignalRow) => (r.outcome === 'WIN' ? 'text-emerald-500' : r.outcome === 'LOSS' ? 'text-rose-500' : 'text-slate-400');

  return (
    <div className="space-y-4" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {error && <Notice kind="error">{error}</Notice>}
      <Card isLight={isLight} icon={<Trophy className="w-4 h-4" />} title={t('Strategy signal results', 'Résultats des signaux', 'نتائج الإشارات')}
        right={<Button variant="ghost" onClick={load} disabled={busy}><RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />{t('Refresh', 'Actualiser', 'تحديث')}</Button>}>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          <Stat isLight={isLight} label={t('Signals', 'Signaux', 'الإشارات')} value={s?.total ?? '—'} />
          <Stat isLight={isLight} label={t('Open', 'Ouverts', 'مفتوحة')} value={s?.open ?? '—'} />
          <Stat isLight={isLight} label={t('Closed', 'Clôturés', 'مغلقة')} value={s?.closed ?? '—'} />
          <Stat isLight={isLight} label={t('Wins', 'Gagnants', 'رابحة')} value={s?.wins ?? '—'} tone="good" />
          <Stat isLight={isLight} label={t('Losses', 'Perdants', 'خاسرة')} value={s?.losses ?? '—'} tone="bad" />
          <Stat isLight={isLight} label={t('Win rate', 'Taux de réussite', 'نسبة النجاح')} value={fmtPct(s?.winRate)} tone="gold" />
          <Stat isLight={isLight} label={t('Total', 'Total', 'المجموع')} value={fmtR(s?.totalR)} tone={(s?.totalR ?? 0) >= 0 ? 'good' : 'bad'} />
          <Stat isLight={isLight} label={t('Profit factor', 'Profit factor', 'معامل الربح')} value={s?.profitFactor ?? '—'} />
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {t('Win rate counts closed trades only (breakevens excluded). Results are in R: 1R = the risk of the trade. Unfilled limit orders are counted as cancelled, not as trades.',
            'Le taux de réussite ne compte que les trades clôturés (hors breakeven). Résultats en R : 1R = le risque du trade. Les ordres limites non exécutés sont annulés, pas comptés.',
            'نسبة النجاح تحسب الصفقات المغلقة فقط (بدون التعادل). النتائج بوحدة R: 1R = مخاطرة الصفقة. الأوامر المعلقة غير المنفذة لا تحسب كصفقات.')}
        </p>
      </Card>

      {s && Object.keys(s.bySymbol).length > 0 && (
        <Card isLight={isLight} icon={<BarChart3 className="w-4 h-4" />} title={t('By instrument', 'Par instrument', 'حسب الأداة')}>
          <div className="grid sm:grid-cols-2 gap-2">
            {Object.entries(s.bySymbol).map(([sym, b]) => (
              <div key={sym} className={`rounded-xl border p-3 text-xs ${isLight ? 'border-paper-line' : 'border-line'}`}>
                <div className="font-semibold text-gold-500 mb-1">{sym}</div>
                <div className="text-slate-400">{b.closed} {t('closed', 'clôturés', 'مغلقة')} · {b.wins}W / {b.losses}L · {fmtPct(b.winRate)} · {fmtR(b.totalR)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card isLight={isLight} title={t('Signal history', 'Historique des signaux', 'سجل الإشارات')}
        right={onOpenTelegram && <Button variant="ghost" onClick={onOpenTelegram}><Send className="w-3.5 h-3.5" />Telegram</Button>}>
        {!data?.signals.length ? (
          <p className="text-xs text-slate-500">{t('No signal has been sent yet. Signals appear here the moment a strategy sends one to Telegram.', "Aucun signal envoyé pour l'instant. Les signaux apparaissent ici dès leur envoi sur Telegram.", 'لم يتم إرسال أي إشارة بعد. تظهر الإشارات هنا لحظة إرسالها إلى تيليجرام.')}</p>
        ) : (
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs tabular-nums">
              <thead className="text-slate-500 text-left">
                <tr>{[t('Sent (UTC)', 'Envoyé (UTC)', 'الإرسال'), t('Pair', 'Paire', 'الزوج'), 'Setup', t('Side', 'Sens', 'الاتجاه'), 'Entry', 'SL', 'TP2', 'R:R', 'Score', t('Result', 'Résultat', 'النتيجة'), 'R'].map(h => <th key={h} className="px-1.5 py-1.5 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.signals.map(r => (
                  <tr key={r.id} className={`border-t ${isLight ? 'border-paper-line' : 'border-line'}`}>
                    <td className="px-1.5 py-1.5 font-mono">{fmtDate(r.sentAt)}</td>
                    <td className="px-1.5 py-1.5">{r.symbol}</td>
                    <td className="px-1.5 py-1.5">{r.setup}</td>
                    <td className={`px-1.5 py-1.5 font-semibold ${r.direction === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>{r.direction} {r.entryType}</td>
                    <td className="px-1.5 py-1.5 font-mono">{r.entry}</td>
                    <td className="px-1.5 py-1.5 font-mono">{r.sl}</td>
                    <td className="px-1.5 py-1.5 font-mono">{r.tp2}</td>
                    <td className="px-1.5 py-1.5 font-mono">1:{r.rrTp2.toFixed(1)}</td>
                    <td className="px-1.5 py-1.5 font-mono">{r.score}</td>
                    <td className={`px-1.5 py-1.5 font-semibold ${tone(r)}`}>{stateLabel(r)}</td>
                    <td className={`px-1.5 py-1.5 font-mono ${tone(r)}`}>{fmtR(r.rMultiple)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
