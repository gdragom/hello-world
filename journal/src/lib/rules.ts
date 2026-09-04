import type { ClosedTrade, RuleChecklistState, TradeStats } from "./types";

export const DEFAULT_CHECKLIST: RuleChecklistState = {
  dailyBias: false,
  mssConfirmed: false,
  fibDiscountOk: false,
  cisdConfirmed: false,
  sessionOk: false,
  noEarlyPartialBefore2R: false,
};

export const RULE_LABELS: Record<keyof RuleChecklistState, string> = {
  dailyBias: "Daily Bias 확인",
  mssConfirmed: "1H+ MSS 확인",
  fibDiscountOk: "Fib 0.5 discount/premium",
  cisdConfirmed: "5~15m CISD 확인",
  sessionOk: "유럽/뉴욕 세션만",
  noEarlyPartialBefore2R: "2R 전 조기 반익절 안 함",
};

export function normalizeChecklist(
  partial?: Partial<RuleChecklistState> | Record<string, boolean>
): RuleChecklistState {
  const next = { ...DEFAULT_CHECKLIST };
  if (!partial) return next;
  (Object.keys(DEFAULT_CHECKLIST) as (keyof RuleChecklistState)[]).forEach(
    (key) => {
      if (typeof partial[key] === "boolean") next[key] = partial[key];
    }
  );
  return next;
}

export const STRATEGY_BRIEF = `
ICT BTC 전략 규칙:
1) Daily Bias 확인 후에만 거래.
2) 아시아 세션 거래 금지. 유럽/뉴욕만.
3) 1H 이상에서 MSS 확인 후에만 방향 신뢰.
4) Fib 0.5 기준 discount(롱)/premium(숏)에서만 관심.
5) 5m/10m/15m CISD로 타이밍 진입.
6) 반익절은 2R에서만 50%. 그 전 조기 반익절 금지.
7) 나머지 포지션은 BE 보호 후 3R 또는 구조 청산.
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

/** Price distance between entry and exit (손절/청산 범위). */
export function stopRange(trade: ClosedTrade): number {
  return Math.abs(trade.exitPrice - trade.entryPrice);
}

/** $ risk if stopped across that range: size × |entry − exit|. */
export function stopLossUsd(trade: ClosedTrade): number | null {
  if (!trade.size) return null;
  const risk = trade.size * stopRange(trade);
  return risk > 0 ? risk : null;
}

export function averageStopRisk(trades: ClosedTrade[]): number {
  const risks = trades
    .map((t) => stopLossUsd(t))
    .filter((n): n is number => n !== null);
  if (!risks.length) return 0;
  return risks.reduce((sum, n) => sum + n, 0) / risks.length;
}

/** Realized R vs the stop sized from this trade's entry/exit/size. */
export function estimateR(trade: ClosedTrade): number | null {
  const risk = stopLossUsd(trade);
  if (!risk) return null;
  return trade.pnl / risk;
}
