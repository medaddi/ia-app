/**
 * Backtest CLI. Writes backtest-reports/<SYMBOL>.md and .json.
 * Run: npm run backtest            (both symbols)
 *      npm run backtest -- XAU/USD (one symbol)
 */

import fs from "fs";
import path from "path";
import { reportToMarkdown, runBacktest } from "./engine";

(async () => {
  const symbols = process.argv[2] ? [process.argv[2]] : ["XAU/USD", "EUR/USD"];
  const dir = path.resolve(process.cwd(), "backtest-reports");
  fs.mkdirSync(dir, { recursive: true });
  for (const s of symbols) {
    const t0 = Date.now();
    const r = await runBacktest(s);
    const name = s.replace("/", "");
    fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(r, null, 2));
    fs.writeFileSync(path.join(dir, `${name}.md`), reportToMarkdown(r));
    console.log(`\n${r.strategy} — ${r.period.from} → ${r.period.to} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
    console.log(`signals ${r.signals} · closed ${r.closed} · W ${r.wins} / L ${r.losses} / BE ${r.breakevens} · win rate ${r.winRate ?? "—"}% · PF ${r.profitFactor ?? "—"} · expectancy ${r.expectancyR ?? "—"}R · total ${r.totalR}R · max DD ${r.maxDrawdownR}R`);
    for (const w of r.warnings) console.log(`  ⚠ ${w}`);
  }
  process.exit(0); // liveMarket keeps a price refresh interval alive
})();
