/**
 * Telegram delivery tests: anti copy-trading protection and candle-close timing.
 * Telegram's API is mocked (global fetch); the bot config and database are not touched.
 */

import { personalizeSignal, personalOffset, referenceCode, hash32 } from "../../telegramProtection";
import { nextCloseSec } from "../../signalScheduler";
import { sendTelegramMessage, formatSignalMessage } from "../../telegram";

let passed = 0, failed = 0;
const check = (cond: boolean, name: string, detail = "") => {
  if (cond) { console.log(`[PASS] ${name}`); passed++; } else { console.error(`[FAIL] ${name} ${detail}`); failed++; }
};

console.log("==================================================");
console.log("TELEGRAM DELIVERY");
console.log("==================================================");

const gold = { id: "sig-XAUUSD-1-2", symbol: "XAU/USD", signalType: "BUY", entryPrice: 4000.25, stopLoss: 3995.95, target1: 4004.55, target2: 4012, target3: 4016.3, confidence: 94, strategyUsed: "XAUUSD · Liquidity Sweep + MSS + FVG" };
const euro = { id: "sig-EURUSD-B-3", symbol: "EUR/USD", signalType: "SELL", entryPrice: 1.1353, stopLoss: 1.13772, target1: 1.13288, target2: 1.13046, target3: 1.12804, confidence: 86, strategyUsed: "EURUSD · Trend Pullback + London Breakout Filter" };

{
  const a = personalizeSignal(gold, "1001"), b = personalizeSignal(gold, "1002");
  check(a.offset !== 0 && Math.abs(a.offset) <= 0.09 + 1e-9, "1. Gold offset is 1–9 cents, never zero", String(a.offset));
  const risk = (s: any) => Math.abs(s.entryPrice - s.stopLoss), reward = (s: any) => Math.abs(s.target2 - s.entryPrice);
  check(Math.abs(risk(a.signal) - risk(gold)) < 1e-6 && Math.abs(reward(a.signal) - reward(gold)) < 1e-6, "2. Stop distance and TP2 distance are unchanged (same risk, same R:R)");
  check(JSON.stringify(personalizeSignal(gold, "1001")) === JSON.stringify(a), "3. Deterministic: the same subscriber always gets the same levels");
  const distinct = new Set(Array.from({ length: 50 }, (_, i) => personalOffset("XAU/USD", String(5000 + i), gold.id).toFixed(2))).size;
  check(distinct >= 10, "4. Different subscribers get different offsets (no identical copy orders)", String(distinct));
  check(a.signal.entryPrice !== b.signal.entryPrice || a.offset !== b.offset || a.ref !== b.ref, "5. Two subscribers receive distinguishable copies");
  const e = personalizeSignal(euro, "1001");
  check(Math.abs(e.offset) <= 0.00009 + 1e-12 && e.offset !== 0, "6. EURUSD offset is 0.1–0.9 pip", String(e.offset));
  check(/^[0-9A-Z]{6}$/.test(a.ref) && referenceCode("1001", gold.id) === a.ref && referenceCode("1002", gold.id) !== a.ref, "7. Personal reference code: 6 chars, unique per subscriber");
  check(hash32("abc") === hash32("abc") && hash32("abc") !== hash32("abd"), "8. Stable hash");
}

{
  const t = Date.UTC(2026, 9, 27, 8, 3, 20);
  check(nextCloseSec(t, 300) === Date.UTC(2026, 9, 27, 8, 5) / 1000, "9. Next M5 close after 08:03:20 is 08:05:00");
  check(nextCloseSec(t, 900) === Date.UTC(2026, 9, 27, 8, 15) / 1000, "10. Next M15 close after 08:03:20 is 08:15:00");
  check(nextCloseSec(Date.UTC(2026, 9, 27, 8, 15), 900) === Date.UTC(2026, 9, 27, 8, 30) / 1000, "11. Exactly on a close → schedules the following one");
}

{
  const msg = formatSignalMessage({ ...euro, confirmationCheckPassed: true, confirmationCloseTime: Date.UTC(2026, 8, 29, 8, 0) / 1000 });
  check(msg.includes("1.13530") && msg.includes("1.13772") && msg.includes("1.13046"), "12. Message prints the exact strategy levels (5 decimals for EURUSD)");
}

(async () => {
  const realFetch = globalThis.fetch;
  let captured: any = null;
  globalThis.fetch = (async (_url: any, init: any) => {
    captured = JSON.parse(init.body);
    return new Response(JSON.stringify({ ok: true, result: { message_id: 7 } }), { status: 200 });
  }) as typeof fetch;
  const res = await sendTelegramMessage("test", { botToken: "TEST", chatId: "42", protectContent: true, skipDedup: true });
  check(res.success && captured?.protect_content === true && captured.chat_id === "42", "13. Signal messages are sent with protect_content (no forward / save / copy)", JSON.stringify(captured));
  await sendTelegramMessage("test2", { botToken: "TEST", chatId: "42", skipDedup: true });
  check(captured?.protect_content === undefined, "14. Other messages are not restricted");
  globalThis.fetch = realFetch;

  console.log("==================================================");
  console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
  console.log("==================================================");
  process.exit(failed > 0 ? 1 : 0);
})();
