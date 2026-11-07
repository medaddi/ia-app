import React, { useState } from 'react';
import { AlertTriangle, CandlestickChart, Check, ChevronDown, Crown, Droplets, FlaskConical, Hourglass, Shield, Swords, Target, Users, X } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { Team, TeamAgent, TeamSetup } from '../smcTeam';

const AGENT_ICON = { lead: Crown, structure: CandlestickChart, liquidity: Droplets, entry: Target, risk: Shield, backtest: FlaskConical, devil: Swords };

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
      <p className="mt-0.5 text-[11px] text-slate-500">{!s.market && <>{t('valid until', 'valable jusqu’à', 'صالح حتى')} {hm(s.validUntil)} UTC · </>}1 % : {s.lots['1000']} lot / $1,000</p>
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
              H1 {team.chart.trend === 'BULLISH' ? t('bullish', 'haussier', 'صاعد') : team.chart.trend === 'BEARISH' ? t('bearish', 'baissier', 'هابط') : t('undefined', 'indéfini', 'غير محدد')} · {team.chart.premium ? 'premium' : 'discount'}
            </span>
          )}
          {team?.success && team.lastCandle && <span className="text-[11px] font-mono text-slate-500">{t('last M5 close', 'dernière clôture M5', 'آخر إغلاق M5')} {hm(team.lastCandle + 300)} UTC</span>}
        </div>
      </header>
      {!team && <div className="mt-3 h-20 rounded-lg bg-white/[0.03] animate-pulse" aria-busy="true" />}
      {team && !team.success && <p className="mt-3 text-xs text-amber-300">{team.error}</p>}
      {team?.success && team.agents && (
        <ul className="mt-3 space-y-1.5" aria-label={t('The team\u2019s agents', 'Les agents de l\u2019équipe', 'الوكلاء ديال الفريق')}>
          {team.agents.map((a: TeamAgent) => {
            const Icon = AGENT_ICON[a.key];
            const lead = a.key === 'lead';
            return (
              <li key={a.key} className={`rounded-lg border px-3 py-2 ${lead ? (a.status === 'ok' ? 'border-emerald-500/40 bg-emerald-500/[0.06]' : 'border-gold-500/30 bg-gold-500/[0.04]') : 'border-line bg-white/[0.02]'}`}>
                <button type="button" onClick={() => setOpen(o => (o === a.key ? null : a.key))} aria-expanded={open === a.key} className="w-full flex items-center gap-2 text-start cursor-pointer">
                  <Icon className={`w-4 h-4 shrink-0 ${lead ? 'text-gold-300' : 'text-slate-400'}`} aria-hidden="true" />
                  <span className={`shrink-0 text-xs font-semibold ${lead ? 'text-gold-100' : 'text-slate-200'}`}>{a.role}</span>
                  <span className="min-w-0 flex-1 truncate text-[11px] text-slate-400">{a.finding}</span>
                  {a.status === 'ok' ? <Check className="w-4 h-4 shrink-0 text-emerald-400" aria-label={t('signs off', 'valide', 'موافق')} />
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
      {team?.success && (
        <div className="mt-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">{t('This pair’s strategies (your guide)', 'Les stratégies de cette paire (votre guide)', 'الاستراتيجيات ديال هاد الزوج (الدليل ديالك)')}</p>
        </div>
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
        {t('A setup is sent to Telegram and your phone once, when its rules and the guide’s checklist (news, reward, 1 %, correlation, regime) pass. Research, not financial advice: each line shows what the guide claims and what one year of tests measured.',
          'Un setup est envoyé sur Telegram et votre téléphone une seule fois, quand ses règles et la liste du guide (news, gain, 1 %, corrélation, régime) passent. Recherche, pas un conseil : chaque ligne montre ce que dit le guide et ce qu’un an de tests a mesuré.',
          'السيتاب كيتصيفط لتيليغرام وللتيليفون مرة وحدة، ملي القواعد ديالو وشروط الدليل (الأخبار، الربح، 1 %، الارتباط، التقلب) كيدوزو. بحث، ماشي نصيحة: كل سطر كيبين شنو كيقول الدليل وشنو قاس التيست ف عام.')}
      </p>
    </section>
  );
};
