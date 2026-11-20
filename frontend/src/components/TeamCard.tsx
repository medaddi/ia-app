import React, { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Crosshair, Hourglass, Info, OctagonX, Shield, Users, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { Team, TeamAgent, TeamSetup } from '../smcTeam';
import { NotificationBell } from './NotificationBell';
import { SizeLine, useMySizing } from './RiskSizing';

/**
 * The pair's FX Alex G Set & Forget desk under its chart, kept short: the verdict and the PairActor's tier, the grade
 * badge and the confluence bar (0 → 100 %+, the 80 % Grade B line), the 2 agents (strategy & confirmation; stop loss,
 * take profit & lot) as tiles (tap one for its checklist), the 3 setup classes (full sync, HTF retracement, daily counter-trend) as short rows (a signal opens its
 * plan), and the rules folded behind "How it works". Research signals, never orders.
 */
const AGENT_ICON = { strategy: Crosshair, risk: Shield };
const GRADE_TONE: Record<string, string> = { 'A+': 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', A: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30',
  B: 'bg-gold-500/15 text-gold-200 ring-gold-500/30', C: 'bg-amber-500/10 text-amber-200 ring-amber-500/25', D: 'bg-white/[0.04] text-slate-400 ring-line',
  WAIT: 'bg-white/[0.04] text-slate-400 ring-line' };
const BAR_MAX = 120;  // the bar shows 0 → 120 %: the 80 % (Grade B) and 100 % (A+) lines inside it, a higher score fills it
const TONE = { SIGNAL: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30', BLOCKED: 'bg-amber-500/10 text-amber-200 ring-amber-500/25',
  WATCHING: 'bg-sky-500/10 text-sky-200 ring-sky-500/25', IDLE: 'bg-white/[0.03] text-slate-500 ring-line', OFF: 'bg-white/[0.02] text-slate-600 ring-line' };
const hm = (t: number) => new Date(t * 1000).toISOString().slice(11, 16);
/** My own lot for a signal (from my USD risk and the signal's stop; never another user's): from /api/me/sizing. */
const MySize: React.FC<{ id: string; lang: Language }> = ({ id, lang }) => <SizeLine s={useMySizing(id)} lang={lang} />;

const StatusIcon: React.FC<{ status: TeamAgent['status']; className?: string }> = ({ status, className = 'w-4 h-4' }) =>
  status === 'ok' ? <Check className={`${className} text-emerald-400`} aria-hidden="true" />
    : status === 'veto' ? <OctagonX className={`${className} text-rose-400`} aria-hidden="true" />
    : status === 'warn' ? <AlertTriangle className={`${className} text-amber-400`} aria-hidden="true" />
    : <Hourglass className={`${className} text-slate-500`} aria-hidden="true" />;

export const TeamCard: React.FC<{ team: Team | null; symbol: string; decimals: number; lang: Language }> = ({ team, symbol, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState<string | null>(null);
  const toggle = (k: string) => setOpen(o => (o === k ? null : k));
  const f = (v: number) => v.toFixed(decimals);
  // short names: a word each, the full role shows in the details
  const agentName = (k: string) => ({ strategy: t('Strategy & confirmation', 'Stratégie & confirmation', 'الستراتيجية والتأكيد'),
    risk: t('SL · TP · lot', 'SL · TP · lot', 'الستوب · الهدف · اللوت') } as Record<string, string>)[k] ?? k;
  const statusWord = (s: TeamAgent['status']) => ({ ok: t('OK', 'OK', 'مزيان'), warn: t('Caution', 'Attention', 'انتباه'), wait: t('Waiting', 'En attente', 'كيتسنا'), veto: t('Veto', 'Veto', 'فيتو') })[s];
  const setupName = (id: string, name: string) => ({ SYNC: t('Full sync · W + D + 4H', 'Sync complet · W + D + 4H', 'تزامن كامل · W + D + 4H'),
    RETRACE: t('Retracement · W + D', 'Retracement · W + D', 'تصحيح · W + D'), COUNTER: t('Counter-trend · D + 4H', 'Contre-tendance · D + 4H', 'عكس الويكلي · D + 4H'),
    SF_DAY: t('Day · D1 + H4', 'Day · D1 + H4', 'داي · D1 + H4') } as Record<string, string>)[id] ?? name;
  const rowStatus = (s: string) => ({ SIGNAL: t('Signal', 'Signal', 'إشارة'), BLOCKED: t('Blocked', 'Bloqué', 'محبوس'), WATCHING: t('Watching', 'En veille', 'كيراقب'), IDLE: t('Nothing', 'Rien', 'والو'), OFF: t('Off', 'Désactivée', 'مطفية') } as Record<string, string>)[s];
  const verdict = ({
    EXECUTE: { word: t('Signal', 'Signal', 'إشارة'), tone: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/40' },
    WAIT_FOR_TRIGGER: { word: t('Waiting for the trigger', 'Attend le déclencheur', 'كيتسنا الزناد'), tone: 'bg-sky-500/10 text-sky-200 ring-sky-500/30' },
    WATCH_ONLY: { word: t('Watching', 'En veille', 'كيراقب'), tone: 'bg-white/[0.04] text-slate-300 ring-line' },
    VETOED: { word: t('No trade', 'Pas de trade', 'ما كاين تريد'), tone: 'bg-rose-500/10 text-rose-200 ring-rose-500/25' },
  } as Record<string, { word: string; tone: string }>)[team?.decision ?? 'WATCH_ONLY'];

  const setupBox = (s: TeamSetup) => (
    <div className={`mt-2 rounded-lg border px-3 py-2.5 ${s.pass ? 'border-emerald-500/40 bg-emerald-500/[0.05]' : 'border-line bg-white/[0.02]'}`}>
      <p className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className={`px-1.5 py-0.5 rounded font-bold ${s.direction === 'BUY' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-rose-500/15 text-rose-200'}`}>{s.direction}</span>
        {s.etf && <span className="px-1.5 py-0.5 rounded bg-surface-2 font-mono text-[11px] text-gold-300">{s.etf}</span>}
        {s.grade && <span className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ring-1 ring-inset ${GRADE_TONE[s.grade] ?? GRADE_TONE.WAIT}`}>{s.grade}{s.score != null ? ` · ${s.score}%` : ''}</span>}
        {s.market != null && <span className="px-1.5 py-0.5 rounded bg-surface-2 text-[10px] font-semibold text-slate-300">{s.market ? t('Market', 'Marché', 'ماركت') : t('Limit', 'Limite', 'ليميت')}</span>}
        <span className="ms-auto font-mono text-[11px] text-slate-500">{hm(s.time)} UTC</span>
      </p>
      <dl className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 font-mono text-xs">
        {[[t('Entry', 'Entrée', 'الدخول'), f(s.entry), 'text-gold-300'], ['SL', f(s.sl), 'text-rose-300'], ['TP', f(s.tp), 'text-emerald-300'], ['R:R', `1:${s.rr}`, 'text-slate-400']].map(([k, v, c]) => (
          <div key={k} className="rounded-md bg-white/[0.03] px-2 py-1.5">
            <dt className={`text-[10px] uppercase tracking-wider ${c}`}>{k}</dt>
            <dd className="text-slate-100">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-1.5"><MySize id={s.id} lang={lang} /></div>
      <p className="mt-0.5 text-[11px] text-slate-400">{t('Set & Forget: SL and TP locked, no break-even, no partial', 'Set & Forget : SL et TP verrouillés, ni break-even ni partiel', 'Set & Forget: SL و TP مقفولين، بلا break-even وبلا جزئي')}</p>
      {!s.market && s.zone && <p className="mt-0.5 text-[11px] text-slate-400">{t('Limit zone', 'Zone limite', 'منطقة الليميت')} <span className="font-mono text-slate-200">{f(s.zone[0])} – {f(s.zone[1])}</span></p>}
      <ul className="mt-1.5 grid sm:grid-cols-2 gap-x-3 gap-y-0.5">
        {s.checklist.map(c => (
          <li key={c.q} className="flex items-start gap-1 text-[11px]" title={c.detail}>
            {c.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 shrink-0 text-rose-400" aria-label={t('no', 'non', 'لا')} />}
            <span className="text-slate-300">{c.q}</span>
          </li>
        ))}
      </ul>
    </div>
  );

  const agents = team?.success ? team.agents ?? [] : [];
  const picked = agents.find(a => open === `agent-${a.key}`);
  const score = team?.gpa ?? 0;
  const grade = team?.grade ?? 'D';
  const tierWord = (x?: string) => ({ TIER_3_DORMANT: t('Dormant', 'En sommeil', 'ناعس'), TIER_2_WATCHLIST: t('Watchlist', 'Liste de veille', 'تحت المراقبة'),
    TIER_1_SNIPER_AOI: t('Tier 1 · at the zone', 'Tier 1 · sur la zone', 'Tier 1 · ف المنطقة'), TIER_1_SOS_CONFIRMED: t('Tier 1 · SoS in', 'Tier 1 · SoS confirmé', 'Tier 1 · SoS تأكد'),
    AWAIT_PULLBACK_LIMIT: t('Limit waiting', 'Limite en attente', 'ليميت كتسنا'), SIGNAL_EMITTED: t('Signal', 'Signal', 'إشارة'),
    SET_AND_FORGET_LOCKED: t('Locked trade', 'Trade verrouillé', 'صفقة مقفولة') } as Record<string, string>)[x ?? ''] ?? '';
  const checklist = team?.checklist ?? [];

  return (
    <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="team-card-title">
      <header className="flex items-center justify-between gap-2">
        <h3 id="team-card-title" className="flex items-center gap-2 min-w-0 text-sm font-semibold text-white">
          <span className="icon-tile icon-tile-gold w-7 h-7 shrink-0" aria-hidden="true"><Users className="w-4 h-4" /></span>
          <span className="truncate">{t('Team', 'Équipe', 'الفريق')} <span className="font-mono text-slate-400">{symbol}</span></span>
        </h3>
        <div className="flex items-center gap-2 shrink-0">
          {team?.success && verdict && <span className={`px-2 py-1 rounded-md text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap ${verdict.tone}`}>{verdict.word}</span>}
          <NotificationBell lang={lang} />
        </div>
      </header>

      {!team && <div className="mt-3 h-24 rounded-lg bg-white/[0.03] animate-pulse" aria-busy="true" />}
      {team && !team.success && <p className="mt-3 text-xs text-amber-300">{team.error}</p>}

      {/* the grade: one bar (0 → 100 %+, the 80 % Grade B line), the 18 confluences on a tap */}
      {team?.success && team.gpa != null && (
        <div className="mt-3 rounded-lg border border-line bg-white/[0.02] px-3 py-2.5">
          <button type="button" onClick={() => toggle('gpa')} aria-expanded={open === 'gpa'} className="w-full text-start cursor-pointer">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded-md text-xs font-bold ring-1 ring-inset ${GRADE_TONE[grade] ?? GRADE_TONE.WAIT}`}>{grade === 'WAIT' ? 'WAIT' : `${t('Grade', 'Grade', 'Grade')} ${grade}`}</span>
              <span className="font-mono text-xs text-slate-200">{score}%</span>
              {team.direction && <span className={`text-[11px] font-semibold ${team.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{team.direction}</span>}
              {team.badge && <span className="hidden sm:inline font-mono text-[11px] text-slate-500 truncate">{team.badge.split(' · ')[0]}</span>}
              {team.tier && <span className="px-1.5 py-0.5 rounded bg-surface-2 text-[10px] text-slate-300 whitespace-nowrap">{tierWord(team.tier)}</span>}
              <ChevronDown className={`ms-auto w-3.5 h-3.5 shrink-0 text-slate-500 transition-transform ${open === 'gpa' ? 'rotate-180' : ''}`} aria-hidden="true" />
            </div>
            <div className="relative mt-2 h-1.5 rounded-full bg-white/[0.06]" role="meter" aria-valuemin={0} aria-valuemax={160} aria-valuenow={score}
              aria-label={t('Confluence score, a trade needs 80 %', 'Score de confluence, un trade demande 80 %', 'سكور التوافقات، التريد خاصو 80 %')}>
              <div className={`h-full rounded-full ${score >= 100 ? 'bg-emerald-400' : score >= 80 ? 'bg-emerald-500/80' : score >= 65 ? 'bg-amber-400' : 'bg-slate-500'}`} style={{ width: `${Math.min(100, (score / BAR_MAX) * 100)}%` }} />
              <span className="absolute -top-1 h-3.5 w-px bg-gold-300" style={{ insetInlineStart: `${(80 / BAR_MAX) * 100}%` }} title="80 % · B" aria-hidden="true" />
              <span className="absolute -top-1 h-3.5 w-px bg-emerald-300/70" style={{ insetInlineStart: `${(100 / BAR_MAX) * 100}%` }} title="100 % · A+" aria-hidden="true" />
            </div>
            <div className="relative mt-1 h-3 text-[9px] font-mono text-slate-500" aria-hidden="true">
              <span className="absolute -translate-x-1/2" style={{ insetInlineStart: `${(80 / BAR_MAX) * 100}%` }}>80 B</span>
              <span className="absolute -translate-x-1/2" style={{ insetInlineStart: `${(100 / BAR_MAX) * 100}%` }}>100 A+</span>
            </div>
          </button>
          {open === 'gpa' && (
            <ul className="mt-2.5 grid sm:grid-cols-2 gap-x-3 gap-y-0.5">
              {checklist.map(c => (
                <li key={c.key} className="flex items-start gap-1 text-[11px]">
                  {c.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 shrink-0 text-slate-600" aria-label={t('no', 'non', 'لا')} />}
                  <span className={c.ok ? 'text-slate-200' : 'text-slate-500'}>{c.label} <span className="font-mono">+{c.pts}</span></span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* the 5 agents: a tile each (icon, one word, its status); tap one for what it found */}
      {agents.length > 0 && (
        <>
          <ul className="mt-3 grid grid-cols-2 gap-1.5" aria-label={t('The team’s agents', 'Les agents de l’équipe', 'الوكلاء ديال الفريق')}>
            {agents.map(a => {
              const Icon = AGENT_ICON[a.key as keyof typeof AGENT_ICON] ?? Shield;
              const on = open === `agent-${a.key}`;
              return (
                <li key={a.key}>
                  <button type="button" onClick={() => toggle(`agent-${a.key}`)} aria-expanded={on} title={`${a.role} · ${statusWord(a.status)}`}
                    className={`w-full h-full flex flex-col items-center gap-1 rounded-lg border px-1 py-2 cursor-pointer transition-colors ${on ? 'border-gold-500/40 bg-gold-500/[0.06]' : 'border-line bg-white/[0.02] hover:bg-white/[0.05]'}`}>
                    <span className="relative">
                      <Icon className="w-4 h-4 text-slate-300" aria-hidden="true" />
                      <span className="absolute -top-1.5 -end-2.5"><StatusIcon status={a.status} className="w-3 h-3" /></span>
                    </span>
                    <span className="text-[11px] leading-tight text-slate-200 text-center">{agentName(a.key)}</span>
                    <span className="sr-only">{statusWord(a.status)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {picked && (
            <div className="mt-1.5 rounded-lg border border-line bg-white/[0.02] px-3 py-2">
              <p className="flex items-center gap-2 text-xs">
                <StatusIcon status={picked.status} className="w-3.5 h-3.5 shrink-0" />
                <span className="font-semibold text-slate-100">{picked.role}</span>
                {picked.score != null && <span className="ms-auto font-mono text-[11px] text-slate-400">{picked.score}/100</span>}
              </p>
              <p className="mt-1 text-[11px] text-slate-300">{picked.finding}</p>
              <ul className="mt-1 space-y-0.5">{picked.lines.map((l, k) => <li key={k} className="text-[11px] text-slate-500 leading-snug">{l}</li>)}</ul>
            </div>
          )}
        </>
      )}

      {/* the 3 setup classes: a short row each; a signal opens its plan */}
      {team?.success && team.strategies.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {team.strategies.map(s => {
            const next = s.watch?.steps.find(x => !x.ok);
            const live = s.status === 'SIGNAL' || s.status === 'BLOCKED' || s.status === 'WATCHING';
            const on = open === s.id || (open === null && s.status === 'SIGNAL');  // a signal shows its plan at once
            return (
              <li key={s.id} className={`rounded-lg border px-3 py-2 ${s.status === 'SIGNAL' ? 'border-emerald-500/30 bg-emerald-500/[0.03]' : 'border-line bg-white/[0.02]'}`}>
                <button type="button" onClick={() => toggle(s.id)} aria-expanded={on} className="w-full flex items-center gap-2 text-start cursor-pointer">
                  <span className={`min-w-0 flex-1 truncate text-xs ${live ? 'text-slate-100' : 'text-slate-400'}`}>{setupName(s.id, s.name)}</span>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${TONE[s.status]}`}>
                    {rowStatus(s.status)}{s.setup ? ` · ${s.setup.direction}` : ''}
                  </span>
                  <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-500 transition-transform ${on ? 'rotate-180' : ''}`} aria-hidden="true" />
                </button>
                {s.status === 'WATCHING' && !on && next && <p className="mt-0.5 text-[11px] text-slate-500 truncate">{t('waiting for', 'attend', 'كيتسنا')}: {next.step}</p>}
                {on && (
                  <div>
                    {s.setup && setupBox(s.setup)}
                    {s.watch && (
                      <ul className="mt-1.5 space-y-0.5">
                        {s.watch.steps.map(x => (
                          <li key={x.step} className="flex items-start gap-1 text-[11px]" title={x.detail}>
                            {x.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-hidden="true" /> : <X className="w-3.5 h-3.5 shrink-0 text-slate-600" aria-hidden="true" />}
                            <span className={x.ok ? 'text-slate-300' : 'text-slate-500'}>{x.step}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {!s.setup && !s.watch && <p className="mt-1 text-[11px] text-slate-500">{t('Nothing forming on the last 6 hours.', 'Rien en formation sur les 6 dernières heures.', 'حتى حاجة كتكون ف آخر 6 ساعات.')}</p>}
                    {s.measured && s.measured.trades > 0 && (
                      <p className="mt-1 text-[11px] text-slate-500">{t('Backtest', 'Backtest', 'باكتيست')}: <span className={`font-mono ${s.measured.totalR > 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{s.measured.winRate} %</span> {t('on', 'sur', 'على')} {s.measured.trades} · {s.measured.totalR >= 0 ? '+' : ''}{s.measured.totalR}R</p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* the rules, folded: one tap */}
      <div className="mt-3 flex items-center justify-between gap-2 text-[10px] text-slate-500">
        <button type="button" onClick={() => toggle('how')} aria-expanded={open === 'how'} className="inline-flex items-center gap-1 cursor-pointer hover:text-slate-300">
          <Info className="w-3 h-3" aria-hidden="true" />{t('How it works', 'Comment ça marche', 'كيفاش خدام')}
        </button>
        <span className="truncate">{t('Signals only · not advice', 'Signaux seulement · pas un conseil', 'إشارات فقط · ماشي نصيحة')}{team?.success && team.lastCandle ? ` · M5 ${hm(team.lastCandle + 300)} UTC` : ''}</span>
      </div>
      {open === 'how' && (
        <p className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">
          {t('2 agents: the strategy agent checks the trend, the zone, the score and the confirmation; the risk agent sets the stop loss, the take profit and the lot. On closed candles: the W / D / 4H trend (body closes only), the W / D zone with 3+ touches, the live confluences. At the zone (within 5 pips), a body-close shift of structure on M15 / M30 / H1 then an engulfing on H1 / H2 / H4 fire the trade, when the score is 80 %+ (Grade B), R:R at least 1:2, in session and away from news. Set & Forget: SL and TP never move. Your lot comes from your own $ risk. The app never places an order.',
            '2 agents : l’agent stratégie vérifie la tendance, la zone, le score et la confirmation ; l’agent risque fixe le stop, le take profit et le lot. Sur bougies clôturées : la tendance W / D / 4H (corps seulement), la zone W / D à 3+ touches, les confluences en direct. Sur la zone (à 5 pips), un changement de structure en clôture de corps sur M15 / M30 / H1 puis un engulfing en H1 / H2 / H4 déclenchent le trade, si le score est de 80 %+ (Grade B), R:R au moins 1:2, en session et loin des news. Set & Forget : SL et TP ne bougent jamais. Votre lot vient de votre propre risque en $. L’app ne passe jamais d’ordre.',
            '2 agents: agent الستراتيجية كيشوف الترند، المنطقة، السكور والتأكيد؛ و agent الريسك كيحدد الستوب، الهدف واللوت. على شموع مسدودة: الترند W / D / 4H (الأجسام فقط)، منطقة W / D فيها 3+ لمسات، والتوافقات الحية. ف المنطقة (5 بيبس)، كسر الهيكلة بإغلاق الجسم ف M15 / M30 / H1 من بعد شمعة ابتلاعية ف H1 / H2 / H4 كيعطيو الصفقة، إلا كان السكور 80 %+ (Grade B)، R:R على الأقل 1:2، ف السيشن وبعيد على الأخبار. Set & Forget: الستوب والهدف ما كيتحركوش. اللوت ديالك من الريسك ديالك بالدولار. التطبيق عمرو ما كيدير أمر.')}
        </p>
      )}
    </section>
  );
};
