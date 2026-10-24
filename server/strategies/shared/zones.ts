/**
 * Fair Value Gaps and Order Blocks.
 * - FVG: candle1.high < candle3.low (bullish) / candle1.low > candle3.high (bearish), gap >= minAtr × ATR(14).
 *   Mitigated once price fills 50% of the gap, filled at 100%.
 * - Order Block: last opposite-coloured candle before the displacement that caused a BOS/CHoCH.
 *   Only valid if the displacement body > mult × average body (20).
 */

import { Candle, Direction } from "./types";
import { StructureEvent } from "./structure";

export interface Fvg {
  id: string;
  direction: Direction;
  top: number;
  bottom: number;
  ce: number;
  startTime: number;
  createdIndex: number;
  createdTime: number;
  sizeAtr: number;
  state: "OPEN" | "MITIGATED" | "FILLED";
  mitigatedTime: number | null;
  filledTime: number | null;
}

export interface OrderBlock {
  id: string;
  direction: Direction;
  top: number;
  bottom: number;
  mid: number;
  time: number;
  index: number;
  breakTime: number;
  breakIndex: number;
  state: "OPEN" | "MITIGATED" | "BROKEN";
  mitigatedTime: number | null;
  brokenTime: number | null;
}

export function detectFvgs(c: Candle[], atr: number[], minAtr: number, tf: string): Fvg[] {
  const out: Fvg[] = [];
  for (let k = 2; k < c.length; k++) {
    const a = atr[k];
    if (!(a > 0)) continue;
    const c1 = c[k - 2];
    const c3 = c[k];
    let fvg: Fvg | null = null;
    if (c1.high < c3.low && c3.low - c1.high >= minAtr * a) {
      fvg = mk("BULLISH", c3.low, c1.high);
    } else if (c1.low > c3.high && c1.low - c3.high >= minAtr * a) {
      fvg = mk("BEARISH", c1.low, c3.high);
    }
    if (!fvg) continue;
    for (let m = k + 1; m < c.length; m++) {
      const x = c[m];
      if (fvg.direction === "BULLISH") {
        if (x.low <= fvg.bottom) { fvg.state = "FILLED"; fvg.filledTime = x.time; fvg.mitigatedTime ??= x.time; break; }
        if (x.low <= fvg.ce && fvg.state === "OPEN") { fvg.state = "MITIGATED"; fvg.mitigatedTime = x.time; }
      } else {
        if (x.high >= fvg.top) { fvg.state = "FILLED"; fvg.filledTime = x.time; fvg.mitigatedTime ??= x.time; break; }
        if (x.high >= fvg.ce && fvg.state === "OPEN") { fvg.state = "MITIGATED"; fvg.mitigatedTime = x.time; }
      }
    }
    out.push(fvg);

    function mk(direction: Direction, top: number, bottom: number): Fvg {
      return {
        id: `${tf}-FVG-${c1.time}`, direction, top, bottom, ce: (top + bottom) / 2,
        startTime: c1.time, createdIndex: k, createdTime: c3.time, sizeAtr: (top - bottom) / a,
        state: "OPEN", mitigatedTime: null, filledTime: null,
      };
    }
  }
  return out;
}

export function detectOrderBlocks(c: Candle[], events: StructureEvent[], tf: string): OrderBlock[] {
  const out: OrderBlock[] = [];
  for (const e of events) {
    if (e.displacementIndex === null) continue;
    const bull = e.direction === "BULLISH";
    let obIdx = -1;
    for (let i = e.displacementIndex - 1; i >= Math.max(0, e.legStartIndex - 3); i--) {
      if (bull ? c[i].close < c[i].open : c[i].close > c[i].open) { obIdx = i; break; }
    }
    if (obIdx < 0) continue;
    const x = c[obIdx];
    const ob: OrderBlock = {
      id: `${tf}-OB-${x.time}`, direction: e.direction, top: x.high, bottom: x.low, mid: (x.high + x.low) / 2,
      time: x.time, index: obIdx, breakTime: e.breakTime, breakIndex: e.breakIndex,
      state: "OPEN", mitigatedTime: null, brokenTime: null,
    };
    for (let m = e.breakIndex + 1; m < c.length; m++) {
      const y = c[m];
      if (bull ? y.close < ob.bottom : y.close > ob.top) { ob.state = "BROKEN"; ob.brokenTime = y.time; break; }
      if (ob.state === "OPEN" && (bull ? y.low <= ob.top : y.high >= ob.bottom)) { ob.state = "MITIGATED"; ob.mitigatedTime = y.time; }
    }
    if (!out.some(o => o.id === ob.id)) out.push(ob);
  }
  return out;
}
