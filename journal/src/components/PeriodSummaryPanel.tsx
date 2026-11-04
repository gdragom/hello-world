"use client";

import { useState } from "react";
import type { ClosedTrade, PeriodSummaryResult } from "@/lib/types";

type Props = {
  trades: ClosedTrade[];
  monthFilter: string | "all";
};

function fmtMoney(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

export function PeriodSummaryPanel({ trades, monthFilter }: Props) {
  const [summary, setSummary] = useState<PeriodSummaryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run(range: "week" | "month" | "filtered", useAi: boolean) {
    setLoading(true);
    setError("");
    try {
      const body: Record<string, unknown> = { range, useAi };
      if (range === "month") {
        body.month =
          monthFilter === "all"
            ? new Date().toISOString().slice(0, 7)
            : monthFilter;
      }
      if (range === "filtered") {
        body.trades = trades;
      }
      const res = await fetch("/api/period-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "failed");
      setSummary(json.summary as PeriodSummaryResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "요약 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="period-summary">
      <div className="period-summary-head">
        <div>
          <p className="section-title">주간 · 월간 복기</p>
          <p className="attach-hint">
            공부용 요약 — 숫자 + 자주 깨진 규칙 + 다음 포커스
          </p>
        </div>
        <div className="period-summary-actions">
          <button
            type="button"
            className="secondary"
            disabled={loading}
            onClick={() => void run("week", false)}
          >
            최근 7일
          </button>
          <button
            type="button"
            className="secondary"
            disabled={loading}
            onClick={() => void run("month", false)}
          >
            이번 달
          </button>
          <button
            type="button"
            className="secondary"
            disabled={loading || !trades.length}
            onClick={() => void run("filtered", false)}
          >
            선택 필터
          </button>
          <button
            type="button"
            className="accent"
            disabled={loading}
            onClick={() => void run(monthFilter === "all" ? "week" : "month", true)}
          >
            AI 코칭
          </button>
        </div>
      </div>

      {loading ? <p className="status">요약 생성 중…</p> : null}
      {error ? <p className="banner">{error}</p> : null}

      {summary ? (
        <div className="period-summary-body review-card">
          <div className="review-top">
            <strong>{summary.rangeLabel}</strong>
            <span>
              {summary.mode} · {summary.tradeCount}건 · 저널{" "}
              {summary.journaledCount}
            </span>
          </div>
          <p>{summary.summary}</p>
          <div className="period-stat-grid">
            <div>
              <span>WR</span>
              <strong>{Math.round(summary.stats.winRate * 100)}%</strong>
            </div>
            <div>
              <span>Net</span>
              <strong className={summary.stats.netPnl >= 0 ? "up" : "down"}>
                {fmtMoney(summary.stats.netPnl)}
              </strong>
            </div>
            <div>
              <span>Long</span>
              <strong>
                {summary.longCount} · {fmtMoney(summary.longPnl)}
              </strong>
            </div>
            <div>
              <span>Short</span>
              <strong>
                {summary.shortCount} · {fmtMoney(summary.shortPnl)}
              </strong>
            </div>
          </div>

          {summary.studyPoints.length ? (
            <div>
              <p className="section-title">공부 포인트</p>
              <ul>
                {summary.studyPoints.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {summary.topBroken.length ? (
            <div>
              <p className="section-title">자주 깨진 규칙</p>
              <ul>
                {summary.topBroken.map((b) => (
                  <li key={b.label}>
                    {b.label} · {b.count}회
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {summary.checklistRates.some((r) => r.n > 0) ? (
            <div className="checklist-rates">
              <p className="section-title">체크리스트 준수율</p>
              <ul>
                {summary.checklistRates
                  .filter((r) => r.n > 0)
                  .map((r) => (
                    <li key={r.key}>
                      {r.label}: {Math.round(r.rate * 100)}% ({r.n})
                    </li>
                  ))}
              </ul>
            </div>
          ) : (
            <p className="muted">
              이 구간 저널이 거의 없어 규칙 준수율은 비어 있습니다. 트레이드마다
              체크리스트를 저장하세요.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}
