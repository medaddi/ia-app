import { Candle } from "./types";
import { NewsEvent } from "./news";

/** Everything a strategy needs. Candle arrays may contain the forming candle; strategies cut it off. */
export interface StrategyInput {
  candles: Partial<Record<"M5" | "M15" | "H1" | "H4" | "D1", Candle[]>>;
  nowSec: number;
  livePrice: number;
  spread: number | null; // price units; null = unknown, the config's assumed spread is used
  isMarketOpen: boolean;
  isRealData: boolean;
  dataSource: string;
  news: { events: NewsEvent[]; source: string };
  day: { trades: number; losses: number };
}
