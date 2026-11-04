import React, { useMemo, useRef } from 'react';
import { Download } from 'lucide-react';
import { tr } from './ui';
import type { Language } from '../types';
import type { Scenarios, Trigger } from './ScenarioPanel';

type Bar = [number, number, number, number, number]; // time, open, high, low, close

const W = 760, H = 360;
const PAD = { top: 40, right: 70, bottom: 26, left: 10 };
const BULL = '#16C784', BEAR = '#EA3943', GOLD = '#D4AF37';

/**
 * The picture of a pair's scenarios: its last closed candles, and for each side the path the trade would take (from the
 * price now to its trigger, then to its target), with its entry zone, stop and target. A plan drawn, not a signal.
 */
export const ScenarioPicture: React.FC<{ symbol: string; tf: string; bars: Bar[]; price: number; decimals: number; sc: Scenarios; lang: Language }> = ({ symbol, tf, bars, price, decimals, sc, lang }) => {
  const t = (en: string, fr: string, ar: string) => tr(lang, en, fr, ar);
  const svgRef = useRef<SVGSVGElement>(null);
  const f = (v: number) => v.toFixed(decimals);
  const sides = [sc.buy.main, sc.sell.main].filter(Boolean) as Trigger[];

  const geo = useMemo(() => {
    const x0 = PAD.left, x1 = W - PAD.right, y0 = PAD.top, y1 = H - PAD.bottom;
    const split = x0 + (x1 - x0) * 0.66;  // candles on the left, the scenarios' future on the right
    const lo0 = Math.min(...bars.map(b => b[3]), price), hi0 = Math.max(...bars.map(b => b[2]), price);
    const span0 = hi0 - lo0 || price * 0.001;
    // the levels in view: entries and targets always, a stop only if it is not far beyond the range
    const lv: number[] = [];
    for (const s of sides) {
      lv.push(s.entry, s.tp);
      if (s.sl > lo0 - span0 * 0.6 && s.sl < hi0 + span0 * 0.6) lv.push(s.sl);
    }
    let lo = Math.min(lo0, ...lv), hi = Math.max(hi0, ...lv);
    const m = (hi - lo) * 0.06;
    lo -= m; hi += m;
    const y = (p: number) => y1 - ((p - lo) / (hi - lo)) * (y1 - y0);
    const n = bars.length;
    const step = (split - x0) / Math.max(1, n);
    const xb = (i: number) => x0 + step * (i + 0.5);
    const ticks = Array.from({ length: 5 }, (_, k) => lo + ((hi - lo) * (k + 0.5)) / 5);
    const times = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1].filter(i => i >= 0 && i < n);
    return { x0, x1, y0, y1, split, y, xb, step, ticks, times, lo, hi };
  }, [bars, price, sc]);  // eslint-disable-line react-hooks/exhaustive-deps

  const save = () => {
    const svg = svgRef.current;
    if (!svg) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = W * 2; c.height = H * 2;
      const ctx = c.getContext('2d');
      if (!ctx) return;
      ctx.fillStyle = '#0B0E14'; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      const a = document.createElement('a');
      a.download = `${symbol.replace('/', '')}-scenarios.png`;
      a.href = c.toDataURL('image/png');
      a.click();
    };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
  };

  if (bars.length < 10) return null;
  const { x0, x1, y0, y1, split, y, xb, step, ticks, times } = geo;
  const last = bars[bars.length - 1];
  const yNow = y(price);
  const date = (s: number) => new Date(s * 1000).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const clampY = (v: number) => Math.max(y0 - 4, Math.min(y1 + 4, v));

  return (
    <figure className="mt-2 rounded-xl border border-line overflow-hidden bg-[#0B0E14]">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" xmlns="http://www.w3.org/2000/svg"
        aria-label={t(`${symbol} scenarios: BUY ${sc.buyPct} %, SELL ${sc.sellPct} %`, `Scénarios ${symbol} : BUY ${sc.buyPct} %, SELL ${sc.sellPct} %`, `سيناريوهات ${symbol}: BUY ${sc.buyPct}%، SELL ${sc.sellPct}%`)}
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace">
        <defs>
          <marker id="arr-buy" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill={BULL} /></marker>
          <marker id="arr-sell" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill={BEAR} /></marker>
          <linearGradient id="future" x1="0" x2="1"><stop offset="0" stopColor="#D4AF37" stopOpacity="0.07" /><stop offset="1" stopColor="#D4AF37" stopOpacity="0" /></linearGradient>
        </defs>
        <rect x="0" y="0" width={W} height={H} fill="#0B0E14" />
        {/* title */}
        <text x={x0 + 2} y="18" fill="#F1F5F9" fontSize="13" fontWeight="700">{symbol} <tspan fill={GOLD} fontSize="11">{tf}</tspan></text>
        <text x={x0 + 2} y="32" fill="#64748B" fontSize="10">{date(last[0] + (tf === 'H4' ? 14400 : 3600))} · {t('scenarios now', 'scénarios maintenant', 'السيناريوهات دابا')}</text>
        <text x={x1} y="18" fill={BULL} fontSize="11" fontWeight="700" textAnchor="end">BUY {sc.buyPct}%</text>
        <text x={x1} y="32" fill={BEAR} fontSize="11" fontWeight="700" textAnchor="end">SELL {sc.sellPct}%</text>
        {/* grid + price axis */}
        {ticks.map((p, k) => (
          <g key={k}>
            <line x1={x0} x2={x1} y1={y(p)} y2={y(p)} stroke="#1E293B" strokeWidth="1" />
            <text x={x1 + 6} y={y(p) + 3} fill="#64748B" fontSize="10">{f(p)}</text>
          </g>
        ))}
        <rect x={split} y={y0} width={x1 - split} height={y1 - y0} fill="url(#future)" />
        <line x1={split} x2={split} y1={y0} y2={y1} stroke="#334155" strokeDasharray="2 4" />
        <text x={split + 4} y={y0 + 10} fill="#94A3B8" fontSize="9">{t('next hours', 'prochaines heures', 'الساعات الجاية')}</text>
        {/* candles */}
        {bars.map((b, i) => {
          const up = b[4] >= b[1];
          const col = up ? BULL : BEAR;
          const top = y(Math.max(b[1], b[4])), bot = y(Math.min(b[1], b[4]));
          const w = Math.max(1, step * 0.62);
          return (
            <g key={b[0]}>
              <line x1={xb(i)} x2={xb(i)} y1={y(b[2])} y2={y(b[3])} stroke={col} strokeWidth="1" />
              <rect x={xb(i) - w / 2} y={top} width={w} height={Math.max(1, bot - top)} fill={col} />
            </g>
          );
        })}
        {times.map(i => <text key={i} x={xb(i)} y={H - 9} fill="#475569" fontSize="9" textAnchor="middle">{date(bars[i][0])}</text>)}
        {/* the scenarios */}
        {sides.map((s, k) => {
          const buy = s.dir === 'BUY';
          const col = buy ? BULL : BEAR;
          const pct = buy ? sc.buyPct : sc.sellPct;
          const xa = split + 6, xm = split + (x1 - split) * 0.42, xe = x1 - 8;
          const ye = y(s.entry), yt = y(s.tp), ys = y(s.sl);
          const tol = Math.max(3, Math.abs(ye - ys) * 0.1);
          const slIn = ys >= y0 - 2 && ys <= y1 + 2;
          return (
            <g key={k}>
              <rect x={xa} y={ye - tol} width={xe - xa} height={tol * 2} fill={col} fillOpacity="0.16" stroke={col} strokeOpacity="0.5" />
              <polyline points={`${xb(bars.length - 1)},${yNow} ${xm},${ye} ${xe},${clampY(yt)}`} fill="none" stroke={col} strokeWidth="2" strokeDasharray="6 4"
                markerEnd={`url(#arr-${buy ? 'buy' : 'sell'})`} />
              <circle cx={xm} cy={ye} r="3.5" fill={col} />
              <line x1={xm} x2={xe} y1={clampY(yt)} y2={clampY(yt)} stroke={BULL} strokeOpacity="0.7" strokeDasharray="2 3" />
              {slIn && <line x1={xm} x2={xe} y1={ys} y2={ys} stroke={BEAR} strokeOpacity="0.8" strokeDasharray="2 3" />}
              <g transform={`translate(${xm + 6}, ${ye + (buy ? 16 : -8)})`}>
                <rect x="-2" y="-10" width="150" height="14" rx="3" fill="#0B0E14" fillOpacity="0.85" />
                <text fill={col} fontSize="10" fontWeight="700">{s.dir} {f(s.entry)} · {pct}%{s.ready ? '' : ' ⏳'}</text>
              </g>
            </g>
          );
        })}
        {/* the levels on the price axis, spread so they never overlap */}
        {(() => {
          const lab: { y: number; text: string; color: string }[] = [];
          for (const s of sides) {
            lab.push({ y: clampY(y(s.tp)), text: `TP ${f(s.tp)}`, color: BULL });
            const ys = y(s.sl);
            if (ys >= y0 - 2 && ys <= y1 + 2) lab.push({ y: ys, text: `SL ${f(s.sl)}`, color: BEAR });
          }
          lab.push({ y: yNow, text: '', color: '' });  // the price tag keeps its place
          lab.sort((a, b) => a.y - b.y);
          for (let i = 1; i < lab.length; i++) if (lab[i].y - lab[i - 1].y < 13) lab[i].y = lab[i - 1].y + 13;
          return lab.filter(l => l.text).map((l, i) => <text key={i} x={x1 + 6} y={l.y + 3} fill={l.color} fontSize="10" fontWeight="700">{l.text}</text>);
        })()}
        {/* the price now */}
        <line x1={x0} x2={x1} y1={yNow} y2={yNow} stroke={GOLD} strokeOpacity="0.7" strokeDasharray="3 3" />
        <rect x={x1 + 2} y={yNow - 8} width={PAD.right - 4} height="16" rx="3" fill={GOLD} />
        <text x={x1 + 6} y={yNow + 4} fill="#0B0E14" fontSize="10" fontWeight="700">{f(price)}</text>
      </svg>
      <figcaption className="flex items-center justify-between gap-2 px-2.5 py-1.5 border-t border-line text-[10px] text-slate-500">
        <span>{t('Each path: price now → trigger → target. A scenario is a plan, not a signal.', 'Chaque trajet : prix → déclencheur → objectif. Un scénario est un plan, pas un signal.', 'كل مسار: الثمن دابا ← الشرط ← الهدف. السيناريو خطة، ماشي إشارة.')}</span>
        <button type="button" onClick={save} className="shrink-0 inline-flex items-center gap-1 h-6 px-2 rounded-md border border-line text-slate-300 hover:bg-white/[0.05] cursor-pointer">
          <Download className="w-3 h-3" aria-hidden="true" />{t('Save image', 'Enregistrer l’image', 'حفظ الصورة')}
        </button>
      </figcaption>
    </figure>
  );
};
