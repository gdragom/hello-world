"use client";

import type { TradeStats } from "@/lib/types";

type Props = {
  stats: TradeStats;
  source: string;
  riskDollars: number;
  availableBalance?: number | null;
};

function formatUsd(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function StatsBar({
  stats,
  source,
  riskDollars,
  availableBalance,
}: Props) {
  return (
    <section className="stats-bar">
      <div>
        <span className="label">Net PnL</span>
        <strong className={stats.netPnl >= 0 ? "up" : "down"}>
          {stats.netPnl >= 0 ? "+" : ""}
          ${stats.netPnl.toFixed(2)}
        </strong>
      </div>
      <div>
        <span className="label">Win rate</span>
        <strong>{(stats.winRate * 100).toFixed(0)}%</strong>
      </div>
      <div>
        <span className="label">Expectancy</span>
        <strong className={stats.expectancy >= 0 ? "up" : "down"}>
          ${stats.expectancy.toFixed(2)}
        </strong>
      </div>
      <div>
        <span className="label">Avg W / L</span>
        <strong>
          ${stats.avgWin.toFixed(1)} / ${stats.avgLoss.toFixed(1)}
        </strong>
      </div>
      <div>
        <span className="label">Avg 1R</span>
        <strong>${riskDollars.toFixed(2)}</strong>
      </div>
      <div>
        <span className="label">Available</span>
        <strong>
          {availableBalance == null ? "—" : `$${formatUsd(availableBalance)}`}
        </strong>
      </div>
      <div>
        <span className="label">Source</span>
        <strong className="source">{source}</strong>
      </div>
    </section>
  );
}
