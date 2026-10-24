import React, { useState, useEffect } from 'react';
import {
  Key,
  ShieldCheck,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  Sparkles,
  PlusCircle,
  RefreshCw,
  Zap,
  Info,
  Send,
  Calendar,
  Lock,
  Users,
  UserCheck,
  UserX,
} from 'lucide-react';

interface ActivationManagerProps {
  onCodeApplied?: () => void;
  lang: 'ar' | 'en' | 'fr';
  theme?: 'light' | 'dark';
}

export const ActivationManager: React.FC<ActivationManagerProps> = ({
  onCodeApplied,
  lang,
  theme = 'light',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const [inputCode, setInputCode] = useState('');
  const [activeLicense, setActiveLicense] = useState<any>(null);
  const [generatedCodes, setGeneratedCodes] = useState<any[]>([]);
  const [subscribers, setSubscribers] = useState<any[]>([]);
  const [durationHours, setDurationHours] = useState<number>(168); // default 7 days
  const [codeLabel, setCodeLabel] = useState<string>('Liquidity Dissection VIP');

  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [feedback, setFeedback] = useState<{ success: boolean; message: string } | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      setIsLoading(true);
      const res = await fetch('/api/telegram/activation/status');
      if (res.ok) {
        const data = await res.json();
        setActiveLicense(data.activeLicense);
        setGeneratedCodes(data.generatedCodes || []);
        setSubscribers(data.subscribers || []);
      }
    } catch (err) {
      console.error('Error loading activation status:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleApplyCode = async (codeToUse?: string) => {
    const code = codeToUse || inputCode;
    if (!code || !code.trim()) {
      setFeedback({
        success: false,
        message: isFr ? 'Veuillez entrer une clé d\'activation !' : isAr ? 'يرجى إدخال كود التفعيل أولاً!' : 'Please enter an activation code first!',
      });
      return;
    }

    try {
      setIsLoading(true);
      const res = await fetch('/api/telegram/activation/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim() }),
      });
      const data = await res.json();
      setFeedback({
        success: data.success,
        message: data.message,
      });

      if (data.success) {
        setInputCode('');
        fetchStatus();
        if (onCodeApplied) onCodeApplied();
      }
    } catch (err: any) {
      setFeedback({
        success: false,
        message: isFr ? 'Échec de la validation de la clé.' : isAr ? 'حدث خطأ أثناء الاتصال بالخادم.' : 'Connection error occurred.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerate = async () => {
    try {
      setIsGenerating(true);
      const res = await fetch('/api/telegram/activation/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ durationHours, label: codeLabel }),
      });
      const data = await res.json();
      if (data.success) {
        fetchStatus();
        setFeedback({
          success: true,
          message: isFr ? `Clé ${data.code.code} générée avec succès !` : isAr ? `تم توليد الكود ${data.code.code} بنجاح!` : `Generated code ${data.code.code} successfully!`,
        });
      }
    } catch (err: any) {
      setFeedback({
        success: false,
        message: isFr ? 'Erreur de génération' : isAr ? 'تعذر توليد الكود' : 'Failed to generate code',
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Active License Overview */}
      <div className={`p-4.5 rounded-2xl border ${
        isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
      }`}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gold-500/15 text-gold-700 dark:text-gold-400 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h4 className={`text-xs font-black uppercase tracking-wider ${isLight ? 'text-ink-strong' : 'text-white'}`}>
                {isFr ? 'Statut de Licence Desk' : isAr ? 'حالة اشتراك المكتب الخاص' : 'Private Desk License Status'}
              </h4>
              <span className="text-xs text-slate-500">
                {activeLicense?.isActive
                  ? (isFr ? 'Accès VIP Illimité Actif' : isAr ? 'وصول VIP نشط' : 'Active VIP Access')
                  : (isFr ? 'Licence Standard' : isAr ? 'وصول قياسي' : 'Standard Access')}
              </span>
            </div>
          </div>

          <span className={`text-xs font-black px-2.5 py-1 rounded-full border ${
            activeLicense?.isActive
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
              : 'bg-paper text-gold-700 border-gold-200 dark:bg-surface dark:text-gold-400 dark:border-gold-700'
          }`}>
            {activeLicense?.tier || 'VIP Institutional'}
          </span>
        </div>

        {/* Enter Code Input */}
        <div className="flex items-center gap-2 mt-3">
          <input
            type="text"
            value={inputCode}
            onChange={(e) => setInputCode(e.target.value.toUpperCase())}
            placeholder={isFr ? "Entrez votre clé VIP..." : isAr ? "أدخل كود التفعيل VIP..." : "Enter VIP License Key..."}
            className={`flex-1 px-3.5 py-2 rounded-xl text-xs font-mono-numbers font-bold border focus:outline-none focus:ring-2 focus:ring-gold-500 ${
              isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface-2 border-line text-white'
            }`}
          />
          <button
            onClick={() => handleApplyCode()}
            disabled={isLoading || !inputCode.trim()}
            className="px-4 py-2 rounded-xl bg-gold-500 hover:bg-gold-500 text-ink-strong font-black text-xs transition cursor-pointer disabled:opacity-50"
          >
            {isFr ? 'Activer' : isAr ? 'تفعيل الكود' : 'Activate'}
          </button>
        </div>

        {feedback && (
          <div className={`mt-3 p-2.5 rounded-xl text-xs font-bold border ${
            feedback.success
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800'
              : 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800'
          }`}>
            {feedback.message}
          </div>
        )}
      </div>

      {/* Permanent Master VIP Codes from db.json */}
      <div className={`p-4.5 rounded-2xl border ${
        isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
      }`}>
        <div className="flex items-center justify-between mb-2.5 pb-2 border-b border-paper-line-2 dark:border-line">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-gold-500" />
            <h4 className={`text-xs font-black uppercase tracking-wider ${isLight ? 'text-slate-900' : 'text-white'}`}>
              {isFr ? 'Clés VIP Permanentes dans db.json (Toujours Actives)' : isAr ? 'أكواد VIP الدائمة المحفوظة في db.json (شغالة دائمـاً)' : 'Permanent VIP Codes in db.json'}
            </h4>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-gold-500/15 text-gold-700 dark:text-gold-400">
            {isAr ? '10 سنوات • حماية من إعادة التشغيل' : '10 Years Lifetime • Persistent'}
          </span>
        </div>

        <p className="text-xs text-slate-500 mb-3 leading-relaxed">
          {isFr 
            ? 'Ces clés VIP sont écrites de manière permanente dans data/db.json. Même après redémarrage du serveur, vos utilisateurs continuent de recevoir les alertes Telegram sans aucune interruption.'
            : isAr
            ? 'هذه الأكواد مكتوبة ومحفوظة بشكل دائم داخل ملف data/db.json. حتى لو انطفأ السيرفر أو أُعيد تشغيل التطبيق، تبقى الأكواد والمشتركون شغالين دائماً وتصلهم تنبيهات التيليجرام بدون انقطاع.'
            : 'These VIP keys are permanently saved inside data/db.json. Even if the server restarts, subscribers will permanently receive Telegram signals without disruption.'}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {[
            { code: 'PRO-TRADER-2026-VIP', label: isAr ? 'كود الماستر VIP الشامل' : 'Master Lifetime VIP' },
            { code: 'VIP-7777-2026', label: isAr ? 'اشتراك كبار المتداولين' : 'VIP Master Pass' },
            { code: 'VIP-FOREVER-2026', label: isAr ? 'وصول دائم غير محدود' : 'VIP Forever Pass' },
            { code: 'VIP-LIFETIME-PASS', label: isAr ? 'مفتاح لايف تايم دائم' : 'Lifetime Key' },
            { code: 'VIP-TRADING-PRO', label: isAr ? 'كود المحترفين Pro' : 'Pro Trader VIP' },
            { code: 'VIP-ALFRED-MILKER', label: isAr ? 'كود الحساب الرئيسي' : 'Alfred Milker Master' },
          ].map((item) => (
            <div
              key={item.code}
              className={`p-2.5 rounded-xl border flex items-center justify-between gap-2 text-xs ${
                isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
              }`}
            >
              <div>
                <div className="flex items-center gap-1.5 font-mono font-bold text-gold-700 dark:text-gold-400">
                  <span>{item.code}</span>
                  <span className="text-xs px-1 py-0.2 rounded bg-emerald-500/10 text-emerald-500 font-sans font-bold">
                    {isAr ? 'دائم 10س' : '10y'}
                  </span>
                </div>
                <span className="text-xs text-slate-400 block mt-0.5">{item.label}</span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(item.code);
                    setCopiedCode(item.code);
                    setTimeout(() => setCopiedCode(null), 2000);
                  }}
                  className={`p-1.5 rounded-lg border text-xs font-bold transition cursor-pointer ${
                    copiedCode === item.code
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : isLight ? 'bg-slate-100 hover:bg-slate-200 border-slate-200 text-slate-700' : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-300'
                  }`}
                  title="نسخ الكود"
                >
                  {copiedCode === item.code ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                </button>

                <button
                  type="button"
                  onClick={() => handleApplyCode(item.code)}
                  className="px-2 py-1 rounded-lg bg-gold-500 hover:bg-gold-500 text-ink-strong font-bold text-xs transition cursor-pointer"
                  title="تفعيل هذا الكود فوراً"
                >
                  {isAr ? 'تفعيل' : 'Apply'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Admin Generator Section */}
      <div className={`p-4.5 rounded-2xl border ${
        isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
      }`}>
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-paper-line-2 dark:border-line">
          <span className={`text-xs font-bold ${isLight ? 'text-slate-800' : 'text-slate-200'}`}>
            {isFr ? 'Générateur de Clés VIP (Admin)' : isAr ? 'توليد أكواد VIP للمشتركين' : 'VIP License Generator'}
          </span>
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-xl bg-gold-500 hover:bg-gold-500 text-ink-strong transition cursor-pointer disabled:opacity-50"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>{isFr ? 'Générer' : isAr ? 'توليد كود' : 'Generate'}</span>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">
              {isFr ? 'Durée (Heures)' : isAr ? 'المدة (بالساعات)' : 'Duration (Hours)'}
            </label>
            <select
              value={durationHours}
              onChange={(e) => setDurationHours(Number(e.target.value))}
              className={`w-full px-3 py-1.5 rounded-xl text-xs font-bold border ${
                isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface-2 border-line text-white'
              }`}
            >
              <option value={24}>24 {isFr ? 'Heures (1 jour)' : isAr ? 'ساعة (يوم واحد)' : 'Hours (1 Day)'}</option>
              <option value={168}>168 {isFr ? 'Heures (7 jours)' : isAr ? 'ساعة (7 أيام)' : 'Hours (7 Days)'}</option>
              <option value={720}>720 {isFr ? 'Heures (1 mois)' : isAr ? 'ساعة (شهر كامل)' : 'Hours (30 Days)'}</option>
              <option value={8760}>8760 {isFr ? 'Heures (1 an)' : isAr ? 'ساعة (سنة كاملة)' : 'Hours (1 Year)'}</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">
              {isFr ? 'Description' : isAr ? 'الوصف / التسمية' : 'Label'}
            </label>
            <input
              type="text"
              value={codeLabel}
              onChange={(e) => setCodeLabel(e.target.value)}
              className={`w-full px-3 py-1.5 rounded-xl text-xs font-bold border ${
                isLight ? 'bg-white border-paper-line-2 text-slate-900' : 'bg-surface-2 border-line text-white'
              }`}
            />
          </div>
        </div>

        {/* Existing Generated Codes */}
        {generatedCodes.length > 0 && (
          <div className="mt-3.5 space-y-1.5">
            <span className="text-xs font-bold text-slate-500">{isFr ? 'Dernières clés générées :' : isAr ? 'الأكواد المولدة مؤخراً:' : 'Recent Keys:'}</span>
            <div className="max-h-36 overflow-y-auto space-y-1">
              {generatedCodes.map((c, i) => (
                <div
                  key={i}
                  className={`p-2 rounded-xl border flex items-center justify-between text-xs font-mono-numbers ${
                    isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
                  }`}
                >
                  <span className="font-bold text-gold-700 dark:text-gold-400">{c.code}</span>
                  <span className="text-xs text-slate-400">{c.durationHours}h • {c.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
