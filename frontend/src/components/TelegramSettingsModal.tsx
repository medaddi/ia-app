import React, { useEffect, useState } from 'react';
import { Bot, Check, Copy, KeyRound, Send, ShieldCheck, Trash2, Users, X, Zap } from 'lucide-react';
import { apiJson } from '../api';
import { Language } from '../types';
import { Button, Card, Field, Notice, Stat, fmtDate, inputCls, tr } from './ui';

interface TelegramSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

interface Config {
  chatId: string; enabled: boolean; minConfidence: number; assets: string[]; protectContent: boolean; personalOffsets: boolean;
  hasBotToken: boolean; botTokenMasked: string;
}
interface LogRow { id: string; type: string; title: string; details: string; sentAt: string; status: string; error?: string | null }
interface Code { code: string; label: string; durationHours: number; multiUse: boolean; usedCount: number; revoked: boolean; createdAt: string }
interface Sub { chatId: string; firstName: string; code: string | null; expiresAt: string | null; active: boolean; capital: number; riskPct: number }

const ASSETS = ['XAU/USD', 'EUR/USD'];
const DURATIONS = [{ h: 24, l: '1 d' }, { h: 168, l: '7 d' }, { h: 720, l: '30 d' }, { h: 2160, l: '90 d' }, { h: 8760, l: '1 y' }];

/** Admin settings of the Telegram bot. The bot token is stored on the server only and never sent back to the browser. */
export const TelegramSettingsModal: React.FC<TelegramSettingsModalProps> = ({ isOpen, onClose, lang, theme = 'dark' }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [token, setToken] = useState('');
  const [botName, setBotName] = useState<string | null>(null);
  const [history, setHistory] = useState<LogRow[]>([]);
  const [codes, setCodes] = useState<Code[]>([]);
  const [subs, setSubs] = useState<Sub[]>([]);
  const [duration, setDuration] = useState(720);
  const [label, setLabel] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

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
      const [c, a, s] = await Promise.all([
        apiJson('/api/telegram/config'), apiJson('/api/telegram/activation/status'), apiJson('/api/telegram/subscribers'),
      ]);
      setCfg(c.config);
      setHistory(c.history || []);
      setCodes(a.codes || []);
      setSubs(s.subscribers || []);
      if (c.config.hasBotToken) apiJson('/api/telegram/bot-info').then(b => setBotName(b.success ? `@${b.username}` : null)).catch(() => setBotName(null));
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  useEffect(() => { if (isOpen) load(); }, [isOpen]);
  if (!isOpen) return null;

  const save = (patch: Partial<Config> & { botToken?: string }) => run(async () => {
    const r = await apiJson('/api/telegram/config', { method: 'POST', body: JSON.stringify(patch) });
    setCfg(r.config);
    return t('Saved', 'Enregistré', 'تم الحفظ');
  });

  const connectBot = () => run(async () => {
    const r = await apiJson('/api/telegram/switch-bot', { method: 'POST', body: JSON.stringify({ botToken: token.trim() }) });
    setToken('');
    setBotName(`@${r.bot.username}`);
    await load();
    return t(`Bot @${r.bot.username} connected`, `Bot @${r.bot.username} connecté`, `تم ربط البوت @${r.bot.username}`);
  });

  const copy = (code: string) => {
    navigator.clipboard?.writeText(code).catch(() => {});
    setCopied(code);
    setTimeout(() => setCopied(null), 1500);
  };

  const toggle = (key: 'enabled' | 'protectContent' | 'personalOffsets', text: string) => cfg && (
    <label className="flex items-center justify-between gap-3 text-xs py-1.5 cursor-pointer">
      <span className={isLight ? 'text-ink-strong' : 'text-slate-200'}>{text}</span>
      <input type="checkbox" className="accent-gold-500 w-4 h-4" checked={cfg[key]} onChange={e => save({ [key]: e.target.checked })} />
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/70 backdrop-blur-xs" role="dialog" aria-modal="true" aria-labelledby="tg-title" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} dir={lang === 'ar' ? 'rtl' : 'ltr'}
        className={`w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded-2xl border shadow-2xl ${isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'}`}>
        <header className={`sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b ${isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'}`}>
          <div className="flex items-center gap-2.5">
            <Bot className="w-5 h-5 text-gold-500" />
            <div>
              <h2 id="tg-title" className={`text-sm font-semibold ${isLight ? 'text-ink-strong' : 'text-white'}`}>{t('Telegram bot', 'Bot Telegram', 'بوت تيليجرام')}</h2>
              <p className="text-xs text-slate-500">{botName ? t(`Connected: ${botName}`, `Connecté : ${botName}`, `متصل: ${botName}`) : t('No bot connected', 'Aucun bot connecté', 'لا يوجد بوت متصل')}</p>
            </div>
          </div>
          <button onClick={onClose} aria-label={t('Close', 'Fermer', 'إغلاق')} className="p-2 rounded-lg text-slate-400 hover:text-white cursor-pointer"><X className="w-4 h-4" /></button>
        </header>

        <div className="p-4 sm:p-5 space-y-4">
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

          <Card isLight={isLight} icon={<KeyRound className="w-4 h-4" />} title={t('Connection', 'Connexion', 'الاتصال')}>
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label={cfg?.hasBotToken ? t(`Bot token (saved: ${cfg.botTokenMasked})`, `Token (enregistré : ${cfg.botTokenMasked})`, `التوكن (محفوظ: ${cfg.botTokenMasked})`) : t('Bot token from @BotFather', 'Token de @BotFather', 'توكن من @BotFather')}>
                <div className="flex gap-2">
                  <input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} placeholder="123456:ABC…" className={inputCls(isLight)} />
                  <Button onClick={connectBot} disabled={busy || token.trim().length < 20}>{t('Connect', 'Connecter', 'ربط')}</Button>
                </div>
              </Field>
              <Field label={t('Admin chat id (always receives signals)', 'Chat id admin (reçoit toujours)', 'معرف محادثة المشرف')}>
                <div className="flex gap-2">
                  <input value={cfg?.chatId ?? ''} onChange={e => cfg && setCfg({ ...cfg, chatId: e.target.value })} className={inputCls(isLight)} />
                  <Button variant="ghost" onClick={() => save({ chatId: cfg?.chatId ?? '' })} disabled={busy}>{t('Save', 'Enregistrer', 'حفظ')}</Button>
                </div>
              </Field>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="ghost" disabled={busy || !cfg?.hasBotToken} onClick={() => run(async () => {
                const r = await apiJson('/api/telegram/test', { method: 'POST', body: '{}' });
                if (!r.success) throw new Error(r.error);
                return t('Test message sent', 'Message test envoyé', 'تم إرسال رسالة الاختبار');
              })}><Send className="w-3.5 h-3.5" />{t('Send test', 'Envoyer un test', 'رسالة اختبار')}</Button>
              <Button variant="ghost" disabled={busy || !cfg?.hasBotToken} onClick={() => run(async () => {
                const r = await apiJson('/api/telegram/dispatch-now', { method: 'POST', body: '{}' });
                const lines = Object.entries(r.results as Record<string, { success: boolean; error?: string }>).map(([s, x]) => `${s}: ${x.success ? 'sent' : x.error}`);
                if (!r.success) throw new Error(lines.join(' · '));
                return lines.join(' · ');
              })}><Zap className="w-3.5 h-3.5" />{t('Send current signal now', 'Envoyer le signal actuel', 'إرسال الإشارة الحالية')}</Button>
            </div>
          </Card>

          <Card isLight={isLight} icon={<ShieldCheck className="w-4 h-4" />} title={t('Delivery and protection', 'Envoi et protection', 'الإرسال والحماية')}>
            {toggle('enabled', t('Send strategy signals automatically at candle close', 'Envoyer les signaux automatiquement à la clôture', 'إرسال الإشارات تلقائياً عند إغلاق الشمعة'))}
            {toggle('protectContent', t('Block forwarding / copying of signal messages', 'Bloquer le transfert / la copie', 'منع إعادة التوجيه والنسخ'))}
            {toggle('personalOffsets', t('Personal micro-offset + reference code per subscriber (anti copy-trading)', 'Micro-décalage personnel + code de référence (anti copy-trading)', 'إزاحة شخصية + رمز مرجعي لكل مشترك'))}
            <div className="flex gap-4 pt-2 text-xs">
              {ASSETS.map(a => (
                <label key={a} className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                  <input type="checkbox" className="accent-gold-500" checked={!!cfg?.assets.includes(a)}
                    onChange={e => cfg && save({ assets: e.target.checked ? [...cfg.assets, a] : cfg.assets.filter(x => x !== a) })} />{a}
                </label>
              ))}
            </div>
          </Card>

          <Card isLight={isLight} icon={<Users className="w-4 h-4" />} title={t('Subscribers and access codes', 'Abonnés et codes', 'المشتركون ورموز التفعيل')}
            right={<span className="text-xs text-slate-500">{subs.filter(s => s.active).length} {t('active', 'actifs', 'نشط')}</span>}>
            <div className="flex flex-wrap items-end gap-2 mb-3">
              <Field label={t('Duration', 'Durée', 'المدة')}>
                <select value={duration} onChange={e => setDuration(Number(e.target.value))} className={inputCls(isLight)}>
                  {DURATIONS.map(d => <option key={d.h} value={d.h}>{d.l}</option>)}
                </select>
              </Field>
              <Field label={t('Label', 'Libellé', 'الوصف')}><input value={label} onChange={e => setLabel(e.target.value)} className={inputCls(isLight)} /></Field>
              <Button disabled={busy} onClick={() => run(async () => {
                const r = await apiJson('/api/telegram/activation/generate', { method: 'POST', body: JSON.stringify({ durationHours: duration, label }) });
                await load();
                copy(r.code);
                return t(`Code ${r.code} created and copied. The subscriber sends it to the bot.`, `Code ${r.code} créé et copié. L'abonné l'envoie au bot.`, `تم إنشاء الرمز ${r.code} ونسخه. يرسله المشترك إلى البوت.`);
              })}>{t('New code', 'Nouveau code', 'رمز جديد')}</Button>
            </div>
            <div className="grid sm:grid-cols-2 gap-3 text-xs">
              <div className="space-y-1.5">
                {codes.slice(0, 12).map(c => (
                  <div key={c.code} className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 ${isLight ? 'border-paper-line' : 'border-line'} ${c.revoked ? 'opacity-40' : ''}`}>
                    <button onClick={() => copy(c.code)} className="font-mono text-gold-500 flex items-center gap-1 cursor-pointer">
                      {copied === c.code ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}{c.code}
                    </button>
                    <span className="text-slate-500">{Math.round(c.durationHours / 24)}d · {c.usedCount} {t('used', 'utilisé', 'استعمال')}</span>
                    {!c.revoked && <button aria-label="revoke" onClick={() => run(async () => { await apiJson(`/api/telegram/activation/${c.code}`, { method: 'DELETE' }); await load(); })} className="text-slate-500 hover:text-rose-500 cursor-pointer"><Trash2 className="w-3 h-3" /></button>}
                  </div>
                ))}
                {!codes.length && <p className="text-slate-500">{t('No codes yet.', 'Aucun code.', 'لا توجد رموز.')}</p>}
              </div>
              <div className="space-y-1.5">
                {subs.map(s => (
                  <div key={s.chatId} className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 ${isLight ? 'border-paper-line' : 'border-line'}`}>
                    <span className={s.active ? 'text-emerald-500' : 'text-slate-500'}>{s.firstName || s.chatId}</span>
                    <span className="text-slate-500">{s.active ? `→ ${fmtDate(s.expiresAt).slice(0, 10)}` : t('expired', 'expiré', 'منتهي')} · ${s.capital}</span>
                    <button aria-label="remove" onClick={() => run(async () => { await apiJson(`/api/telegram/subscribers/${s.chatId}`, { method: 'DELETE' }); await load(); })} className="text-slate-500 hover:text-rose-500 cursor-pointer"><Trash2 className="w-3 h-3" /></button>
                  </div>
                ))}
                {!subs.length && <p className="text-slate-500">{t('No subscriber yet.', 'Aucun abonné.', 'لا يوجد مشتركون.')}</p>}
              </div>
            </div>
          </Card>

          <Card isLight={isLight} title={t('Recent deliveries', 'Derniers envois', 'آخر الإرسالات')}>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <Stat isLight={isLight} label={t('Sent', 'Envoyés', 'ناجحة')} value={history.filter(h => h.status === 'SUCCESS').length} tone="good" />
              <Stat isLight={isLight} label={t('Failed', 'Échecs', 'فاشلة')} value={history.filter(h => h.status !== 'SUCCESS').length} tone="bad" />
            </div>
            <ul className="space-y-1 text-xs">
              {history.map(h => (
                <li key={h.id} className="flex gap-2">
                  <span className="font-mono text-slate-500">{h.sentAt}</span>
                  <span className={h.status === 'SUCCESS' ? 'text-emerald-500' : 'text-rose-500'}>{h.title}</span>
                  <span className="text-slate-500 truncate">{h.error || h.details}</span>
                </li>
              ))}
              {!history.length && <li className="text-slate-500">{t('Nothing sent since the server started.', 'Rien depuis le démarrage du serveur.', 'لا شيء منذ تشغيل الخادم.')}</li>}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
};
