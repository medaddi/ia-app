/**
 * Converts detector output into chart drawings, the way a trader marks a chart by hand:
 * few objects, most recent first, max `maxPerType` per type, higher-timeframe objects
 * prefixed with their timeframe ("H1 OB").
 */

import { Drawing } from "./result";
import { Swing, StructureEvent } from "./structure";
import { Fvg, OrderBlock } from "./zones";
import { Level, Sweep } from "./liquidity";
import { SessionRange } from "./sessions";
import { TradeSetup } from "./result";

const prefix = (tf: string, chartTf: string) => (tf === chartTf ? "" : `${tf} `);

export function structureDrawings(events: StructureEvent[], tf: string, entryTf: string, max: number): Drawing[] {
  return events.slice(-max).map(e => ({
    id: `${tf}-${e.type}-${e.breakTime}`,
    layer: "structure" as const,
    kind: "hline" as const,
    tf,
    t1: e.pivotTime,
    t2: e.breakTime,
    p1: e.level,
    text: `${prefix(tf, entryTf)}${e.type === "CHOCH" ? "CHoCH" : "BOS"}`,
    color: e.direction === "BULLISH" ? "bull" as const : "bear" as const,
    style: e.type === "CHOCH" ? "dashed" as const : "solid" as const,
  }));
}

export function swingDrawings(swings: Swing[], tf: string, max: number): Drawing[] {
  return swings.filter(s => s.label).slice(-max - 1).map(s => ({
    id: `${tf}-SW-${s.kind}-${s.time}`,
    layer: "swings" as const,
    kind: "label" as const,
    tf,
    t1: s.time,
    t2: s.time,
    p1: s.price,
    text: s.label!,
    color: "muted" as const,
    position: s.kind === "HIGH" ? "above" as const : "below" as const,
  }));
}

export function fvgDrawings(fvgs: Fvg[], tf: string, entryTf: string, max: number): Drawing[] {
  return fvgs.filter(f => f.state !== "FILLED").slice(-max).map(f => ({
    id: f.id,
    layer: "fvg" as const,
    kind: "box" as const,
    tf,
    t1: f.startTime,
    t2: f.mitigatedTime,
    p1: f.top,
    p2: f.bottom,
    text: `${prefix(tf, entryTf)}FVG`,
    color: f.direction === "BULLISH" ? "bull" as const : "bear" as const,
    faded: f.state === "MITIGATED",
    midline: true,
  }));
}

export function obDrawings(obs: OrderBlock[], tf: string, entryTf: string, max: number): Drawing[] {
  return obs.filter(o => o.state !== "BROKEN").slice(-max).map(o => ({
    id: o.id,
    layer: "ob" as const,
    kind: "box" as const,
    tf,
    t1: o.time,
    t2: null,
    p1: o.top,
    p2: o.bottom,
    text: `${prefix(tf, entryTf)}${o.direction === "BULLISH" ? "Demand OB" : "Supply OB"}`,
    color: o.direction === "BULLISH" ? "bull" as const : "bear" as const,
    faded: o.state === "MITIGATED",
  }));
}

const LEVEL_LAYER: Record<string, "levels" | "liquidity"> = {
  PDH: "levels", PDL: "levels", PWH: "levels", PWL: "levels",
  ASIA_H: "liquidity", ASIA_L: "liquidity", PSH: "liquidity", PSL: "liquidity",
  EQH: "liquidity", EQL: "liquidity", ROUND: "levels", SWING_H: "liquidity", SWING_L: "liquidity",
};

export function levelDrawings(levels: Level[]): Drawing[] {
  return levels.map(l => ({
    id: `LV-${l.id}`,
    layer: LEVEL_LAYER[l.kind],
    kind: "hline" as const,
    tf: "",
    t1: l.time,
    t2: null,
    p1: l.price,
    text: l.label,
    color: l.kind === "EQH" || l.kind === "EQL" ? "liquidity" as const : "muted" as const,
    style: l.kind === "EQH" || l.kind === "EQL" || l.kind === "ROUND" ? "dotted" as const : "dashed" as const,
  }));
}

export function sweepDrawings(sweeps: Sweep[], tf: string, max: number): Drawing[] {
  return sweeps.slice(-max).map(s => ({
    id: s.id,
    layer: "liquidity" as const,
    kind: "marker" as const,
    tf,
    t1: s.time,
    t2: s.time,
    p1: s.extreme,
    text: "Sweep",
    color: "gold" as const,
    position: s.level.side === "HIGH" ? "above" as const : "below" as const,
  }));
}

export function sessionDrawings(sessions: SessionRange[]): Drawing[] {
  const out: Drawing[] = [];
  for (const s of sessions) {
    const color = s.name === "Asia" ? "asia" as const : s.name === "London" ? "london" as const : "ny" as const;
    out.push({ id: `SES-${s.name}-${s.dateKey}`, layer: "sessions", kind: "session", tf: "", t1: s.startSec, t2: s.endSec, p1: s.high, p2: s.low, text: s.name, color });
    if (s.name === "Asia") {
      out.push({ id: `SES-AH-${s.dateKey}`, layer: "sessions", kind: "box", tf: "", t1: s.startSec, t2: s.endSec, p1: s.high, p2: s.low, text: `Asia range`, color: "asia" });
    }
  }
  return out;
}

export function tradeDrawings(setup: TradeSetup, entryTf: string, lotText: string): Drawing[] {
  const bull = setup.direction === "BUY";
  const t1 = setup.signalTime;
  // Box spans the life of the order: pending → until expiry; filled → until exit (open = right edge)
  const lc = setup.lifecycle;
  const cancel = lc.events.find(e => e.type === "CANCEL" || e.type === "EXPIRE");
  const end = lc.fillTime !== null ? lc.exitTime : cancel ? cancel.time : setup.expiresAt;
  const rrText = `1:${setup.rrTp2.toFixed(1)}`;
  const out: Drawing[] = [
    { id: `TR-TP-${setup.id}`, layer: "trade", kind: "box", tf: entryTf, t1, t2: end, p1: setup.entry, p2: setup.tp2, text: `TP2 ${setup.tp2} · ${rrText}`, color: "bull" },
    { id: `TR-SL-${setup.id}`, layer: "trade", kind: "box", tf: entryTf, t1, t2: end, p1: setup.entry, p2: setup.sl, text: `SL ${setup.sl} · ${setup.slPips}p · ${lotText}`, color: "bear" },
    { id: `TR-EN-${setup.id}`, layer: "trade", kind: "hline", tf: entryTf, t1, t2: end, p1: setup.entry, text: `Entry ${setup.entry}`, color: "entry", style: "solid" },
    { id: `TR-T1-${setup.id}`, layer: "trade", kind: "hline", tf: entryTf, t1, t2: end, p1: setup.tp1, text: `TP1 ${setup.tp1}`, color: "bull", style: "dashed" },
    { id: `TR-T3-${setup.id}`, layer: "trade", kind: "hline", tf: entryTf, t1, t2: end, p1: setup.tp3, text: `TP3 ${setup.tp3}`, color: "bull", style: "dotted" },
  ];
  for (const e of setup.lifecycle.events) {
    if ((e.type === "FILL" && setup.entryType === "LIMIT") || e.type === "TP1" || e.type === "TP2" || e.type === "TP3" || e.type === "SL" || e.type === "BE_EXIT" || e.type === "TRAIL_EXIT") {
      out.push({ id: `TR-EV-${e.type}-${setup.id}`, layer: "trade", kind: "marker", tf: entryTf, t1: e.time, t2: null, p1: e.price, text: e.type === "FILL" ? "Filled" : e.type.replace("_", " "), color: e.type === "SL" ? "bear" : e.type === "FILL" ? "entry" : "bull", position: bull === (e.type === "SL") ? "below" : "above" });
    }
  }
  return out;
}

/**
 * Declutters zones like a trader would: when two boxes of the same layer and side overlap in
 * price by more than half of the smaller one, only the newest is kept.
 */
export function declutterZones(drawings: Drawing[]): Drawing[] {
  const boxes = drawings.filter(d => d.kind === "box" && (d.layer === "fvg" || d.layer === "ob") && d.p2 !== undefined);
  const drop = new Set<string>();
  const sorted = [...boxes].sort((a, b) => b.t1 - a.t1); // newest first
  for (let i = 0; i < sorted.length; i++) {
    const a = sorted[i];
    if (drop.has(a.id)) continue;
    const aTop = Math.max(a.p1, a.p2!), aBot = Math.min(a.p1, a.p2!);
    for (let j = i + 1; j < sorted.length; j++) {
      const b = sorted[j];
      if (drop.has(b.id) || b.color !== a.color) continue;
      const bTop = Math.max(b.p1, b.p2!), bBot = Math.min(b.p1, b.p2!);
      const overlap = Math.min(aTop, bTop) - Math.max(aBot, bBot);
      if (overlap > 0.5 * Math.min(aTop - aBot, bTop - bBot)) drop.add(b.id);
    }
  }
  return drawings.filter(d => !drop.has(d.id));
}
