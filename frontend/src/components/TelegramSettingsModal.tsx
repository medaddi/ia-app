import React, { useEffect, useState } from 'react';
import { INSTRUMENT_SYMBOLS } from '../instruments';
import { Bot, KeyRound, Send, ShieldCheck, Trash2, Users, X, Zap } from 'lucide-react';
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
interface Sub { chatId: string; username: string; firstName: string; active: boolean; muted: boolean }

const ASSETS: readonly string[] = INSTRUMENT_SYMBOLS;

/** Admin settings of the Telegram bot. The bot token is stored on the server only and never sent back to the browser. */
export const TelegramSettingsModal: React.FC<TelegramSettingsModalProps> = ({ isOpen, onClose, lang, theme = 'dark' }) => {
  const isLight = theme === 'light';
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [token, setToken] = useState('');
  const [botName, setBotName] = useState<string | null>(null);
  const [history, setHistory] = useState<LogRow[]>([]);
  const [subs, setSubs] = useState<Sub[]>([]);
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
      const [c, s] = await Promise.all([apiJson('/api/telegram/config'), apiJson('/api/telegram/subscribers')]);
      setCfg(c.config);
      setHistory(c.history || []);
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
        className={`w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded-2xl border shadow-2xl ${isLight ? 'bg-paper border-paper-line-2' : 'glass-strong'}`}>
        <header className={`sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b ${isLight ? 'bg-paper border-paper-line-2' : 'bg-[rgb(16_19_26/0.92)] border-line'}`}>
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
              <Field label={t('Admin chat id', 'Chat id admin', 'معرف محادثة المشرف')}>
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
            </div>
          </Card>

          <Card isLight={isLight} icon={<Users className="w-4 h-4" />} title={t('Accounts linked to Telegram', 'Comptes liés à Telegram', 'الحسابات المربوطة بتيليغرام')}
            right={<span className="text-xs text-slate-500">{subs.filter(s => s.active).length} {t('linked', 'liés', 'مربوطين')}</span>}>
            <div className="grid sm:grid-cols-2 gap-1.5 text-xs">
              {subs.map(s => (
                <div key={s.chatId} className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 ${isLight ? 'border-paper-line' : 'border-line'}`}>
                  <span className="min-w-0 truncate"><span className={s.active ? 'text-emerald-500 font-semibold' : 'text-slate-500'}>● {s.username}</span>
                    {s.firstName && <span className="text-slate-500"> · {s.firstName}</span>}{s.muted && <span className="text-gold-400"> · {t('paused', 'en pause', 'موقوف')}</span>}</span>
                  <button aria-label={t('Unlink', 'Délier', 'فك')} onClick={() => run(async () => { await apiJson(`/api/telegram/subscribers/${s.chatId}`, { method: 'DELETE' }); await load(); })} className="text-slate-500 hover:text-rose-500 cursor-pointer"><Trash2 className="w-3 h-3" /></button>
                </div>
              ))}
              {!subs.length && <p className="text-slate-500">{t('No account linked yet: each user presses Start in the bot and accepts in the app.', 'Aucun compte lié : chaque utilisateur appuie sur Démarrer dans le bot puis accepte dans l’app.', 'حتى حساب ما مربوط: كل مستخدم كيضغط Start ف البوت ومن بعد كيقبل ف التطبيق.')}</p>}
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
