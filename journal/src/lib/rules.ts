import type { ClosedTrade, RuleChecklistState, TradeStats } from "./types";

export const DEFAULT_CHECKLIST: RuleChecklistState = {
  mssConfirmed: false,
  fibDiscountOk: false,
  cisdConfirmed: false,
  sessionOk: false,
  riskOneRDefined: false,
  targetAtLeast2R: false,
  noEarlyPartialBefore2R: false,
};

export const RULE_LABELS: Record<keyof RuleChecklistState, string> = {
  mssConfirmed: "1H+ MSS 확인",
  fibDiscountOk: "Fib 0.5 discount/premium",
  cisdConfirmed: "5~15m CISD 확인",
  sessionOk: "유럽/뉴욕 세션만",
  riskOneRDefined: "1R(손절) 사전 정의",
  targetAtLeast2R: "2R 경로 확인 후 진입",
  noEarlyPartialBefore2R: "2R 전 조기 반익절 안 함",
};

export const STRATEGY_BRIEF = `
ICT BTC 전략 규칙:
1) 아시아 세션 거래 금지. 유럽/뉴욕만.
2) 1H 이상에서 MSS 확인 후에만 방향 신뢰.
3) Fib 0.5 기준 discount(롱)/premium(숏)에서만 관심.
4) 5m/10m/15m CISD로 타이밍 진입.
5) 트레이드당 리스크는 계좌의 약 5%(≈$25~$30)로 1R 고정.
6) 2R 목표가 구조적으로 안 보이면 진입하지 않음.
7) 반익절은 2R에서만 50%. 그 전 조기 반익절 금지.
8) 나머지 포지션은 BE 보호 후 3R 또는 구조 청산.
`.trim();

export function outcomeOf(trade: ClosedTrade): "win" | "loss" | "breakeven" {
  if (Math.abs(trade.pnl) < 1) return "breakeven";
  return trade.pnl > 0 ? "win" : "loss";
}

export function computeStats(trades: ClosedTrade[]): TradeStats {
  const wins = trades.filter((t) => t.pnl > 1);
  const losses = trades.filter((t) => t.pnl < -1);
  const breakevens = trades.filter((t) => Math.abs(t.pnl) <= 1);
  const avgWin =
    wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
  const avgLoss =
    losses.length > 0
      ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length
      : 0;
  const winRate = trades.length ? wins.length / trades.length : 0;
  const expectancy =
    trades.length === 0
      ? 0
      : winRate * avgWin + (1 - winRate) * avgLoss;

  return {
    count: trades.length,
    wins: wins.length,
    losses: losses.length,
    breakevens: breakevens.length,
    winRate,
    netPnl: trades.reduce((s, t) => s + t.pnl, 0),
    avgWin,
    avgLoss,
    expectancy,
  };
}

/** Price distance implied by PnL and size. */
export function priceMove(trade: ClosedTrade): number {
  if (!trade.size) return 0;
  return Math.abs(trade.exitPrice - trade.entryPrice);
}

/**
 * Estimate R using planned risk dollars (default $25).
 * Positive = reward in R, negative = loss in R.
 */
export function estimateR(trade: ClosedTrade, riskDollars = 25): number | null {
  if (!riskDollars) return null;
  return trade.pnl / riskDollars;
}
