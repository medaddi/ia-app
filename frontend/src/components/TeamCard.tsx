import React, { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Crosshair, Gauge, Hourglass, MapPin, OctagonX, Shield, TrendingUp, Users, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { Team, TeamAgent, TeamSetup } from '../smcTeam';
import { NotificationBell } from './NotificationBell';
import { SizeLine, useMySizing } from './RiskSizing';

// the 5 FXAlexG agents
const AGENT_ICON = { trend: TrendingUp, aoi: MapPin, confluence: Gauge, trigger: Crosshair, risk: Shield };
const GRADE_TONE: Record<string, string> = { 'A+': 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', A: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30',
  B: 'bg-gold-500/15 text-gold-200 ring-gold-500/30', 'C+': 'bg-amber-500/15 text-amber-200 ring-amber-500/30', F: 'bg-white/[0.04] text-slate-400 ring-line' };

const TONE = { SIGNAL: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30', BLOCKED: 'bg-amber-500/10 text-amber-200 ring-amber-500/25',
  WATCHING: 'bg-sky-500/10 text-sky-200 ring-sky-500/25', IDLE: 'bg-white/[0.03] text-slate-400 ring-line', OFF: 'bg-white/[0.02] text-slate-600 ring-line' };
const hm = (t: number) => new Date(t * 1000).toISOString().slice(11, 16);
/** My own lot for a signal (never another user's): from /api/me/sizing. */
const MySize: React.FC<{ id: string; lang: Language }> = ({ id, lang }) => <SizeLine s={useMySizing(id)} lang={lang} />;

/** The pair's team under its chart: its own playbook strategy, and each setup with its levels and the 5 questions (research, not advice). */
export const TeamCard: React.FC<{ team: Team | null; symbol: string; decimals: number; lang: Language }> = ({ team, symbol, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState<string | null>(null);
  const f = (v: number) => v.toFixed(decimals);
  const status = (s: string) => ({ SIGNAL: t('Setup', 'Setup', 'سيتاب'), BLOCKED: t('Blocked', 'Bloqué', 'محبوس'), WATCHING: t('Watching', 'En veille', 'كيراقب'), IDLE: t('Idle', 'Rien', 'والو'), OFF: t('Off for this pair', 'Désactivée', 'مطفية') } as Record<string, string>)[s];
  const setupBox = (s: TeamSetup) => (
    <div className={`mt-2 rounded-lg border px-3 py-2 ${s.pass ? 'border-emerald-500/40 bg-emerald-500/[0.05]' : 'border-line bg-white/[0.02]'}`}>
      <p className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className={`px-1.5 py-0.5 rounded font-bold ${s.direction === 'BUY' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-rose-500/15 text-rose-200'}`}>{s.direction}</span>
        {s.setupType && <span className="font-mono text-slate-200">{s.setupType}</span>}
        {s.etf && <span className="px-1.5 py-0.5 rounded bg-surface-2 font-mono text-[11px] text-gold-300">{s.etf}</span>}
        {s.grade && <span className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ring-1 ring-inset ${GRADE_TONE[s.grade] ?? GRADE_TONE.F}`}>{t('Grade', 'Grade', 'Grade')} {s.grade}{s.gpa != null ? ` · ${s.gpa}%` : ''}</span>}
        {s.family && <span className={`px-1.5 py-0.5 rounded text-[11px] ring-1 ring-inset ${s.family === 'counter-trend' ? 'bg-amber-500/10 text-amber-200 ring-amber-500/30' : 'bg-white/[0.03] text-slate-300 ring-line'}`}>
          {s.family === 'counter-trend' ? t('Counter-trend', 'Contre-tendance', 'عكس الترند') : t('Trend-following', 'Suivi de tendance', 'مع الترند')}</span>}
        <span className="ms-auto text-[11px] text-slate-500">{t('Research signal · not an order', 'Signal de recherche · pas un ordre', 'إشارة بحث · ماشي أمر')}</span>
      </p>
      <dl className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 font-mono text-xs">
        <div className="rounded-md bg-white/[0.03] px-2 py-1.5">
          <dt className="text-[10px] uppercase tracking-wider text-gold-300">{s.market ? t('Entry (market)', 'Entrée (marché)', 'الدخول (السوق)') : t('Entry (limit)', 'Entrée (limite)', 'الدخول (ليميت)')}</dt>
          <dd className="text-slate-100">{f(s.entry)}</dd>
        </div>
        <div className="rounded-md bg-white/[0.03] px-2 py-1.5">
          <dt className="text-[10px] uppercase tracking-wider text-rose-300">{t('Stop', 'Stop', 'الستوب')}</dt>
          <dd className="text-slate-100">{f(s.sl)}{s.slPips != null && <span className="text-slate-500"> · {s.slPips} pips</span>}</dd>
        </div>
        <div className="rounded-md bg-white/[0.03] px-2 py-1.5">
          <dt className="text-[10px] uppercase tracking-wider text-emerald-300">{t('Target', 'Objectif', 'الهدف')}</dt>
          <dd className="text-slate-100">{f(s.tp)}{s.tpPips != null && <span className="text-slate-500"> · {s.tpPips} pips</span>}</dd>
        </div>
        <div className="rounded-md bg-white/[0.03] px-2 py-1.5">
          <dt className="text-[10px] uppercase tracking-wider text-slate-400">R:R</dt>
          <dd className="text-slate-100">1:{s.rr}</dd>
        </div>
      </dl>
      {s.tp1 != null && <p className="mt-1.5 text-[11px] text-slate-400">{s.part
        ? <>TP1 {f(s.tp1)} ({Math.round(s.part * 100)} %)</>
        : <>{t('Break-even step', 'Passage à break-even', 'خطوة البريك إيفن')}: {t('at', 'à', 'ف')} <span className="font-mono text-slate-200">{f(s.tp1)}</span> {t('the stop moves to the entry + 2 pips', 'le stop passe à l’entrée + 2 pips', 'الستوب كيمشي للدخول + 2 بيبس')}</>}</p>}
      {s.invalidation && <p className="mt-0.5 text-[11px] text-slate-400"><span className="text-rose-300">{t('Invalidation', 'Invalidation', 'الإبطال')}:</span> {s.invalidation}</p>}
      <div className="mt-1"><MySize id={s.id} lang={lang} /></div>
      <p className="mt-0.5 text-[11px] text-slate-500">{!s.market && <>{t('valid until', 'valable jusqu’à', 'صالح حتى')} {hm(s.validUntil)} UTC · </>}{t('stop fixed for this signal', 'stop fixe pour ce signal', 'الستوب ثابت لهاد الإشارة')} · {t('signal candle closed', 'bougie du signal clôturée', 'شمعة الإشارة سدات')} {hm(s.time)} UTC</p>
      <p className="mt-1.5 text-[10px] uppercase tracking-wider text-slate-500">{t('Why', 'Pourquoi', 'علاش')}</p>
      <ul className="grid sm:grid-cols-2 gap-x-3 gap-y-0.5">
        {s.steps.map(x => (
          <li key={x.step} className="flex items-start gap-1 text-[11px]" title={x.detail}>
            {x.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 shrink-0 text-rose-400" aria-label={t('no', 'non', 'لا')} />}
            <span className="text-slate-300">{x.step}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[10px] uppercase tracking-wider text-slate-500">{t('Execution gate', 'Règle d’exécution', 'قاعدة التنفيذ')}</p>
      <ul className="grid sm:grid-cols-2 gap-x-3 gap-y-0.5">
        {s.checklist.map(c => (
          <li key={c.q} className="flex items-start gap-1 text-[11px]" title={c.detail}>
            {c.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 shrink-0 text-rose-400" aria-label={t('no', 'non', 'لا')} />}
            <span className="text-slate-300">{c.q}</span>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <section className="mt-4 rounded-[var(--radius-card)] glass border p-4" aria-labelledby="team-card-title">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="team-card-title" className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="icon-tile icon-tile-gold w-7 h-7" aria-hidden="true"><Users className="w-4 h-4" /></span>
          {t('Pair team', 'Équipe de la paire', 'فريق الزوج')} <span className="text-[11px] font-normal text-slate-500">{symbol}{team?.playbook ? ` · ${team.playbook.name}` : ""}</span>
        </h3>
        <div className="flex flex-wrap items-center gap-2">
          {team?.success && team.chart && (
            <span className={`px-1.5 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${team.chart.trend === 'BULLISH' ? 'bg-emerald-500/10 text-emerald-200 ring-emerald-500/25' : team.chart.trend === 'BEARISH' ? 'bg-rose-500/10 text-rose-200 ring-rose-500/25' : 'bg-white/[0.03] text-slate-400 ring-line'}`}>
              {team.badge ?? <>H1 {team.chart.trend === 'BULLISH' ? t('bullish', 'haussier', 'صاعد') : team.chart.trend === 'BEARISH' ? t('bearish', 'baissier', 'هابط') : t('undefined', 'indéfini', 'غير محدد')} · {team.chart.premium ? 'premium' : 'discount'}</>}
            </span>
          )}
          {team?.success && team.evidence && (() => {
            const e = team.evidence;
            const word = e.state === 'validated for research' ? t('Validated for research', 'Validée pour la recherche', 'مأكدة للبحث')
              : e.state === 'experimental' ? t('Experimental', 'Expérimentale', 'تجريبية') : t('Insufficient data', 'Données insuffisantes', 'المعطيات ما كافياش');
            const tip = t(`Out-of-sample trades in the validation: ${e.oosTrades} of the ${e.needed} needed before any claim. The chart and the setups stay available; the strategy is not proven on this pair.`,
              `Trades hors échantillon dans la validation : ${e.oosTrades} sur les ${e.needed} exigés avant toute conclusion. Le graphique et les setups restent disponibles ; la stratégie n’est pas prouvée sur cette paire.`,
              `الصفقات خارج العينة ف التحقق: ${e.oosTrades} من ${e.needed} اللي خاصين قبل أي خلاصة. الشارت والسيتابات باقيين؛ الاستراتيجية ما مأكداش على هاد الزوج.`);
            return (
              <span title={tip} className={`px-1.5 py-0.5 rounded-md text-[11px] ring-1 ring-inset ${e.state === 'validated for research' ? 'bg-emerald-500/10 text-emerald-200 ring-emerald-500/25' : 'bg-amber-500/10 text-amber-200 ring-amber-500/25'}`}>
                {t('Evidence', 'Preuves', 'الدليل')}: {word} · {e.oosTrades}/{e.needed}
              </span>
            );
          })()}
          <NotificationBell lang={lang} />
          {team?.success && team.lastCandle && <span className="text-[11px] font-mono text-slate-500">{t('last M5 close', 'dernière clôture M5', 'آخر إغلاق M5')} {hm(team.lastCandle + 300)} UTC</span>}
        </div>
      </header>
      {!team && <div className="mt-3 h-20 rounded-lg bg-white/[0.03] animate-pulse" aria-busy="true" />}
      {team && !team.success && <p className="mt-3 text-xs text-amber-300">{team.error}</p>}
      {team?.success && team.agents && (
        <ul className="mt-3 space-y-1.5" aria-label={t('The team\u2019s agents', 'Les agents de l\u2019équipe', 'الوكلاء ديال الفريق')}>
          {team.agents.map((a: TeamAgent) => {
            const Icon = AGENT_ICON[a.key];
            const lead = false;  // five equal specialists: no lead row
            return (
              <li key={a.key} className={`rounded-lg border px-3 py-2 ${lead ? (a.status === 'ok' ? 'border-emerald-500/40 bg-emerald-500/[0.06]' : 'border-gold-500/30 bg-gold-500/[0.04]') : 'border-line bg-white/[0.02]'}`}>
                <button type="button" onClick={() => setOpen(o => (o === a.key ? null : a.key))} aria-expanded={open === a.key} className="w-full flex items-center gap-2 text-start cursor-pointer">
                  <Icon className={`w-4 h-4 shrink-0 ${lead ? 'text-gold-300' : 'text-slate-400'}`} aria-hidden="true" />
                  <span className={`shrink-0 text-xs font-semibold ${lead ? 'text-gold-100' : 'text-slate-200'}`}>{a.role}</span>
                  <span className="min-w-0 flex-1 truncate text-[11px] text-slate-400">{a.finding}</span>
                  {a.score != null && <span className="hidden sm:inline shrink-0 font-mono text-[10px] text-slate-400">{a.score}</span>}
                  {a.weight != null && <span className="hidden sm:inline shrink-0 font-mono text-[10px] text-slate-500">×{Math.round(a.weight * 100)}%</span>}
                  {a.status === 'ok' ? <Check className="w-4 h-4 shrink-0 text-emerald-400" aria-label={t('signs off', 'valide', 'موافق')} />
                    : a.status === 'veto' ? <OctagonX className="w-4 h-4 shrink-0 text-rose-400" aria-label={t('veto', 'veto', 'فيتو')} />
                    : a.status === 'warn' ? <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" aria-label={t('objection', 'objection', 'اعتراض')} />
                    : <Hourglass className="w-4 h-4 shrink-0 text-slate-500" aria-label={t('waiting', 'en attente', 'كيتسنا')} />}
                  <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-500 transition-transform ${open === a.key ? 'rotate-180' : ''}`} aria-hidden="true" />
                </button>
                {open === a.key && (
                  <ul className="mt-1.5 ms-6 space-y-0.5">
                    {a.lines.map((l, k) => <li key={k} className="text-[11px] text-slate-300 leading-snug">{l}</li>)}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {team?.success && team.gpa != null && (() => {
        const score = team.gpa ?? 0;
        const grade = team.grade ?? 'F';
        const all = team.checklist ?? [];
        const decision = ({ EXECUTE: 'EXECUTE', WAIT_FOR_TRIGGER: t('WAIT FOR TRIGGER', 'ATTEND LE DÉCLENCHEUR', 'كيتسنا الزناد'),
          WATCH_ONLY: t('WATCH ONLY', 'SURVEILLANCE', 'مراقبة فقط'), VETOED: 'VETO' } as Record<string, string>)[team.decision ?? 'WATCH_ONLY'];
        return (
          <div className="mt-3 rounded-lg border border-line bg-white/[0.02] px-3 py-2.5">
            <button type="button" onClick={() => setOpen(o => (o === 'gpa' ? null : 'gpa'))} aria-expanded={open === 'gpa'} className="w-full text-start cursor-pointer">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`px-2 py-0.5 rounded-md text-xs font-bold ring-1 ring-inset ${GRADE_TONE[grade] ?? GRADE_TONE.F}`}>
                  {grade === 'F' ? t('Grade F · NO TRADE', 'Grade F · PAS DE TRADE', 'Grade F · ما كاين تريد') : `Grade ${grade}`}
                </span>
                <span className="font-mono text-xs text-slate-200">GPA {score}%</span>
                <span className="text-[11px] text-slate-500">{team.direction}{team.setupType ? ` · ${team.setupType}` : ''} · {t('consensus', 'consensus', 'الإجماع')} {team.consensus ?? 0}/100 · {all.filter(c => c.ok).length}/9</span>
                <span className="ms-auto text-[11px] font-semibold text-slate-300">{decision}</span>
                <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-500 transition-transform ${open === 'gpa' ? 'rotate-180' : ''}`} aria-hidden="true" />
              </div>
              <div className="relative mt-2 h-2 rounded-full bg-white/[0.06]" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score}
                aria-label={t('GPA score, a trade needs 70 % (C+)', 'Score GPA, un trade demande 70 % (C+)', 'سكور GPA، التريد خاصو 70 % (C+)')}>
                <div className={`h-full rounded-full ${score >= 80 ? 'bg-emerald-400' : score >= 70 ? 'bg-gold-400' : score >= 55 ? 'bg-amber-400' : 'bg-slate-500'}`} style={{ width: `${Math.min(100, score)}%` }} />
                <span className="absolute -top-1 h-4 w-px bg-gold-300" style={{ insetInlineStart: '70%' }} aria-hidden="true" />
                <span className="absolute -top-1 h-4 w-px bg-white/30" style={{ insetInlineStart: '90%' }} aria-hidden="true" />
              </div>
              <div className="relative mt-1 h-3 text-[10px] font-mono text-slate-500" aria-hidden="true">
                <span className="absolute start-0">0%</span>
                <span className="absolute -translate-x-1/2 text-gold-300" style={{ insetInlineStart: '70%' }}>70% C+</span>
                <span className="absolute -translate-x-1/2" style={{ insetInlineStart: '90%' }}>90% A+</span>
              </div>
            </button>
            {open === 'gpa' && (
              <ul className="mt-2 grid sm:grid-cols-2 gap-x-3 gap-y-0.5">
                {all.map(c => (
                  <li key={c.key} className="flex items-start gap-1 text-[11px]">
                    {c.ok ? <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" aria-label={t('yes', 'oui', 'آه')} /> : <X className="w-3.5 h-3.5 shrink-0 text-slate-600" aria-label={t('no', 'non', 'لا')} />}
                    <span className={c.ok ? 'text-slate-200' : 'text-slate-500'}>{c.label} <span className="font-mono">+{c.pts}</span></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })()}
      {team?.success && (
        <div className="mt-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">{t('Set & Forget setup', 'Setup Set & Forget', 'السيتاب Set & Forget')}</p>
        </div>
      )}
      {team?.success && team.strategies.length === 0 && (
        <p className="mt-1.5 rounded-lg border border-line bg-white/[0.02] px-3 py-2 text-xs text-slate-400">
          {t('No strategy passed the one-year test for this pair (win rate ≥ 55 % and profit in both halves): the team keeps its analysis and sends no setup.',
            'Aucune stratégie n’a passé le test d’un an pour cette paire (réussite ≥ 55 % et gain sur les deux moitiés) : l’équipe garde son analyse et n’envoie aucun setup.',
            'حتى استراتيجية ما دوزات التيست ديال عام ف هاد الزوج (ربح ≥ 55 % ومربحة ف جوج الأجزاء): الفريق كيخلي التحليل وما كيصيفط حتى سيتاب.')}
        </p>
      )}
      {team?.success && (
        <ul className="mt-1.5 space-y-1.5">
          {team.strategies.map(s => {
            const next = s.watch?.steps.find(x => !x.ok);
            const fails = s.setup?.checklist.filter(c => !c.ok).length ?? 0;
            return (
              <li key={s.id} className="rounded-lg border border-line bg-white/[0.02] px-3 py-2">
                <button type="button" onClick={() => setOpen(o => (o === s.id ? null : s.id))} aria-expanded={open === s.id}
                  className="w-full flex items-center gap-2 text-start cursor-pointer">
                  {s.id !== 'P' && <span className="font-mono text-xs text-gold-300 w-6">{s.id}</span>}
                  <span className="min-w-0 flex-1 truncate text-xs text-slate-200">{s.name}</span>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded-md text-[11px] font-semibold ring-1 ring-inset ${TONE[s.status]}`}>
                    {status(s.status)}{s.setup ? ` · ${s.setup.direction}` : ''}{s.status === 'BLOCKED' ? ` · ${fails} ✗` : ''}
                  </span>
                  <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-500 transition-transform ${open === s.id ? 'rotate-180' : ''}`} aria-hidden="true" />
                </button>
                {s.claimed && (
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {t('guide', 'guide', 'الدليل')}: <span className="text-slate-300">{s.claimed}</span> ·{' '}
                    {s.measured && s.measured.trades > 0
                      ? <>{t('test (1 year)', 'test (1 an)', 'التيست (عام)')}: <span className={`font-mono ${s.measured.totalR > 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{s.measured.winRate} %</span> {t('on', 'sur', 'على')} {s.measured.trades} · {s.measured.totalR >= 0 ? '+' : ''}{s.measured.totalR}R</>
                      : <span className="text-amber-300">{t('no trade in the test year', 'aucun trade sur l’année testée', 'حتى صفقة ف عام التيست')}</span>}
                  </p>
                )}
                {s.status === 'WATCHING' && open !== s.id && next && <p className="mt-0.5 text-[11px] text-slate-500 truncate">{t('waiting for', 'attend', 'كيتسنا')}: {next.step}</p>}
                {open === s.id && (
                  <div className="ms-8">
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
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-[10px] text-slate-500 leading-relaxed">
        {t(`A setup is sent to Telegram, your phone and this app once, when the 5 agents agree (consensus 70+, GPA 70 %+, no veto, a closed confirmation candle at a zone with 3+ touches, R:R 1:${team?.params?.minRr ?? 2} or more to the next opposing structure, the session, day and news rules). A counter-trend setup needs GPA ${team?.params?.counterMinGpa ?? 80} %+. Nothing is sent while a setup is only forming. Research signals, never orders; not financial advice and no promise of profit.`,
          `Un setup est envoyé sur Telegram, votre téléphone et cette app une seule fois, quand les 5 agents sont d’accord (consensus 70+, GPA 70 %+, aucun veto, une bougie de confirmation clôturée sur une zone à 3+ touches, gain 1:${team?.params?.minRr ?? 2} ou plus jusqu’à la prochaine structure opposée, les règles de session, de jour et de news). Un setup contre-tendance exige un GPA de ${team?.params?.counterMinGpa ?? 80} %+. Rien n’est envoyé tant qu’un setup est seulement en formation. Signaux de recherche, jamais des ordres ; pas un conseil financier, aucune promesse de gain.`,
          `السيتاب كيتصيفط لتيليغرام وللتيليفون ولهاد التطبيق مرة وحدة، ملي 5 agents كيتفقو (إجماع 70+، GPA 70 %+، حتى فيتو، شمعة تأكيد مسدودة ف منطقة فيها 3+ لمسات، ربح 1:${team?.params?.minRr ?? 2} ولا كثر حتى للهيكل المعاكس الجاي، وقواعد السيشن والنهار والأخبار). السيتاب عكس الترند خاصو GPA ${team?.params?.counterMinGpa ?? 80} %+. والو ما كيتصيفط ملي السيتاب باقي غير كيتكون. إشارات بحث، ماشي أوامر؛ ماشي نصيحة مالية وحتى وعد بالربح.`)}
      </p>
    </section>
  );
};
