import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Activity, 
  BarChart2, 
  Sparkles, 
  TrendingUp, 
  Briefcase, 
  History, 
  Trophy, 
  Calculator, 
  Send, 
  Settings, 
  X, 
  ShieldCheck, 
  Radio
} from 'lucide-react';
import { Language } from '../types';
import { LiquidityDissectionLogo } from './LiquidityDissectionLogo';

interface ToolsSidebarDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: string;
  onSelectTab: (tabId: string) => void;
  lang: Language;
  theme?: 'light' | 'dark';
  activeSignalsCount?: number;
  onOpenTelegram: () => void;
}

export const ToolsSidebarDrawer: React.FC<ToolsSidebarDrawerProps> = ({
  isOpen,
  onClose,
  activeTab,
  onSelectTab,
  lang,
  theme = 'dark',
  activeSignalsCount = 0,
  onOpenTelegram,
}) => {
  const isAr = lang === 'ar';
  const isFr = lang === 'fr';
  const isLight = theme === 'light';

  const navItems = [
    {
      id: 'overview',
      labelAr: 'لوحة التحكم الشاملة',
      labelFr: 'Accueil (Overview)',
      labelEn: 'Overview',
      descAr: 'ملخص السوق الحية والتحليل والذكاء الاصطناعي',
      descFr: 'Vue d\'ensemble, prix spot & statut du marché',
      descEn: 'Live spot price, market status & signal overview',
      icon: Activity,
    },
    {
      id: 'chart',
      labelAr: 'الشارت (ذهب ويورو)',
      labelFr: 'Graphique (XAUUSD & EURUSD)',
      labelEn: 'Chart (XAUUSD & EURUSD)',
      descAr: 'شارت تفكيك السيولة BSL/SSL وكتل الأوامر',
      descFr: 'Cartographie temps réel Order Blocks & FVG',
      descEn: 'Real-time order flow dissection & liquidity sweeps',
      icon: BarChart2,
    },
    {
      id: 'analysis',
      labelAr: 'الاستراتيجيات (الذهب واليورو)',
      labelFr: 'Stratégies (XAUUSD & EURUSD)',
      labelEn: 'Strategies (XAUUSD & EURUSD)',
      descAr: 'الذهب: اختراق H1 مع الاتجاه · اليورو: رجوع مع الترند',
      descFr: 'Or : breakout H1 avec la tendance · EURUSD : pullback de tendance',
      descEn: 'Gold: H1 trend breakout · EURUSD: trend pullback',
      icon: Sparkles,
    },
    {
      id: 'positions',
      labelAr: 'صفقاتي المفتوحة',
      labelFr: 'Mes trades ouverts',
      labelEn: 'My open trades',
      descAr: 'الصفقات التي دخلتها، إغلاقها ونقل الوقف',
      descFr: 'Trades pris, clôture et breakeven',
      descEn: 'Trades you took, close and breakeven',
      icon: Briefcase,
    },
    {
      id: 'history',
      labelAr: 'سجل الصفقات (Trade History)',
      labelFr: 'Historique des Trades',
      labelEn: 'Trade History',
      descAr: 'صفقاتك المغلقة، الربح والخسارة ونسبة النجاح',
      descFr: 'Vos trades clôturés, P&L et taux de réussite',
      descEn: 'Your closed trades, P&L and win rate',
      icon: History,
    },
    {
      id: 'performance',
      labelAr: 'تحليل الأداء (Performance)',
      labelFr: 'Performance Analytics',
      labelEn: 'Performance Analytics',
      descAr: 'نسبة النجاح الفعلي، عامل الربح، والـ Drawdown',
      descFr: 'Win rate réel, profit factor & drawdown max',
      descEn: 'Real win rate, profit factor & max drawdown audit',
      icon: Trophy,
    },
    {
      id: 'telegram',
      labelAr: 'إعدادات تيليجرام (Telegram)',
      labelFr: 'Configuration Telegram',
      labelEn: 'Telegram Settings',
      descAr: 'ربط البوت الآلي وحفظ التوكن بشكل آمن',
      descFr: 'Bot token sécurisé, dispatch & anti-doublon',
      descEn: 'Secure bot token storage & event-driven dispatch',
      icon: Send,
    },
    {
      id: 'settings',
      labelAr: 'الحساب والإعدادات',
      labelFr: 'Compte & paramètres',
      labelEn: 'Account & settings',
      descAr: 'رأس المال، المستخدمون وإعدادات التطبيق',
      descFr: 'Capital, utilisateurs et paramètres',
      descEn: 'Capital, users and app parameters',
      icon: Settings,
    },
  ];

  const handleSelect = (tabId: string) => {
    if (tabId === 'telegram') {
      onOpenTelegram();
    } else {
      onSelectTab(tabId);
    }
    onClose();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/70 backdrop-blur-xs z-50 transition-opacity"
          />

          {/* Drawer Panel */}
          <motion.div
            initial={{ x: isAr ? 350 : -350, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: isAr ? 350 : -350, opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={`fixed top-0 bottom-0 ${isAr ? 'right-0' : 'left-0'} w-[85vw] max-w-sm sm:w-92 z-50 shadow-2xl flex flex-col border-r transition-colors ${
              isLight
                ? 'bg-white border-paper-line-2 text-ink-strong'
                : 'bg-surface border-white/[0.08] text-white'
            }`}
          >
            {/* Header */}
            <div className={`p-4 border-b flex items-center justify-between ${
              isLight ? 'bg-paper border-paper-line-2' : 'bg-surface-2 border-white/[0.08]'
            }`}>
              <LiquidityDissectionLogo size="sm" withText={true} />
              <button
                onClick={onClose}
                className={`p-2 rounded-xl border transition cursor-pointer ${
                  isLight
                    ? 'bg-white border-paper-line-2 hover:bg-slate-100 text-slate-600'
                    : 'bg-surface-3 border-white/[0.08] hover:bg-surface-3 text-zinc-300'
                }`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Navigation List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
              <div className="text-xs font-bold uppercase tracking-wider text-zinc-500 px-3 pb-2">
                {isAr ? 'تنقلات منصة تداول الذهب (Gold XAU/USD)' : 'Gold Trading Terminal Navigation'}
              </div>

              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                let label = item.labelEn;
                if (isAr) label = item.labelAr;
                else if (isFr) label = item.labelFr;

                let desc = item.descEn;
                if (isAr) desc = item.descAr;
                else if (isFr) desc = item.descFr;

                return (
                  <button
                    key={item.id}
                    onClick={() => handleSelect(item.id)}
                    className={`w-full text-left p-3 rounded-xl transition-all flex items-start gap-3 cursor-pointer border ${
                      isActive
                        ? isLight
                          ? 'bg-paper text-gold-700 border-gold-500 shadow-xs'
                          : 'bg-surface-3 text-gold-400 border-gold-500/40 shadow-sm'
                        : isLight
                        ? 'hover:bg-slate-50 text-slate-700 border-transparent'
                        : 'hover:bg-surface-3 text-zinc-300 border-transparent hover:border-white/[0.06]'
                    }`}
                  >
                    <div className={`p-2 rounded-lg mt-0.5 shrink-0 ${
                      isActive ? 'bg-gold-500 text-ink-strong' : 'bg-white/[0.04] text-zinc-400'
                    }`}>
                      <Icon className="w-4 h-4" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-extrabold text-xs tracking-tight truncate">{label}</span>
                      </div>
                      <p className="text-xs text-zinc-400 truncate mt-0.5">{desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Footer */}
            <div className={`p-4 border-t text-xs ${
              isLight ? 'bg-paper border-paper-line-2 text-slate-600' : 'bg-surface-2 border-white/[0.08] text-zinc-400'
            }`}>
              <div className="flex items-center gap-2 font-bold text-gold-500">
                <ShieldCheck className="w-4 h-4" />
                <span>Gold Sovereign 1% Risk Enforced</span>
              </div>
              <p className="text-xs text-zinc-500 mt-1">
                Professional XAU/USD Quantitative Execution & Event-Driven Telegram Dispatch.
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
