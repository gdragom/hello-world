"use client";

import type { ClosedTrade } from "@/lib/types";
import { estimateR, outcomeOf } from "@/lib/rules";

function fmtTime(ms: number) {
  return new Date(ms).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type Props = {
  trades: ClosedTrade[];
  selectedId: string | null;
  riskDollars: number;
  onSelect: (trade: ClosedTrade) => void;
};

export function TradeList({
  trades,
  selectedId,
  riskDollars,
  onSelect,
}: Props) {
  return (
    <div className="trade-list">
      {trades.map((trade) => {
        const outcome = outcomeOf(trade);
        const r = estimateR(trade, riskDollars);
        return (
          <button
            key={trade.id}
            type="button"
            className={`trade-row ${selectedId === trade.id ? "active" : ""}`}
            onClick={() => onSelect(trade)}
          >
            <div className="trade-row-top">
              <span className={`side-pill ${trade.side}`}>{trade.side}</span>
              <span className={`pnl ${outcome}`}>
                {trade.pnl >= 0 ? "+" : ""}
                {trade.pnl.toFixed(2)}
              </span>
            </div>
            <div className="trade-row-meta">
              <span>{fmtTime(trade.closeTime)}</span>
              <span>
                {trade.size} BTC · {r !== null ? `${r.toFixed(2)}R` : "—"}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
