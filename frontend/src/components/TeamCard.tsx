import React, { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Crosshair, Gauge, Hourglass, MapPin, OctagonX, Shield, TrendingUp, Users, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { Team, TeamAgent, TeamSetup } from '../smcTeam';
import { NotificationBell } from './NotificationBell';

// the 5 FXAlexG agents
const AGENT_ICON = { trend: TrendingUp, aoi: MapPin, confluence: Gauge, trigger: Crosshair, risk: Shield };
const GRADE_TONE: Record<string, string> = { 'A+': 'bg-emerald-500/20 text-emerald-200 ring-emerald-500/40', A: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30',
  B: 'bg-gold-500/15 text-gold-200 ring-gold-500/30', 'C+': 'bg-amber-500/15 text-amber-200 ring-amber-500/30', F: 'bg-white/[0.04] text-slate-400 ring-line' };

const TONE = { SIGNAL: 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/30', BLOCKED: 'bg-amber-500/10 text-amber-200 ring-amber-500/25',
  WATCHING: 'bg-sky-500/10 text-sky-200 ring-sky-500/25', IDLE: 'bg-white/[0.03] text-slate-400 ring-line', OFF: 'bg-white/[0.02] text-slate-600 ring-line' };
const hm = (t: number) => new Date(t * 1000).toISOString().slice(11, 16);

/** The pair's team under its chart: its own playbook strategy, and each setup with its levels and the 5 questions (research, not advice). */
export const TeamCard: React.FC<{ team: Team | null; symbol: string; decimals: number; lang: Language }> = ({ team, symbol, decimals, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const [open, setOpen] = useState<string | null>(null);
  const f = (v: number) => v.toFixed(decimals);
  const status = (s: string) => ({ SIGNAL: t('Setup', 'Setup', 'سيتاب'), BLOCKED: t('Blocked', 'Bloqué', 'محبوس'), WATCHING: t('Watching', 'En veille', 'كيراقب'), IDLE: t('Idle', 'Rien', 'والو'), OFF: t('Off for this pair', 'Désactivée', 'مطفية') } as Record<string, string>)[s];
  const setupBox = (s: TeamSetup) => (
    <div className={`mt-2 rounded-lg border px-3 py-2 ${s.pass ? 'border-emerald-500/40 bg-emerald-500/[0.05]' : 'border-line bg-white/[0.02]'}`}>
      <p className="text-xs font-mono text-slate-200">
        <span className={`font-bold ${s.direction === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{s.market
          ? (s.direction === 'BUY' ? t('BUY at market', 'ACHAT au marché', 'شرا ف السوق') : t('SELL at market', 'VENTE au marché', 'بيع ف السوق'))
          : (s.direction === 'BUY' ? t('BUY zone', 'Zone d’achat', 'منطقة الشرا') : t('SELL zone', 'Zone de vente', 'منطقة البيع'))}</span> {!s.market && s.zone ? `${f(s.zone[0])} – ${f(s.zone[1])}` : f(s.entry)} ·
        <span className="text-rose-300"> SL {f(s.sl)}</span> ·{s.tp1 != null && <span className="text-emerald-200"> TP1 {f(s.tp1)} ({Math.round((s.part ?? 1) * 100)} %) ·</span>} <span className="text-emerald-300">TP {f(s.tp)}</span> · 1:{s.rr}{s.rrBest && s.rrBest > s.rr ? `–${s.rrBest}` : ''}
      </p>
      {s.market ? <p className="mt-0.5 text-[11px] text-slate-400">{t('Entered at the close of the trigger candle, as the playbook says.', 'Entrée à la clôture de la bougie de déclenchement, comme le dit le guide.', 'الدخول مع إغلاق شمعة الزناد، كيما كيقول الدليل.')}</p>
      : <p className="mt-0.5 text-[11px] text-slate-400">{t(`Limit at ${f(s.entry)}, the near edge: price only has to come into the zone, not touch one exact price.`,
        `Limite à ${f(s.entry)}, le bord proche : le prix doit seulement entrer dans la zone, pas toucher un prix exact.`,
        `الليميت ف ${f(s.entry)}، الطرف القريب: الثمن خاصو غير يدخل للمنطقة، ماشي يقيس نقطة بالضبط.`)}</p>}
      <p className="mt-0.5 text-[11px] text-slate-500">{!s.market && <>{t('valid until', 'valable jusqu’à', 'صالح حتى')} {hm(s.validUntil)} UTC · </>}{s.riskPct ?? 1} % : {s.lots['1000']} lot / $1,000</p>
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
        {t('A setup is sent to Telegram, your phone and this app once, when the 5 agents agree (consensus 70+, GPA 70 %+ = grade C+ or better, no veto, a closed LTF trigger, R:R 1:2 or more, the session, day and news rules). A radar alert comes earlier, when only the engulfing close is missing. Research, not financial advice.',
          'Un setup est envoyé sur Telegram, votre téléphone et cette app une seule fois, quand les 5 agents sont d’accord (consensus 70+, GPA 70 %+ = grade C+ ou mieux, aucun veto, un déclencheur LTF clôturé, gain 1:2 ou plus, les règles de session, de jour et de news). Une alerte radar arrive avant, quand il ne manque que la bougie englobante. Recherche, pas un conseil.',
          'السيتاب كيتصيفط لتيليغرام وللتيليفون ولهاد التطبيق مرة وحدة، ملي 5 agents كيتفقو (إجماع 70+، GPA 70 %+ يعني C+ ولا حسن، حتى فيتو، زناد LTF مسدود، ربح 1:2 ولا كثر، وقواعد السيشن والنهار والأخبار). تنبيه الرادار كيجي قبل، ملي كتبقى غير الشمعة الابتلاعية. بحث، ماشي نصيحة.')}
      </p>
    </section>
  );
};
