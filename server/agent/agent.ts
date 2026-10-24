/**
 * In-app AI agent.
 * - Answers only from the deterministic strategy results (context.ts), never from its own analysis.
 * - With GEMINI_API_KEY it asks Gemini using the generated system prompt, then rejects the answer
 *   if it contains any price that is not in the context (no invented levels). Otherwise, or on
 *   rejection, it returns a deterministic answer in the required format.
 * - Explains any drawing on the chart from the drawing's own data and the shared definitions.
 */

import { GoogleGenAI } from "@google/genai";
import { StrategyResult, Drawing } from "../strategies/shared/result";
import { buildAgentContext } from "./context";
import { buildSystemPrompt } from "./systemPrompt";
import { buildExplanation } from "./explain";
import { validateSignal } from "./validator";

export type Lang = "en" | "fr" | "ar" | "darija";

export function detectLang(text: string): Lang {
  if (/[؀-ۿ]/.test(text)) return "ar";
  const t = ` ${text.toLowerCase()} `;
  if (/\b(chno|chnou|kifach|kifash|wach|wash|dyal|dial|bghit|safqa|daba|3lach|3lash|mzn|khas|kayn|kayna|wla|bzaf|f had|dyali)\b/.test(t)) return "darija";
  if (/\b(pourquoi|quel|quelle|est-ce|analyse|le |la |les |pas de|achat|vente|tendance)\b/.test(t)) return "fr";
  return "en";
}

export function symbolsFromQuestion(text: string): ("XAUUSD" | "EURUSD")[] {
  const t = text.toLowerCase();
  const gold = /(xau|gold|dhab|dahab|ذهب|\bor\b)/.test(t);
  const eur = /(eur|euro|يورو|اليورو)/.test(t);
  if (gold && !eur) return ["XAUUSD"];
  if (eur && !gold) return ["EURUSD"];
  return ["XAUUSD", "EURUSD"];
}

const L = {
  en: { bias: "Bias", levels: "Key levels", setup: "Setup status", plan: "Plan", noTrade: "NO TRADE", missing: "missing rule", risk: "Risk", riskText: "1% of equity per trade, losses are part of trading; nothing here is guaranteed.", data: "Data not usable", entry: "Entry", lot: "lot per $1k" },
  fr: { bias: "Biais", levels: "Niveaux clés", setup: "État du setup", plan: "Plan", noTrade: "PAS DE TRADE", missing: "règle manquante", risk: "Risque", riskText: "1 % du capital par trade ; les pertes font partie du trading, rien n'est garanti.", data: "Données inutilisables", entry: "Entrée", lot: "lot par 1k$" },
  ar: { bias: "الاتجاه", levels: "المستويات المهمة", setup: "حالة الإعداد", plan: "الخطة", noTrade: "لا صفقة", missing: "الشرط الناقص", risk: "المخاطرة", riskText: "1% من الرصيد لكل صفقة، والخسارة جزء من التداول؛ لا شيء مضمون.", data: "البيانات غير صالحة", entry: "الدخول", lot: "لوت لكل 1000$" },
  darija: { bias: "Ttijah (bias)", levels: "Niveaux mohimmin", setup: "7alat setup", plan: "Plan", noTrade: "MA KAYNACH TRADE", missing: "chart li na9es", risk: "Risk", riskText: "1% mn l'capital f kol trade; l'khsara jz2 mn trading, walo madmoun.", data: "Data ma salhach", entry: "Dkhoul", lot: "lot l kol 1000$" },
};

function rule(c: StrategyResult["checklist"][number], lang: Lang) {
  return lang === "ar" ? c.ruleAr : c.rule;
}

export function deterministicAnswer(results: StrategyResult[], lang: Lang): string {
  const t = L[lang];
  return results.map(r => {
    const d = r.spec.decimals;
    const f = (v: number) => Number(v).toFixed(d);
    const head = `**${r.symbol} — ${r.strategyName}** (${r.timeframes.bias} → ${r.timeframes.entry})`;
    if (!r.dataQuality.ok) return `${head}\n${t.data}: ${r.dataQuality.reason}`;
    const facts = r.facts as any;
    const levels = (facts.levels || [])
      .filter((l: any) => l.untaken !== false && l.kind !== "ROUND")
      .sort((a: any, b: any) => Math.abs(a.price - r.price) - Math.abs(b.price - r.price))
      .slice(0, 5)
      .map((l: any) => `${l.label || l.kind} ${f(l.price)}`).join(" · ");
    const checklist = r.checklist.map(c => `${c.passed ? "✔" : "✘"} ${rule(c, lang)} — ${c.detail}`).join("\n");
    const s = r.setup;
    let plan: string;
    if (s && r.status === "SIGNAL") {
      const v = validateSignal(r);
      plan = `${s.direction} ${s.entryType} · ${t.entry} ${f(s.entry)} · SL ${f(s.sl)} (${s.slPips} pips) · TP1 ${f(s.tp1)} · TP2 ${f(s.tp2)} (1:${s.rrTp2.toFixed(1)}) · TP3 ${f(s.tp3)} · ${s.lots["1000$"] ?? 0} ${t.lot} · score ${v.score}/100${v.approved ? "" : ` · ✘ ${v.issues.join("; ")}`}`;
    } else if (s && r.status === "WATCH") {
      plan = `WATCH (score ${r.score} < 75): ${s.direction} ${f(s.entry)} / SL ${f(s.sl)} / TP2 ${f(s.tp2)} — ${t.noTrade}`;
    } else {
      plan = `${t.noTrade} — ${t.missing}: ${r.rejection || r.headline}`;
    }
    return [
      head,
      `**${t.bias}:** ${r.bias.direction} — ${r.bias.detail}`,
      `**${t.levels}:** ${levels || "—"}`,
      `**${t.setup}:** ${r.status}${s ? ` (score ${r.score})` : ""}\n${checklist}`,
      `**${t.plan}:** ${plan}`,
      s && r.status === "SIGNAL" ? buildExplanation(r, lang === "ar" ? "ar" : "en") : "",
      `**${t.risk}:** ${t.riskText}`,
    ].filter(Boolean).join("\n");
  }).join("\n\n");
}

/** Every price-like number in the answer must exist in the context (at the instrument's precision). */
export function inventsNumbers(answer: string, context: unknown): string[] {
  const allowed = new Set<string>();
  const walk = (v: unknown) => {
    if (typeof v === "number" && Number.isFinite(v)) { allowed.add(v.toFixed(2)); allowed.add(v.toFixed(4)); allowed.add(v.toFixed(5)); allowed.add(String(v)); }
    else if (typeof v === "string") for (const m of v.match(/\d+\.\d+/g) || []) allowed.add(m);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  walk(context);
  const bad: string[] = [];
  for (const m of answer.match(/\b\d{1,5}\.\d{2,5}\b/g) || []) {
    const n = Number(m);
    if (n < 0.5 || n > 100000) continue;
    const ok = allowed.has(m) || allowed.has(n.toFixed(2)) || allowed.has(n.toFixed(4)) || allowed.has(n.toFixed(5));
    if (!ok) bad.push(m);
  }
  return bad;
}

let gemini: GoogleGenAI | null = null;
function client(): GoogleGenAI | null {
  if (!process.env.GEMINI_API_KEY || process.env.GEMINI_API_KEY === "MY_GEMINI_API_KEY") return null;
  gemini ||= new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  return gemini;
}

export async function askAgent(question: string, results: StrategyResult[]): Promise<{ answer: string; source: "gemini" | "deterministic"; lang: Lang; note?: string }> {
  const lang = detectLang(question);
  const wanted = symbolsFromQuestion(question);
  const scoped = results.filter(r => wanted.includes(r.symbol));
  const context = buildAgentContext(scoped);
  const fallback = deterministicAnswer(scoped, lang);
  const ai = client();
  if (!ai) return { answer: fallback, source: "deterministic", lang };
  try {
    const res = await ai.models.generateContent({
      model: process.env.AGENT_MODEL || "gemini-2.5-flash",
      contents: `CONTEXT (deterministic strategy output, the only source of truth):\n${JSON.stringify(context)}\n\nUser language: ${lang}\nUser question: ${question}`,
      config: { systemInstruction: buildSystemPrompt(), temperature: 0.1 },
    });
    const text = (res.text || "").trim();
    if (!text) return { answer: fallback, source: "deterministic", lang, note: "Empty model reply" };
    const invented = inventsNumbers(text, context);
    if (invented.length) return { answer: fallback, source: "deterministic", lang, note: `Model reply rejected: prices not in the data (${invented.slice(0, 3).join(", ")})` };
    return { answer: text, source: "gemini", lang };
  } catch (err: any) {
    return { answer: fallback, source: "deterministic", lang, note: `Model unavailable: ${err?.message || err}` };
  }
}

/** Explains one chart drawing from its own data and the shared definitions. */
export function explainDrawing(r: StrategyResult, drawing: Drawing, lang: Lang): string {
  const d = r.spec.decimals;
  const f = (v: number) => Number(v).toFixed(d);
  const time = (t: number | null) => (t ? new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC" : "now");
  const tf = drawing.tf || "";
  const ar = lang === "ar";
  const id = drawing.id;
  if (drawing.layer === "structure") {
    const choch = drawing.text?.includes("CHoCH");
    return ar
      ? `${choch ? "CHoCH (تغير الطابع)" : "BOS (كسر الهيكل)"} على ${tf}: شمعة أغلقت ${drawing.color === "bull" ? "فوق" : "تحت"} القمة/القاع المؤكد عند ${f(drawing.p1)} (تكوّن ${time(drawing.t1)}، كُسر ${time(drawing.t2)}). ${choch ? "هذا أول إغلاق عكس الاتجاه السابق." : "إغلاق في اتجاه الترند الحالي."}`
      : `${choch ? "CHoCH (change of character)" : "BOS (break of structure)"} on ${tf}: a candle CLOSED ${drawing.color === "bull" ? "above" : "below"} the confirmed swing at ${f(drawing.p1)} (formed ${time(drawing.t1)}, broken ${time(drawing.t2)}). ${choch ? "It is the first close against the previous trend." : "The close is in the direction of the current trend."}`;
  }
  if (drawing.layer === "fvg") {
    return ar
      ? `فجوة FVG على ${tf} بين ${f(drawing.p2!)} و ${f(drawing.p1)}: الشمعة الأولى والثالثة لا تتلامسان. منتصفها ${f((drawing.p1 + drawing.p2!) / 2)}. ${drawing.faded ? "تم ملء 50% منها (مستعملة)." : "لم يُملأ نصفها بعد."}`
      : `${tf} Fair Value Gap ${f(drawing.p2!)}–${f(drawing.p1)}: candle 1 and candle 3 do not overlap, leaving an imbalance (size ≥ 0.25 × ATR). Its 50% line is ${f((drawing.p1 + drawing.p2!) / 2)}. ${drawing.faded ? "Price has already filled 50%, so it is mitigated." : "Price has not filled 50% yet."}`;
  }
  if (drawing.layer === "ob") {
    return ar
      ? `بلوك أوامر ${drawing.color === "bull" ? "طلب" : "عرض"} على ${tf} (${f(drawing.p2!)}–${f(drawing.p1)}): آخر شمعة عكسية قبل الاندفاع (جسم > 1.5× المتوسط) الذي كسر الهيكل. ${drawing.faded ? "السعر رجع إليه (مستعمل)." : "لم يُختبر بعد."}`
      : `${tf} ${drawing.color === "bull" ? "demand" : "supply"} order block ${f(drawing.p2!)}–${f(drawing.p1)}: the last opposite-coloured candle before the displacement (body > 1.5× the 20-candle average) that broke structure. ${drawing.faded ? "Price has returned into it (mitigated)." : "Not revisited yet."}`;
  }
  if (drawing.layer === "levels" || drawing.layer === "liquidity") {
    if (drawing.kind === "marker") return ar ? `سحب سيولة عند ${f(drawing.p1)} (${time(drawing.t1)}): ذيل تجاوز المستوى ثم أُغلقت الشمعة داخله.` : `Liquidity sweep at ${f(drawing.p1)} (${time(drawing.t1)}): the wick went beyond the level and the candle closed back inside.`;
    const what: Record<string, string> = { PDH: "previous day high", PDL: "previous day low", PWH: "previous week high", PWL: "previous week low", "$$$": "equal highs/lows (resting stops)", "Asia H": "Asian session high", "Asia L": "Asian session low", "London H": "London session high", "London L": "London session low" };
    return ar ? `مستوى ${drawing.text} عند ${f(drawing.p1)}: سيولة (أوامر وقف) تتجمع هنا.` : `${drawing.text} at ${f(drawing.p1)}: ${what[drawing.text || ""] || "key level"}. Stops rest beyond it, which is why the strategy watches for a sweep here.`;
  }
  if (drawing.layer === "fib") return ar ? `فيبوناتشي ${drawing.text} لآخر موجة اندفاع H1 عند ${f(drawing.p1)}.` : `Fibonacci ${drawing.text} of the last H1 impulse leg at ${f(drawing.p1)}; the EURUSD pullback zone is 50–61.8%.`;
  if (drawing.layer === "sessions") return ar ? `جلسة ${drawing.text}.` : `${drawing.text} session window (${time(drawing.t1)} → ${time(drawing.t2)}).`;
  if (drawing.layer === "trade" && r.setup) return buildExplanation(r, ar ? "ar" : "en");
  return ar ? `عنصر ${id}.` : `Drawing ${id}.`;
}
