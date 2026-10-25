import { apiFetch } from '../api';
import React, { useState, useEffect } from 'react';
import { MarketAsset, AISignal, RiskCalculationResult, Language } from '../types';
import { ShieldCheck, AlertTriangle, Calculator, DollarSign, Percent, Scale, CheckCircle2 } from 'lucide-react';

interface RiskCalculatorProps {
  asset: MarketAsset | null;
  prefillSignal: AISignal | null;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const RiskManagementCalculator: React.FC<RiskCalculatorProps> = ({
  asset,
  prefillSignal,
  lang,
  theme = 'light',
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const defaultPrice = asset?.price || 100;
  const decimals = asset?.decimalPlaces ?? 2;

  const [accountBalance, setAccountBalance] = useState<number>(1000);
  const [riskPercent, setRiskPercent] = useState<number>(1.0);
  const [entryPrice, setEntryPrice] = useState<number>(defaultPrice);
  const [stopLoss, setStopLoss] = useState<number>(Number((defaultPrice * 0.995).toFixed(decimals)));
  const [target1, setTarget1] = useState<number>(Number((defaultPrice * 1.01).toFixed(decimals)));
  const [target2, setTarget2] = useState<number>(Number((defaultPrice * 1.02).toFixed(decimals)));

  const [calcResult, setCalcResult] = useState<RiskCalculationResult | null>(null);

  // When asset changes and no prefill signal is active, calibrate prices
  useEffect(() => {
    if (asset && !prefillSignal) {
      setEntryPrice(asset.price);
      setStopLoss(Number((asset.price * 0.995).toFixed(asset.decimalPlaces ?? 2)));
      setTarget1(Number((asset.price * 1.01).toFixed(asset.decimalPlaces ?? 2)));
      setTarget2(Number((asset.price * 1.02).toFixed(asset.decimalPlaces ?? 2)));
    }
  }, [asset?.symbol]);

  // If user selected a signal from the signals section, prefill
  useEffect(() => {
    if (prefillSignal) {
      const parts = prefillSignal.entryZone.split('-').map((s) => parseFloat(s.replace(/,/g, '').trim()));
      const entry = parts[0] || (asset?.price ?? 100);
      setEntryPrice(entry);
      setStopLoss(prefillSignal.stopLoss);
      setTarget1(prefillSignal.target1);
      setTarget2(prefillSignal.target2);
    }
  }, [prefillSignal]);

  // Recalculate whenever inputs change
  useEffect(() => {
    const fetchCalc = async () => {
      try {
        const res = await apiFetch('/api/risk/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            accountBalance,
            riskPercent,
            entryPrice,
            stopLossPrice: stopLoss,
            target1Price: target1,
            target2Price: target2,
            symbol: asset?.symbol || 'XAU/USD',
          }),
        });
        if (res.ok) {
          const data = await res.json();
          setCalcResult(data);
        }
      } catch (err) {
        console.error('Failed to calculate risk:', err);
      }
    };
    fetchCalc();
  }, [accountBalance, riskPercent, entryPrice, stopLoss, target1, target2, asset?.symbol]);

  return (
    <div className={`rounded-2xl border p-5 shadow-sm transition-colors ${
      isLight ? 'bg-white border-paper-line-2' : 'bg-surface-2 border-line'
    }`}>
      {/* Header */}
      <div className={`flex items-center justify-between pb-4 mb-4 border-b ${
        isLight ? 'border-paper-line-2' : 'border-line'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-xl border flex items-center justify-center shadow-xs ${
            isLight ? 'bg-paper border-gold-200 text-gold-700' : 'bg-surface border-gold-700 text-gold-400'
          }`}>
            <Scale className="w-4 h-4" />
          </div>
          <div>
            <h3 className={`font-bold text-sm flex items-center gap-2 ${isLight ? 'text-ink-strong' : 'text-white'}`}>
              <span>{isFr ? 'Calculateur de Gestion du Risque (Desk 1% Rule)' : isAr ? 'حاسبة إدارة المخاطر المؤسساتية (1% Risk Rule)' : 'Institutional Risk Management Desk'}</span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
                isLight ? 'bg-paper text-gold-700 border-gold-200' : 'bg-surface-2 text-gold-400 border-gold-700'
              }`}>
                Capital Protection
              </span>
            </h3>
            <p className={`text-xs ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
              {isFr ? 'Dimensionnement automatique de la position et limite de perte stricte' : isAr ? 'تحديد حجم اللوت المناسب ونسبة المخاطرة وفق معادلات حسابية صارمة' : 'Automated position sizing and maximum loss limits'}
            </p>
          </div>
        </div>

        <div className={`text-xs font-mono-numbers font-bold px-2.5 py-1 rounded-lg border ${
          isLight ? 'bg-paper border-paper-line-2 text-gold-700' : 'bg-surface-3 border-line-2 text-gold-400'
        }`}>
          {asset?.symbol || 'XAU/USD'}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Form Inputs */}
        <div className="lg:col-span-6 space-y-3.5">
          <div>
            <label className={`block text-xs font-bold mb-1 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
              {isFr ? 'Solde du Compte ($)' : isAr ? 'رأس مال الحساب ($)' : 'Account Balance ($)'}
            </label>
            <input
              type="number"
              value={accountBalance}
              onChange={(e) => setAccountBalance(Math.max(1, Number(e.target.value)))}
              className={`w-full px-3.5 py-2 rounded-xl text-xs font-mono-numbers font-bold border focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                isLight ? 'bg-paper border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
              }`}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block text-xs font-bold mb-1 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                {isFr ? 'Risque par Trade (%)' : isAr ? 'نسبة المخاطرة (%)' : 'Risk Per Trade (%)'}
              </label>
              <input
                type="number"
                step="0.1"
                value={riskPercent}
                onChange={(e) => setRiskPercent(Math.max(0.1, Number(e.target.value)))}
                className={`w-full px-3.5 py-2 rounded-xl text-xs font-mono-numbers font-bold border focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                  isLight ? 'bg-paper border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                }`}
              />
            </div>

            <div>
              <label className={`block text-xs font-bold mb-1 ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                {isFr ? 'Prix d\'Entrée ($)' : isAr ? 'سعر الدخول ($)' : 'Entry Price ($)'}
              </label>
              <input
                type="number"
                step="any"
                value={entryPrice}
                onChange={(e) => setEntryPrice(Number(e.target.value))}
                className={`w-full px-3.5 py-2 rounded-xl text-xs font-mono-numbers font-bold border focus:outline-none focus:ring-2 focus:ring-gold-500 ${
                  isLight ? 'bg-paper border-paper-line-2 text-slate-900' : 'bg-surface border-line text-white'
                }`}
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-xs font-bold text-rose-600 mb-1">
                {isFr ? 'Stop Loss' : isAr ? 'وقف الخسارة' : 'Stop Loss'}
              </label>
              <input
                type="number"
                step="any"
                value={stopLoss}
                onChange={(e) => setStopLoss(Number(e.target.value))}
                className={`w-full px-2.5 py-1.5 rounded-xl text-xs font-mono-numbers font-bold border border-rose-500/30 ${
                  isLight ? 'bg-rose-50/50 text-rose-900' : 'bg-rose-950/20 text-rose-300'
                }`}
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-emerald-600 mb-1">
                {isFr ? 'TP1' : isAr ? 'الهدف 1' : 'TP1'}
              </label>
              <input
                type="number"
                step="any"
                value={target1}
                onChange={(e) => setTarget1(Number(e.target.value))}
                className={`w-full px-2.5 py-1.5 rounded-xl text-xs font-mono-numbers font-bold border border-emerald-500/30 ${
                  isLight ? 'bg-emerald-50/50 text-emerald-900' : 'bg-emerald-950/20 text-emerald-300'
                }`}
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-emerald-600 mb-1">
                {isFr ? 'TP2' : isAr ? 'الهدف 2' : 'TP2'}
              </label>
              <input
                type="number"
                step="any"
                value={target2}
                onChange={(e) => setTarget2(Number(e.target.value))}
                className={`w-full px-2.5 py-1.5 rounded-xl text-xs font-mono-numbers font-bold border border-emerald-500/30 ${
                  isLight ? 'bg-emerald-50/50 text-emerald-900' : 'bg-emerald-950/20 text-emerald-300'
                }`}
              />
            </div>
          </div>
        </div>

        {/* Calculation Output Card */}
        <div className={`lg:col-span-6 rounded-2xl border p-4.5 flex flex-col justify-between ${
          isLight ? 'bg-paper border-paper-line-2' : 'bg-surface border-line'
        }`}>
          {calcResult ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-paper-line-2 dark:border-line">
                <span className={`text-xs font-bold ${isLight ? 'text-slate-700' : 'text-slate-300'}`}>
                  {isFr ? 'Recommandation de Lot' : isAr ? 'حجم اللوت الموصى به' : 'Recommended Lot Size'}
                </span>
                <span className="text-xl font-black font-mono-numbers text-gold-700 dark:text-gold-400">
                  {calcResult.recommendedLotSize} Lots
                </span>
              </div>

              <div className="space-y-2 text-xs font-mono-numbers">
                <div className="flex justify-between">
                  <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>{isFr ? 'Perte Max à Risquer :' : isAr ? 'أقصى خسارة مقبولة:' : 'Max Risk Amount:'}</span>
                  <span className="font-bold text-rose-600 dark:text-rose-400">-${calcResult.maxLossDollars.toFixed(2)} ({calcResult.riskPercent}%)</span>
                </div>
                <div className="flex justify-between">
                  <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>{isFr ? 'Gain Potentiel TP1 :' : isAr ? 'الربح المتوقع TP1:' : 'Potential Profit TP1:'}</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">+${(calcResult.potentialProfitT1 ?? 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>{isFr ? 'Gain Potentiel TP2 :' : isAr ? 'الربح المتوقع TP2:' : 'Potential Profit TP2:'}</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">+${(calcResult.potentialProfitT2 ?? 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>{isFr ? 'Ratio Risque / Récompense :' : isAr ? 'العائد للمخاطرة R:R:' : 'Risk / Reward Ratio:'}</span>
                  <span className="font-bold text-gold-700 dark:text-gold-400">{calcResult.riskRewardRatio}</span>
                </div>
              </div>

              <div className={`p-2.5 rounded-xl border text-xs flex items-center gap-2 ${
                isLight ? 'bg-emerald-50 text-emerald-900 border-emerald-200' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50'
              }`}>
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{isFr ? 'Règle de 1% respectée : votre capital est protégé sans modifier le Stop Loss.' : isAr ? 'قاعدة 1% مطبقة بدقة: حسابك محمي بالكامل ووقف الخسارة ثابت في مكانه دون أي تغيير.' : '1% rule strictly applied: capital protected, Stop Loss strictly preserved.'}</span>
              </div>

              {/* Telegram Bot Sync Card */}
              <div className={`p-2.5 rounded-xl border text-xs ${
                isLight ? 'bg-sky-50/70 border-sky-200 text-sky-950' : 'bg-sky-950/30 border-sky-800/50 text-sky-200'
              }`}>
                <div className="font-bold flex items-center justify-between">
                  <span>{isFr ? 'Système Bot Telegram (Calcul Instantané) :' : isAr ? 'نظام تيليجرام الذكي لحساب اللوت التلقائي:' : 'Telegram Bot Lot Sizing System:'}</span>
                  <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-600 dark:text-sky-300">/capital & /risk</span>
                </div>
                <p className="mt-1 opacity-90 leading-relaxed">
                  {isFr
                    ? 'Envoyez simplement votre capital et risque sur Telegram (ex: /capital 5000 ou 3ndi 5000$ bghit nriski 1%) et le bot calculera le lot exact pour chaque trade.'
                    : isAr
                    ? 'أرسل رأس مالك ونسبة المخاطرة مباشرة في التيليجرام (مثال: /capital 5000 أو 3ndi 5000$ bghit nriski 1%) وسيقوم البوت بحساب اللوت الصارم لكل صفقة فورياً دون لمس الستوب.'
                    : 'Send your capital & risk to Telegram bot (e.g. /capital 5000 or /risk 1%), and the bot will calculate the exact lot size for every trade without touching Stop Loss.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-xs text-slate-400">
              {isFr ? 'Calcul des paramètres...' : isAr ? 'جاري الحساب...' : 'Calculating...'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
