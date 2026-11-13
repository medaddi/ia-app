import React, { useEffect, useRef, useState } from 'react';
import { Bell, Send, Smartphone } from 'lucide-react';
import { apiJson } from '../api';
import { testPush } from '../notifications';
import { tr } from './ui';
import type { Language } from '../types';
import { signalHead, signalLevels, type TeamSetup } from '../smcTeam';

/**
 * The in-app notification bell: the live feed of the desk's alerts (Set & Forget signals with their trade updates; radar
 * reads are not alerts) from /api/smc/signals, and the two test buttons: a Telegram message to this account's
 * linked chat (/api/telegram/test-me) and a web push to this browser (/api/push/test).
 */
interface Item { id: string; symbol: string; title: string; detail: string; time: number }

const hm = (t: number) => new Date(t * 1000).toISOString().slice(5, 16).replace('T', ' ');

export const NotificationBell: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Item[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    apiJson<{ signals?: TeamSetup[] }>('/api/smc/signals').then(j => {
      if (!alive) return;
      const sig: Item[] = (j.signals ?? []).map(s => ({ id: s.id, symbol: s.symbol ?? '', time: s.time,
        title: `🎯 ${signalHead(s)}`,
        detail: `${signalLevels(s)}${s.resultR != null ? ` · ${s.resultR > 0 ? '+' : ''}${s.resultR}R` : ''}` }));
      setItems(sig.sort((a, b) => b.time - a.time).slice(0, 20));
    }).catch(() => setItems([]));
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => { alive = false; document.removeEventListener('mousedown', close); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const testTelegram = async () => {
    try {
      const r = await apiJson<{ success: boolean; error?: string }>('/api/telegram/test-me', { method: 'POST' });
      setNote(r.success ? t('Telegram test sent ✓', 'Test Telegram envoyé ✓', 'تصيفط التيست ف تيليغرام ✓') : (r.error ?? t('Telegram test failed', 'Échec du test Telegram', 'التيست ديال تيليغرام ما خدمش')));
    } catch { setNote(t('Telegram test failed', 'Échec du test Telegram', 'التيست ديال تيليغرام ما خدمش')); }
  };
  const testWebPush = async () => {
    const ok = await testPush();
    setNote(ok ? t('Push test sent ✓', 'Test push envoyé ✓', 'تصيفط التيست ديال الإشعار ✓') : t('No device subscribed: turn notifications on first', 'Aucun appareil abonné : activez les notifications', 'حتى جهاز ما مسجل: شعل الإشعارات أولا'));
  };

  return (
    <div className="relative" ref={box}>
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} aria-label={t('Notifications', 'Notifications', 'الإشعارات')}
        className="h-8 w-8 flex items-center justify-center rounded-lg border border-line text-slate-300 hover:text-white hover:bg-surface-2 cursor-pointer">
        <Bell className="w-4 h-4" />
      </button>
      {open && (
        <div className="absolute end-0 top-10 z-50 w-[min(92vw,360px)] rounded-xl border border-line glass shadow-xl p-3">
          <p className="text-xs font-semibold text-white">{t('Live alerts', 'Alertes en direct', 'التنبيهات المباشرة')}</p>
          <ul className="mt-2 max-h-72 overflow-y-auto space-y-1.5">
            {items.length === 0 && <li className="text-[11px] text-slate-500">{t('No alert yet.', 'Aucune alerte pour le moment.', 'حتى تنبيه دابا.')}</li>}
            {items.map(x => (
              <li key={x.id}>
                <button type="button" onClick={() => { window.dispatchEvent(new CustomEvent('ld-open-symbol', { detail: x.symbol })); setOpen(false); }}
                  className="w-full text-start rounded-lg border border-line bg-white/[0.02] px-2.5 py-1.5 hover:bg-white/[0.05] cursor-pointer">
                  <p className="text-[11px] font-semibold text-slate-100 truncate">{x.title}</p>
                  <p className="text-[10px] text-slate-400 truncate">{x.detail}</p>

                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button type="button" onClick={testTelegram} className="h-8 inline-flex items-center justify-center gap-1.5 rounded-lg border border-line text-[11px] text-slate-200 hover:bg-surface-2 cursor-pointer">
              <Send className="w-3.5 h-3.5" />{t('Test Telegram', 'Tester Telegram', 'جرب تيليغرام')}
            </button>
            <button type="button" onClick={testWebPush} className="h-8 inline-flex items-center justify-center gap-1.5 rounded-lg border border-line text-[11px] text-slate-200 hover:bg-surface-2 cursor-pointer">
              <Smartphone className="w-3.5 h-3.5" />{t('Test Web Push', 'Tester le push', 'جرب الإشعار')}
            </button>
          </div>
          {note && <p className="mt-2 text-[11px] text-slate-300" role="status">{note}</p>}
        </div>
      )}
    </div>
  );
};
