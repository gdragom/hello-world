export type TradeSide = "long" | "short";

export type TradeOutcome = "win" | "loss" | "breakeven";

export interface ClosedTrade {
  id: string;
  symbol: string;
  side: TradeSide;
  marginMode: string;
  openTime: number;
  closeTime: number;
  entryPrice: number;
  exitPrice: number;
  size: number;
  pnl: number;
  fundingFee?: number;
  openFee?: number;
  closeFee?: number;
  source: "bitget" | "demo";
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface JournalScreenshot {
  id: string;
  name: string;
  dataUrl: string;
  createdAt: number;
}

export interface JournalEntry {
  tradeId: string;
  entryReason: string;
  exitReason: string;
  checklist: RuleChecklistState;
  tags: string[];
  screenshots: JournalScreenshot[];
  updatedAt: number;
}

export interface RuleChecklistState {
  dailyBias: boolean;
  hourlyCandleStructuralSweep: boolean;
  mssConfirmed: boolean;
  fibDiscountOk: boolean;
  cisdConfirmed: boolean;
  sessionOk: boolean;
  noEarlyPartialBefore2R: boolean;
}

export interface PeriodNote {
  id: string;
  note: string;
  updatedAt: number;
}

export interface ReviewResult {
  tradeId: string;
  verdict: "process_win" | "process_loss" | "mixed" | "unclear";
  summary: string;
  kept: string[];
  broken: string[];
  marketNote: string;
  suggestions: string[];
  estimatedR: number | null;
  generatedAt: number;
  mode: "rules" | "ai";
}

export interface TradeStats {
  count: number;
  wins: number;
  losses: number;
  breakevens: number;
  winRate: number;
  netPnl: number;
  avgWin: number;
  avgLoss: number;
  expectancy: number;
}
