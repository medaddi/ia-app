/**
 * One-off: records the TypeScript strategies' output on real candles so the Python port can be
 * checked bar for bar (backend/tests/fixtures/parity_*.json).
 */
import fs from "fs";
import crypto from "crypto";
import { evaluateXauusd } from "../server/strategies/xauusd/strategy";
import { evaluateEurusd } from "../server/strategies/eurusd/strategy";
import { xauInput, buildM5, trend } from "../server/strategies/tests/fixtures";
import path from "path";
import { loadStrategyCandles, STRATEGY_DEFS } from "../server/strategies";
import { replay } from "../server/strategies/replay";
import { TF_SEC } from "../server/strategies/shared/types";

function summary(r: any) {
  return {
    status: r.status, score: r.score, bias: r.bias.direction, rejection: r.rejection, headline: r.headline, canNotify: r.canNotify,
    checklist: r.checklist.map((c: any) => [c.key, c.passed]),
    setup: r.setup && {
      id: r.setup.id, setup: r.setup.setup, direction: r.setup.direction, entryType: r.setup.entryType,
      entry: r.setup.entry, sl: r.setup.sl, tp1: r.setup.tp1, tp2: r.setup.tp2, tp3: r.setup.tp3,
      rrTp2: Number(r.setup.rrTp2.toFixed(6)), state: r.setup.lifecycle.state, lots: r.setup.lots,
    },
    drawings: crypto.createHash("sha1").update(r.drawings.map((d: any) => `${d.id}|${d.layer}|${d.kind}|${d.t1}|${d.t2}|${d.p1}|${d.p2 ?? ""}|${d.text ?? ""}`).sort().join("\n")).digest("hex"),
    drawingCount: r.drawings.length,
  };
}

(async () => {
  const out = path.resolve("backend/tests/fixtures");
  fs.mkdirSync(out, { recursive: true });
  for (const sym of ["XAU/USD", "EUR/USD"] as const) {
    const def = STRATEGY_DEFS[sym];
    const { candles, source } = await loadStrategyCandles(sym);
    const entry = candles[def.entryTf]!;
    const tf = TF_SEC[def.entryTf];
    const end = entry[entry.length - 1].time + tf;
    // Trim history to keep the fixture small but enough for every lookback
    const keepFrom = end - (sym === "XAU/USD" ? 62 : 25) * 86400;
    const trimmed: any = {};
    for (const [k, v] of Object.entries(candles)) {
      const min = k === "H1" ? end - 120 * 86400 : k === "H4" ? end - 400 * 86400 : k === "D1" ? end - 500 * 86400 : keepFrom - 8 * 86400;
      trimmed[k] = (v as any[]).filter(c => c.time >= min).map(c => [c.time, c.open, c.high, c.low, c.close, c.volume || 0]);
    }
    const news = { events: [], source: "fixture" };
    const base = { candles: Object.fromEntries(Object.entries(trimmed).map(([k, v]) => [k, (v as any[]).map(a => ({ time: a[0], open: a[1], high: a[2], low: a[3], close: a[4], volume: a[5] }))])), livePrice: 0, spread: null, isRealData: true, dataSource: source, news };
    const evals: any[] = [];
    const entryT = base.candles[def.entryTf] as any[];
    const startIdx = entryT.findIndex(c => c.time >= keepFrom);
    for (let i = startIdx; i < entryT.length; i += 1) {
      const close = entryT[i].time + tf;
      const inWindow = def.canSignalAt(close);
      if (!inWindow && i % 12 !== 0) continue; // all window bars + a sample outside windows
      const r = def.run({ ...base, nowSec: close, isMarketOpen: true, day: { trades: 0, losses: 0 } } as any);
      evals.push({ nowSec: close, result: summary(r) });
    }
    const rep = replay(def, base as any, entryT[startIdx].time, end);
    const emitted = rep.emitted.map(e => ({ id: e.id, signalTime: e.signalTime, score: e.score, entry: e.setup.entry, sl: e.setup.sl }));
    const file = path.join(out, `parity_${sym.replace("/", "")}.json`);
    fs.writeFileSync(file, JSON.stringify({ symbol: sym, source, candles: trimmed, evals, emitted }));
    console.log(`${sym}: ${evals.length} evaluations, ${emitted.length} emitted, ${evals.filter(e => e.result.setup).length} with setup → ${file} (${(fs.statSync(file).size / 1024).toFixed(0)} KB)`);
  }
  // Hand-built scenarios from the TS unit tests (exercise the full setup path)
  const ser = (inp: any) => ({ ...inp, candles: Object.fromEntries(Object.entries(inp.candles).map(([k, v]) => [k, (v as any[]).map(c => [c.time, c.open, c.high, c.low, c.close, c.volume || 0])])) });
  const scen: any[] = [];
  const add = (name: string, fn: string, inp: any, r: any) => scen.push({ name, fn, input: ser(inp), result: summary(r) });
  const base = xauInput();
  add("xau_signal", "xau", base, evaluateXauusd(base));
  const bear = xauInput(); bear.candles.H4 = trend(bear.nowSec - (bear.nowSec % 14400), 14400, 120, 4300, -2.5, 12);
  add("xau_h4_bearish", "xau", bear, evaluateXauusd(bear));
  const early = xauInput({}, buildM5().map(c => ({ ...c, time: c.time - 7200 })));
  add("xau_outside_killzone", "xau", early, evaluateXauusd(early));
  const news = { ...xauInput(), news: { events: [{ time: base.nowSec + 600, currency: "USD", title: "CPI m/m", impact: "High" as const }], source: "t" } };
  add("xau_news", "xau", news, evaluateXauusd(news));
  const day = { ...xauInput(), day: { trades: 2, losses: 0 } };
  add("xau_daily_limit", "xau", day, evaluateXauusd(day));
  const eurMod = await import("../server/strategies/tests/eurusdFixture");
  for (const [name, inp] of eurMod.eurScenarios()) add(name, "eur", inp, evaluateEurusd(inp));
  fs.writeFileSync(path.join(out, "parity_scenarios.json"), JSON.stringify(scen));
  console.log(`scenarios: ${scen.map(x => `${x.name}=${x.result.status}`).join(", ")}`);
  process.exit(0);
})();
