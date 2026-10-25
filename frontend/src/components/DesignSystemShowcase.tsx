import React, { useState, useEffect } from 'react';
import { 
  Palette, 
  Type, 
  Layers, 
  MousePointer, 
  Sliders, 
  Check, 
  Copy, 
  Sparkles, 
  Search, 
  DollarSign, 
  ArrowUpRight, 
  ArrowDownRight,
  ShieldCheck,
  AlertCircle,
  X
} from 'lucide-react';
import { DESIGN_TOKENS } from '../design-system/tokens';
import { Button, InputField, Card, MetricCard, StatusTag } from '../design-system/components';
import { Language } from '../types';

interface DesignSystemShowcaseProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
  theme: 'light' | 'dark';
}

export const DesignSystemShowcase: React.FC<DesignSystemShowcaseProps> = ({
  isOpen,
  onClose,
  lang,
  theme
}) => {
  const isAr = lang === 'ar';
  const isLight = theme === 'light';

  const [activeTab, setActiveTab] = useState<'COLORS' | 'TYPOGRAPHY' | 'COMPONENTS' | 'SPACING'>('COLORS');
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [btnLoading, setBtnLoading] = useState<boolean>(false);
  const [testInputValue, setTestInputValue] = useState<string>('EUR/USD Position');
  const [inputError, setInputError] = useState<string>('');

  // Lock body scroll and listen for Escape key
  useEffect(() => {
    if (!isOpen) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const currentPalette = isLight ? DESIGN_TOKENS.colors.light : DESIGN_TOKENS.colors.dark;

  const copyToClipboard = (text: string, tokenKey: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(tokenKey);
    setTimeout(() => setCopiedToken(null), 1500);
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="design-system-modal-title"
    >
      <div className={`relative w-full max-w-5xl max-h-[92vh] flex flex-col rounded-2xl border shadow-2xl overflow-hidden ${
        isLight ? 'bg-white border-slate-200 text-slate-900' : 'bg-surface border-white/10 text-white'
      }`}>
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200/80 dark:border-white/10 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center border border-blue-500/20">
              <Palette className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="design-system-modal-title" className="text-lg font-bold tracking-tight">
                  {isAr ? 'نظام التصميم القياسي' : 'Vanguard Neo-Precision Design System'}
                </h2>
                <span className="text-xs font-mono px-2 py-0.5 rounded font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                  v1.0 Standard
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">
                {isAr ? 'نظام تصميم احترافي، هندسي ومتناسق 100% بدون قوالب الذكاء الاصطناعي العشوائية' : 'Strict, bespoke tokens & components adhering to mathematical 4px rhythm & anti-slop rules.'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/5 active:scale-95 transition cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            aria-label="Close Design System Showcase"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 pt-3 pb-2 border-b border-slate-200/60 dark:border-white/[0.06] bg-slate-50/50 dark:bg-white/[0.02] text-xs font-semibold shrink-0 overflow-x-auto no-scrollbar">
          {[
            { id: 'COLORS', labelEn: 'Color Palette', labelAr: 'لوحة الألوان', icon: Palette },
            { id: 'TYPOGRAPHY', labelEn: 'Typography Scale', labelAr: 'مقياس الخطوط', icon: Type },
            { id: 'COMPONENTS', labelEn: 'Core Components', labelAr: 'المكونات الأساسية', icon: Layers },
            { id: 'SPACING', labelEn: 'Spatial Math & Radii', labelAr: 'الأبعاد والمسافات', icon: Sliders },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                  isActive
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-200/60 dark:hover:bg-white/5'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{isAr ? tab.labelAr : tab.labelEn}</span>
              </button>
            );
          })}
        </div>

        {/* Main Content Area */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          
          {/* TAB 1: COLOR PALETTE */}
          {activeTab === 'COLORS' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  {isAr ? 'الألوان الأساسية والأسطح (Surfaces & Canvas)' : 'Surfaces & Canvas Tokens'}
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { name: 'Canvas', key: 'canvas', val: currentPalette.canvas, desc: 'Base application backdrop' },
                    { name: 'Surface Base', key: 'surfaceBase', val: currentPalette.surfaceBase, desc: 'Primary card layer' },
                    { name: 'Surface Subtle', key: 'surfaceSubtle', val: currentPalette.surfaceSubtle, desc: 'Recessed elements & inputs' },
                    { name: 'Surface Raised', key: 'surfaceRaised', val: currentPalette.surfaceRaised, desc: 'Modals & floating popovers' },
                  ].map((c) => (
                    <div 
                      key={c.key} 
                      onClick={() => copyToClipboard(c.val, c.key)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer hover:border-blue-500/50 ${
                        isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-900/60 border-white/10'
                      }`}
                    >
                      <div className="w-full h-12 rounded-lg border border-slate-200/50 dark:border-white/10 mb-2.5 shadow-inner" style={{ backgroundColor: c.val }} />
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs">{c.name}</span>
                        {copiedToken === c.key ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
                      </div>
                      <span className="font-mono text-xs text-slate-400 block mt-0.5">{c.val}</span>
                      <span className="text-xs text-slate-500 mt-1 block">{c.desc}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  {isAr ? 'الهوية والأزرار (Brand & Action CTAs)' : 'Brand & Action Hierarchy'}
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { name: 'Primary CTA', key: 'primary', val: currentPalette.primary, desc: 'Dominant high-contrast action' },
                    { name: 'Primary Hover', key: 'primaryHover', val: currentPalette.primaryHover, desc: 'Interactive hover state' },
                    { name: 'Secondary Cobalt', key: 'secondary', val: currentPalette.secondary, desc: 'Interactive accent' },
                    { name: 'Secondary Subtle', key: 'secondarySubtle', val: currentPalette.secondarySubtle, desc: 'Tinted backdrop' },
                  ].map((c) => (
                    <div 
                      key={c.key} 
                      onClick={() => copyToClipboard(c.val, c.key)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer hover:border-blue-500/50 ${
                        isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-900/60 border-white/10'
                      }`}
                    >
                      <div className="w-full h-12 rounded-lg border border-slate-200/50 dark:border-white/10 mb-2.5 shadow-inner" style={{ backgroundColor: c.val }} />
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs">{c.name}</span>
                        {copiedToken === c.key ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
                      </div>
                      <span className="font-mono text-xs text-slate-400 block mt-0.5">{c.val}</span>
                      <span className="text-xs text-slate-500 mt-1 block">{c.desc}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  {isAr ? 'حالات التداول والتنبيهات (Semantic Trading States)' : 'Controlled Semantic Feedback'}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    { name: 'Success (Profit / TP)', key: 'success', val: currentPalette.success, subtle: currentPalette.successSubtle, desc: 'Pine Emerald 600 (+Pips / Wins)' },
                    { name: 'Danger (Loss / SL)', key: 'danger', val: currentPalette.danger, subtle: currentPalette.dangerSubtle, desc: 'Crimson Berry 600 (-Pips / Stops)' },
                    { name: 'Warning (Caution / Break-Even)', key: 'warning', val: currentPalette.warning, subtle: currentPalette.warningSubtle, desc: 'Warm Amber 600 (Cooldown)' },
                  ].map((c) => (
                    <div 
                      key={c.key} 
                      className={`p-3.5 rounded-xl border flex items-center gap-3.5 ${
                        isLight ? 'bg-white border-slate-200' : 'bg-slate-900/60 border-white/10'
                      }`}
                    >
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 font-mono font-bold text-xs" style={{ backgroundColor: c.subtle, color: c.val }}>
                        ●
                      </div>
                      <div>
                        <span className="font-semibold text-xs block">{c.name}</span>
                        <span className="font-mono text-xs text-slate-400">{c.val}</span>
                        <p className="text-xs text-slate-500 mt-0.5">{c.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: TYPOGRAPHY SCALE */}
          {activeTab === 'TYPOGRAPHY' && (
            <div className="space-y-6">
              <div className={`p-4 rounded-xl border ${isLight ? 'bg-blue-50/50 border-blue-200/80 text-blue-900' : 'bg-blue-950/20 border-blue-800/40 text-blue-200'}`}>
                <p className="text-xs font-medium">
                  <strong>Typographic Rule:</strong> Swiss typographic baseline using <code>Inter</code> for crystal-clear readability and <code>JetBrains Mono</code> with <code>tabular-nums</code> for high-precision financial numbers.
                </p>
              </div>

              <div className="space-y-4">
                {[
                  { name: 'Display Heading', spec: '36px / 1.15 / -0.035em', text: 'Executive SMC Portfolio', class: 'text-3xl sm:text-4xl font-extrabold tracking-tight' },
                  { name: 'Heading 1', spec: '28px / 1.20 / -0.025em', text: 'Institutional Liquidity Dissection', class: 'text-2xl font-bold tracking-tight' },
                  { name: 'Heading 2', spec: '20px / 1.30 / -0.020em', text: 'Active Trade Management & R:R Ratios', class: 'text-xl font-semibold tracking-tight' },
                  { name: 'Heading 3', spec: '16px / 1.40 / -0.010em', text: 'Real-Time Market Execution Diagnostics', class: 'text-base font-semibold tracking-tight' },
                  { name: 'Body Large', spec: '15px / 1.50 / 0em', text: 'The trading engine monitors order blocks and fair value gaps with 95% minimum probability confirmation.', class: 'text-[15px] font-normal leading-relaxed text-slate-600 dark:text-slate-300' },
                  { name: 'Body Standard', spec: '14px / 1.50 / 0em', text: 'Standard application content, forms, table records and descriptions.', class: 'text-sm font-normal text-slate-600 dark:text-slate-300' },
                  { name: 'Caption / Meta', spec: '12px / 1.40 / +0.015em', text: 'XAU/USD · 1H Timeframe · Order Block 4153.80 · 2 mins ago', class: 'text-xs font-medium text-slate-400' },
                  { name: 'Tabular Financial Numbers', spec: 'Mono / 700 / Tabular', text: '+185 Pips  |  $5,420.00 USD  |  84.2% Win Rate', class: 'font-mono font-bold text-lg text-emerald-600 dark:text-emerald-400 tabular-nums' },
                ].map((row, i) => (
                  <div key={i} className={`p-4 rounded-xl border ${isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-900/40 border-white/10'}`}>
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-mono">
                      <span>{row.name}</span>
                      <span>{row.spec}</span>
                    </div>
                    <div className={row.class}>
                      {row.text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: CORE COMPONENTS PLAYGROUND */}
          {activeTab === 'COMPONENTS' && (
            <div className="space-y-8">
              
              {/* Buttons Section */}
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  Buttons (Optical 2:1 Padding & Tactile Press)
                </h3>
                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="primary" onClick={() => { setBtnLoading(true); setTimeout(() => setBtnLoading(false), 1500); }} isLoading={btnLoading}>
                    Primary Action
                  </Button>
                  <Button variant="secondary" leftIcon={<DollarSign className="w-4 h-4" />}>
                    Cobalt Accent
                  </Button>
                  <Button variant="outline">
                    Hairline Outline
                  </Button>
                  <Button variant="danger">
                    Crimson Action
                  </Button>
                  <Button variant="ghost">
                    Quiet Ghost
                  </Button>
                  <Button variant="primary" disabled>
                    Disabled State
                  </Button>
                </div>

                <div className="flex items-center gap-3 mt-4">
                  <span className="text-xs text-slate-400 font-mono">Sizes:</span>
                  <Button size="sm" variant="outline">Small (32px)</Button>
                  <Button size="md" variant="outline">Medium (40px)</Button>
                  <Button size="lg" variant="outline">Large (48px)</Button>
                </div>
              </div>

              {/* Input Fields Section */}
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  Input Fields (Dual-Ring Focus & Validation)
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <InputField
                    label="Trading Asset Symbol"
                    value={testInputValue}
                    onChange={(e) => setTestInputValue(e.target.value)}
                    leftAddon={<Search className="w-4 h-4" />}
                    hint="Default active input state"
                  />
                  <InputField
                    label="Capital Balance ($)"
                    defaultValue="5000"
                    leftAddon={<DollarSign className="w-4 h-4" />}
                    hint="Numeric tabular field"
                  />
                  <InputField
                    label="Risk Percentage (%)"
                    defaultValue="1.0"
                    error={inputError || undefined}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (v > 3.0) setInputError('Institutional maximum is 3.0%');
                      else setInputError('');
                    }}
                    hint="Type > 3 to test error validation state"
                  />
                </div>
              </div>

              {/* Cards Section */}
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  Cards & Surfaces (Single-Elevation Depth)
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <MetricCard
                    label="Total Net Pips"
                    value="+1,420"
                    change={{ value: '185 Pips today', isPositive: true }}
                    icon={<ArrowUpRight className="w-4 h-4 text-emerald-500" />}
                  />
                  <MetricCard
                    label="Live Win Rate"
                    value="84.2%"
                    change={{ value: '+4.2%', isPositive: true }}
                    icon={<ShieldCheck className="w-4 h-4 text-blue-500" />}
                  />
                  <MetricCard
                    label="Average R:R Ratio"
                    value="1:2.45"
                    change={{ value: 'Guaranteed 1:2', isPositive: true }}
                    icon={<Sparkles className="w-4 h-4 text-amber-500" />}
                  />
                </div>

                <div className="mt-4">
                  <Card
                    title="Interactive Executive Card"
                    subtitle="Adheres to r_inner = r_outer - padding mathematical radius formula."
                    action={
                      <div className="flex items-center gap-1.5">
                        <StatusTag status="success" label="Active" />
                        <StatusTag status="neutral" label="1H TF" />
                      </div>
                    }
                    interactive
                  >
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      Hover over this card to experience the subtle mathematical lift and hairline border adjustment without garish AI gradients.
                    </p>
                  </Card>
                </div>
              </div>

            </div>
          )}

          {/* TAB 4: SPATIAL MATH & RADII */}
          {activeTab === 'SPACING' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  4px Spatial Grid (Padding, Margin, Gaps)
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { token: '--space-3xs', val: '2px', tailwind: 'p-0.5 / gap-0.5' },
                    { token: '--space-2xs', val: '4px', tailwind: 'p-1 / gap-1' },
                    { token: '--space-xs',  val: '8px', tailwind: 'p-2 / gap-2' },
                    { token: '--space-sm',  val: '12px', tailwind: 'p-3 / gap-3' },
                    { token: '--space-md',  val: '16px', tailwind: 'p-4 / gap-4 (Standard)' },
                    { token: '--space-lg',  val: '24px', tailwind: 'p-6 / gap-6 (Cards)' },
                    { token: '--space-xl',  val: '32px', tailwind: 'p-8 / gap-8 (Sections)' },
                    { token: '--space-2xl', val: '48px', tailwind: 'p-12 / gap-12 (Hero)' },
                  ].map((s, i) => (
                    <div key={i} className={`p-3 rounded-xl border ${isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-900/60 border-white/10'}`}>
                      <div className="h-4 bg-blue-500/20 border border-blue-500/30 rounded mb-2" style={{ width: s.val }} />
                      <span className="font-mono font-bold text-xs block">{s.token}</span>
                      <span className="text-slate-400 text-xs font-mono">{s.val} ({s.tailwind})</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  Border Radius Geometry (Nested Alignment Formula)
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  {[
                    { token: '--radius-xs', val: '4px', desc: 'Inner micro elements' },
                    { token: '--radius-sm', val: '6px', desc: 'Small action controls' },
                    { token: '--radius-md', val: '10px', desc: 'Standard inputs & buttons' },
                    { token: '--radius-lg', val: '14px', desc: 'Primary card containers' },
                    { token: '--radius-xl', val: '20px', desc: 'Modals & drawers' },
                  ].map((r, i) => (
                    <div key={i} className={`p-3 rounded-xl border text-center ${isLight ? 'bg-slate-50/70 border-slate-200' : 'bg-slate-900/60 border-white/10'}`}>
                      <div className="w-12 h-12 mx-auto bg-slate-900 dark:bg-white/20 border border-slate-300 dark:border-white/20 mb-2" style={{ borderRadius: r.val }} />
                      <span className="font-mono font-bold text-xs block">{r.token}</span>
                      <span className="text-slate-400 text-xs font-mono">{r.val}</span>
                      <p className="text-xs text-slate-500 mt-1">{r.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-200/80 dark:border-white/10 bg-slate-50/80 dark:bg-white/[0.02] text-xs text-slate-500 shrink-0">
          <span>Active Standard: <strong>Vanguard Neo-Precision</strong> · Anti-AI Slop Compliant</span>
          <Button size="sm" variant="outline" onClick={onClose}>
            {isAr ? 'إغلاق المعاينة' : 'Close Showcase'}
          </Button>
        </div>

      </div>
    </div>
  );
};
