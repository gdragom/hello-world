"use client";

import type { TradeStats } from "@/lib/types";

type Props = {
  stats: TradeStats;
  source: string;
  riskDollars: number;
};

export function StatsBar({ stats, source, riskDollars }: Props) {
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
        <span className="label">Source</span>
        <strong className="source">{source}</strong>
      </div>
    </section>
  );
}
