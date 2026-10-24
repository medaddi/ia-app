/**
 * Agent tests: the validator can only reject, the deterministic answer follows the required
 * format, language detection, and the guard that rejects invented prices.
 */

import { evaluateXauusd } from "../xauusd/strategy";
import { xauInput } from "./fixtures";
import { validateSignal } from "../../agent/validator";
import { deterministicAnswer, detectLang, explainDrawing, inventsNumbers, symbolsFromQuestion } from "../../agent/agent";
import { buildSystemPrompt } from "../../agent/systemPrompt";
import { buildAgentContext } from "../../agent/context";

let passed = 0, failed = 0;
const check = (cond: boolean, name: string, detail = "") => {
  if (cond) { console.log(`[PASS] ${name}`); passed++; } else { console.error(`[FAIL] ${name} ${detail}`); failed++; }
};

console.log("==================================================");
console.log("AGENT");
console.log("==================================================");

const signal = evaluateXauusd(xauInput());
check(validateSignal(signal).approved, "1. Validator approves a clean SIGNAL", validateSignal(signal).issues.join("; "));

{
  const tampered = structuredClone(signal);
  tampered.setup!.tp2 = tampered.setup!.entry + (tampered.setup!.entry - tampered.setup!.sl) * 1.2; // R:R 1.2
  const v = validateSignal(tampered);
  check(!v.approved && v.issues.some(i => i.includes("R:R")), "2. Validator rejects a signal whose R:R fell below 1:2", v.issues.join("; "));
  const wide = structuredClone(signal);
  wide.setup!.sl = wide.setup!.entry - 12;
  check(!validateSignal(wide).approved, "3. Validator rejects a gold stop wider than $8");
  const noTrade = evaluateXauusd({ ...xauInput(), day: { trades: 2, losses: 0 } });
  check(!validateSignal(noTrade).approved, "4. Validator never approves what the strategy rejected");
  const lowered = structuredClone(signal);
  lowered.checklist = lowered.checklist.map(c => (c.key === "htf" ? { ...c, passed: false } : c));
  check(validateSignal(lowered).score <= signal.score, "5. Validator can only lower the score");
}

const answer = deterministicAnswer([signal], "en");
check(answer.includes("Bias") && answer.includes("Key levels") && answer.includes("Setup status") && answer.includes("Plan") && answer.includes("Risk"), "6. Answer follows Bias → Key levels → Setup → Plan → Risk");
check(answer.includes(signal.setup!.entry.toFixed(2)) && answer.includes(signal.setup!.sl.toFixed(2)), "7. Plan quotes the strategy's own entry and SL");

{
  const nt = evaluateXauusd({ ...xauInput(), day: { trades: 2, losses: 0 } });
  const a = deterministicAnswer([nt], "fr");
  check(a.includes("PAS DE TRADE") && a.includes("règle manquante"), "8. NO TRADE answer names the missing rule (French)", a.slice(0, 200));
}

check(detectLang("chno kayn f gold daba?") === "darija" && detectLang("ما هو اتجاه الذهب") === "ar" && detectLang("pourquoi pas de trade sur l'euro") === "fr" && detectLang("why no trade") === "en", "9. Language detection: Darija / Arabic / French / English");
check(JSON.stringify(symbolsFromQuestion("chno kayn f dhab")) === '["XAUUSD"]' && JSON.stringify(symbolsFromQuestion("euro bias?")) === '["EURUSD"]', "10. Questions are scoped to the right instrument");

const prompt = buildSystemPrompt();
check(prompt.includes("Never invent") && prompt.includes("XAUUSD") && prompt.includes("EURUSD") && prompt.includes("$2–$8") && prompt.includes("Setup B"), "11. System prompt holds both strategies' rules from the configs");

const ctx = JSON.stringify(buildAgentContext([signal]));
check(ctx.includes(String(signal.setup!.entry)) && !ctx.includes("candles\":["), "12. Agent context carries detector output, not raw guesses");

const fvg = signal.drawings.find(d => d.layer === "fvg");
check(!!fvg && explainDrawing(signal, fvg, "en").includes("Fair Value Gap"), "13. Explains a drawn FVG from its own data");

{
  const c = buildAgentContext([signal]);
  const ok = `Entry ${signal.setup!.entry.toFixed(2)}, SL ${signal.setup!.sl.toFixed(2)}`;
  check(inventsNumbers(ok, c).length === 0, "14. Guard accepts prices that exist in the context");
  check(JSON.stringify(inventsNumbers(`${ok}, TP 4123.45`, c)) === '["4123.45"]', "15. Guard catches an invented price (4123.45)");
}

console.log("==================================================");
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
console.log("==================================================");
if (failed > 0) process.exit(1);
