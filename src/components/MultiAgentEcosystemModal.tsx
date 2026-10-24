import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  X,
  Bot,
  Layers,
  Shield,
  Activity,
  Send,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  Cpu,
  RefreshCw,
  MessageSquare,
  Sparkles,
  Zap,
  Target,
  BarChart2,
  Code
} from 'lucide-react';
import { Language } from '../types';

interface MultiAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
  theme?: 'light' | 'dark';
}

export const MultiAgentEcosystemModal: React.FC<MultiAgentModalProps> = ({
  isOpen,
  onClose,
  lang,
  theme = 'light'
}) => {
  const isAr = lang === 'ar';
  const isLight = theme === 'light';

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [data, setData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'CREW_AGENTS' | 'DIALOGUE' | 'CTO_JSON'>('CREW_AGENTS');

  const fetchCrewEcosystem = async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/agents/crewai?symbol=XAU/USD');
      const json = await res.json();
      if (json.success && json.crewai) {
        setData(json.crewai);
      }
    } catch (err) {
      console.error('Failed to load CrewAI ecosystem:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchCrewEcosystem();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const agentsList = [
    {
      id: 'agent1',
      num: 1,
      title: isAr ? 'الوكيل 1: محلل هيكل السوق (Market Structure Analyst)' : 'Agent 1: Market Structure Analyst',
      roleAr: 'يقوم بفحص الاتجاه العام (BULLISH/BEARISH)، كسر الهيكل BOS، وتغير السلوك CHoCH.',
      roleEn: 'Analyzes primary market trend, Break of Structure (BOS), and Change of Character (CHoCH).',
      color: 'indigo',
      badge: 'Structure Specialist',
      output: data?.agents?.market_structure_analyst
    },
    {
      id: 'agent2',
      num: 2,
      title: isAr ? 'الوكيل 2: صائد السيولة ومناطق العرض والطلب (Liquidity & Zones Analyst)' : 'Agent 2: Liquidity & Zones Analyst',
      roleAr: 'يكتشف كتل الطلب والسيولة Institutional Order Blocks، الفجوات السعرية FVG، وسحب سيولة BSL/SSL.',
      roleEn: 'Locates Order Blocks, Fair Value Gaps (FVG), and Buy/Sell-side liquidity sweeps.',
      color: 'emerald',
      badge: 'Liquidity Hunter',
      output: data?.agents?.liquidity_zones_analyst
    },
    {
      id: 'agent3',
      num: 3,
      title: isAr ? 'الوكيل 3: مدير المخاطرة وإدارة رأس المال (Risk Manager)' : 'Agent 3: Risk Manager',
      roleAr: 'يحسب الدخول الدقيق، الستوب لوس الهيكلي SL، الأهداف TP1 و TP2، نسبة R:R >= 1:2.0 إجبارية وحجم اللوت المناسب.',
      roleEn: 'Calculates exact Entry, SL, TP1, TP2, mandatory R:R >= 1:2.0, and risk position sizing.',
      color: 'blue',
      badge: 'Risk Manager',
      output: data?.agents?.risk_manager
    },
    {
      id: 'agent4',
      num: 4,
      title: isAr ? 'الوكيل 4: رئيس قسم التداول والمصادقة (Chief Trading Officer - CTO)' : 'Agent 4: Chief Trading Officer (CTO)',
      roleAr: 'يدقق شروط الوكلاء 1 و 2 و 3، يفرض نسبة توافق >= 85%، ويخرج التقرير النهائي بفرمتة JSON المعتمدة.',
      roleEn: 'Audits inputs, verifies >=85% confluence score, and outputs final confirmed setup in JSON.',
      color: 'purple',
      badge: 'Final Authority',
      output: data?.agents?.chief_trading_officer
    },
    {
      id: 'agent5',
      num: 5,
      title: isAr ? 'الوكيل 5: مرسل إشعارات التيليجرام الفورية (Telegram Dispatcher)' : 'Agent 5: Telegram Dispatcher',
      roleAr: 'يستلم اعتماد الـ CTO وصياغة الرسالة الفورية مع أزرار التحكم التفاعلية لتيليجرام بدون أي تأخير.',
      roleEn: 'Dispatches zero-lag interactive alerts to Telegram with buttons upon CTO green light.',
      color: 'sky',
      badge: 'Telegram Dispatcher',
      output: data?.agents?.telegram_dispatcher
    }
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className={`w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl border shadow-2xl overflow-hidden ${
          isLight ? 'bg-white border-slate-200 text-slate-800' : 'bg-surface border-slate-800 text-slate-100'
        }`}
      >
        {/* Header */}
        <div className={`p-4 sm:p-5 border-b flex items-center justify-between ${
          isLight ? 'bg-gradient-to-r from-purple-50/70 via-slate-50 to-white border-slate-200' : 'bg-gradient-to-r from-purple-950/40 via-slate-900 to-surface border-slate-800'
        }`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center text-white shadow-md">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base sm:text-lg font-black tracking-tight">
                  {isAr ? 'منظومة وكلاء التداول الذكية (CrewAI 5-Agent Framework)' : 'CrewAI 5-Agent Institutional Trading Engine'}
                </h3>
                <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-purple-500/20 text-purple-700 dark:text-purple-300 border border-purple-500/30">
                  CrewAI Python v3.10
                </span>
              </div>
              <p className={`text-xs mt-0.5 ${isLight ? 'text-slate-500' : 'text-slate-400'}`}>
                {isAr
                  ? '5 وكلاء ذكاء اصطناعي متخصصين يعملون بالتبادل التشاركي مع اعتماد الـ CTO مرسل إلى التيليجرام تلقائياً'
                  : '5 specialized CrewAI agents working sequentially with CTO final JSON approval & Telegram dispatch.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchCrewEcosystem}
              disabled={isLoading}
              className={`p-2 rounded-xl border text-xs font-bold transition ${
                isLight
                  ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
              }`}
              title={isAr ? 'تحديث بيانات الوكلاء' : 'Refresh Agents'}
            >
              <RefreshCw className={`w-4 h-4 text-purple-400 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className={`p-2 rounded-xl border text-xs font-bold transition ${
                isLight ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300' : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
              }`}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Selector */}
        <div className={`flex items-center border-b px-4 gap-2 text-xs font-bold ${
          isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/60 border-slate-800'
        }`}>
          <button
            onClick={() => setActiveTab('CREW_AGENTS')}
            className={`flex items-center gap-2 py-3 px-3 border-b-2 transition cursor-pointer ${
              activeTab === 'CREW_AGENTS'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400 font-extrabold'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>{isAr ? 'وكلاء CrewAI الـ 5' : 'CrewAI 5 Agents'}</span>
          </button>

          <button
            onClick={() => setActiveTab('DIALOGUE')}
            className={`flex items-center gap-2 py-3 px-3 border-b-2 transition cursor-pointer ${
              activeTab === 'DIALOGUE'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400 font-extrabold'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            <span>{isAr ? 'حوار وتبادل البيانات المباشر' : 'Inter-Agent Dialogue'}</span>
            {data?.inter_agent_dialogue && (
              <span className="px-1.5 py-0.2 rounded-full text-xs bg-purple-500/20 text-purple-500">
                {data.inter_agent_dialogue.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('CTO_JSON')}
            className={`flex items-center gap-2 py-3 px-3 border-b-2 transition cursor-pointer ${
              activeTab === 'CTO_JSON'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400 font-extrabold'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Code className="w-4 h-4" />
            <span>{isAr ? 'تقرير الـ CTO النهائي (JSON Output)' : 'CTO Final JSON Output'}</span>
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <RefreshCw className="w-8 h-8 text-purple-500 animate-spin" />
              <p className="text-sm text-slate-400 font-medium">
                {isAr ? 'جاري تشغيل خوارزميات CrewAI التشاركية...' : 'Running CrewAI Collaborative Agents...'}
              </p>
            </div>
          ) : activeTab === 'CREW_AGENTS' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {agentsList.map((ag) => (
                <div
                  key={ag.id}
                  className={`p-4 rounded-xl border transition-all ${
                    isLight ? 'bg-slate-50/80 border-slate-200 hover:border-purple-300' : 'bg-slate-900/60 border-slate-800 hover:border-purple-500/50'
                  }`}
                >
                  <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-200 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center text-xs font-black">
                        #{ag.num}
                      </div>
                      <h4 className="font-bold text-xs sm:text-sm">{ag.title}</h4>
                    </div>
                    <span className="text-xs font-extrabold px-2 py-0.5 rounded-md bg-purple-500/20 text-purple-400 border border-purple-500/30">
                      {ag.badge}
                    </span>
                  </div>

                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-3 leading-relaxed">
                    {isAr ? ag.roleAr : ag.roleEn}
                  </p>

                  <div className={`p-2.5 rounded-lg border text-xs font-mono space-y-1 ${
                    isLight ? 'bg-white border-slate-200 text-slate-700' : 'bg-canvas border-slate-800 text-slate-300'
                  }`}>
                    {ag.output ? (
                      <div>
                        <div className="text-xs text-purple-400 font-bold mb-1">
                          {isAr ? 'النتيجة المباشرة:' : 'Live Finding:'}
                        </div>
                        <p className="text-xs leading-relaxed">
                          {ag.output.summary_ar || ag.output.summary || JSON.stringify(ag.output)}
                        </p>
                      </div>
                    ) : (
                      <p className="text-slate-500 italic text-xs">
                        {isAr ? 'في انتظار استلام المهمة التشاركية...' : 'Awaiting task execution...'}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : activeTab === 'DIALOGUE' ? (
            <div className="space-y-3">
              <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4 shrink-0 text-purple-400" />
                <span>
                  {isAr
                    ? 'سجل التبادل التشاركي المباشر بين وكلاء CrewAI الخمسة بالتتابع (Sequential Execution Flow).'
                    : 'Real-time sequential task execution log between the 5 CrewAI agents.'}
                </span>
              </div>

              {data?.inter_agent_dialogue && data.inter_agent_dialogue.length > 0 ? (
                <div className="space-y-2.5">
                  {data.inter_agent_dialogue.map((item: any, idx: number) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-xl border text-xs ${
                        isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/80 border-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2 font-bold text-purple-400">
                          <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
                          <span>{item.sender}</span>
                        </div>
                        <span className="text-xs text-slate-500 font-mono">{item.time_str}</span>
                      </div>
                      <div className="font-semibold text-slate-300 mb-1">
                        Topic: <span className="text-amber-400 font-mono">{item.topic}</span>
                      </div>
                      <p className="text-slate-400 leading-relaxed text-xs">
                        {item.summary || JSON.stringify(item.data)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-10 text-slate-500 text-xs">
                  {isAr ? 'لا يوجد حوار متاح حالياً.' : 'No dialogue logs recorded.'}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300 flex items-center gap-2">
                <Code className="w-4 h-4 shrink-0 text-purple-400" />
                <span>
                  {isAr
                    ? 'التقرير الهيكلي النهائي الصادر من الوكيل 4 (CTO) بصيغة JSON المعتمدة.'
                    : 'Final structured JSON setup generated by Agent 4 (CTO).'}
                </span>
              </div>

              <div className={`p-4 rounded-xl border font-mono text-xs overflow-x-auto ${
                isLight ? 'bg-slate-900 text-purple-300 border-slate-800' : 'bg-canvas text-purple-300 border-slate-800'
              }`}>
                <pre>{JSON.stringify(data?.setup_json || data, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={`p-4 border-t flex items-center justify-between text-xs ${
          isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-900/80 border-slate-800'
        }`}>
          <div className="flex items-center gap-2 font-mono text-slate-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span>ENGINE: CrewAI 5-Agent Framework (server/crew_ai_trading_system.py)</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-extrabold transition cursor-pointer"
          >
            {isAr ? 'إغلاق النافذة' : 'Close Dashboard'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};
