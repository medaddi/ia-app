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

  // 10 Required Navigation Tabs
  const navItems = [
    {
      id: 'overview',
      labelAr: '1. لوحة التحكم الشاملة',
      labelFr: '1. Accueil (Overview)',
      labelEn: '1. Overview',
      descAr: 'ملخص السوق الحية والتحليل والذكاء الاصطناعي',
      descFr: 'Vue d\'ensemble, prix spot & statut du marché',
      descEn: 'Live spot price, market status & signal overview',
      icon: Activity,
    },
    {
      id: 'chart',
      labelAr: '2. شارت الذهب (Gold Chart)',
      labelFr: '2. Graphique Or (SMC)',
      labelEn: '2. Gold Chart',
      descAr: 'شارت تفكيك السيولة BSL/SSL وكتل الأوامر',
      descFr: 'Cartographie temps réel Order Blocks & FVG',
      descEn: 'Real-time order flow dissection & liquidity sweeps',
      icon: BarChart2,
    },
    {
      id: 'analysis',
      labelAr: '3. استراتيجية نيويورك (NY Silver Bullet)',
      labelFr: '3. Stratégie NY Silver Bullet',
      labelEn: '3. NY Silver Bullet Strategy',
      descAr: 'تحضير سيولة M15 وتنفيذ أمر معلق 50% CE على فريم M5',
      descFr: 'Préparation liquidité M15 & exécution limit 50% CE sur M5',
      descEn: 'M15 liquidity preparation & M5 50% CE limit execution',
      icon: Sparkles,
    },
    {
      id: 'signals',
      labelAr: '4. إشارات التداول (Trade Signals)',
      labelFr: '4. Signaux de Trading',
      labelEn: '4. Trade Signals',
      descAr: 'الصفقات المؤكدة بنسبة 80%+ مع شمعة التأكيد',
      descFr: 'Opportunités A+ validées avec confirmation 15M',
      descEn: 'High-probability A+ setups & confirmation rules',
      icon: TrendingUp,
      badge: activeSignalsCount > 0 ? `${activeSignalsCount} active` : undefined,
    },
    {
      id: 'positions',
      labelAr: '5. الصفقات المفتوحة (Open Positions)',
      labelFr: '5. Positions Ouvertes',
      labelEn: '5. Open Positions',
      descAr: 'متابعة الصفقات النشطة وتنفيذ البروكر بالمليمتر',
      descFr: 'Suivi tick-par-tick des contrats engagés',
      descEn: 'Active trade tracking & broker execution desk',
      icon: Briefcase,
    },
    {
      id: 'history',
      labelAr: '6. سجل الصفقات (Trade History)',
      labelFr: '6. Historique des Trades',
      labelEn: '6. Trade History',
      descAr: 'السجل الكامل لجميع الصفقات وأهداف TP و SL',
      descFr: 'Registre transparent de tous les TP & SL touchés',
      descEn: 'Transparent ledger of all hit TP and SL levels',
      icon: History,
    },
    {
      id: 'performance',
      labelAr: '7. تحليل الأداء (Performance)',
      labelFr: '7. Performance Analytics',
      labelEn: '7. Performance Analytics',
      descAr: 'نسبة النجاح الفعلي، عامل الربح، والـ Drawdown',
      descFr: 'Win rate réel, profit factor & drawdown max',
      descEn: 'Real win rate, profit factor & max drawdown audit',
      icon: Trophy,
    },
    {
      id: 'risk',
      labelAr: '8. إدارة المخاطر (Risk Management)',
      labelFr: '8. Gestion du Risque (1%)',
      labelEn: '8. Risk Management',
      descAr: 'حساب اللوت الدقيق وقاعدة 1% لحماية رأس المال',
      descFr: 'Calculateur de lot & règle stricte de 1%',
      descEn: 'Lot size calculator & 1% portfolio risk protection',
      icon: Calculator,
    },
    {
      id: 'telegram',
      labelAr: '9. إعدادات تيليجرام (Telegram)',
      labelFr: '9. Configuration Telegram',
      labelEn: '9. Telegram Settings',
      descAr: 'ربط البوت الآلي وحفظ التوكن بشكل آمن',
      descFr: 'Bot token sécurisé, dispatch & anti-doublon',
      descEn: 'Secure bot token storage & event-driven dispatch',
      icon: Send,
    },
    {
      id: 'settings',
      labelAr: '10. إعدادات النظام (System Settings)',
      labelFr: '10. Paramètres Système',
      labelEn: '10. System Settings',
      descAr: 'فحص التخزين السحابي وصحة خادم الذهب الفوري',
      descFr: 'Santé infrastructure, persistance & cache',
      descEn: 'Infrastructure health, cloud sync & persistence',
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
                        {item.badge && (
                          <span className="text-xs font-black px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">
                            {item.badge}
                          </span>
                        )}
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
