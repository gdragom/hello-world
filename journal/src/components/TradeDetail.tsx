"use client";

import { useEffect, useMemo, useState } from "react";
import { RULE_LABELS } from "@/lib/rules";
import type {
  ClosedTrade,
  JournalEntry,
  ReviewResult,
  RuleChecklistState,
} from "@/lib/types";
import { DEFAULT_CHECKLIST } from "@/lib/rules";

type Props = {
  trade: ClosedTrade;
  riskDollars: number;
};

const verdictLabel: Record<ReviewResult["verdict"], string> = {
  process_win: "프로세스 승 (잘한 손실/수익)",
  process_loss: "프로세스 패",
  mixed: "혼합",
  unclear: "판단 보류",
};

export function TradeDetail({ trade, riskDollars }: Props) {
  const [journal, setJournal] = useState<JournalEntry>({
    tradeId: trade.id,
    entryReason: "",
    exitReason: "",
    checklist: { ...DEFAULT_CHECKLIST },
    tags: [],
    updatedAt: 0,
  });
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [jRes, rRes] = await Promise.all([
        fetch(`/api/journal?tradeId=${encodeURIComponent(trade.id)}`),
        fetch(`/api/review?tradeId=${encodeURIComponent(trade.id)}`),
      ]);
      const jJson = await jRes.json();
      const rJson = await rRes.json();
      if (cancelled) return;
      setJournal(jJson.journal);
      setReview(rJson.review);
      setStatus("");
    })();
    return () => {
      cancelled = true;
    };
  }, [trade.id]);

  const checklistEntries = useMemo(
    () =>
      (Object.keys(RULE_LABELS) as (keyof RuleChecklistState)[]).map((key) => ({
        key,
        label: RULE_LABELS[key],
        value: journal.checklist[key],
      })),
    [journal.checklist]
  );

  async function saveJournal() {
    setSaving(true);
    setStatus("저장 중…");
    try {
      const res = await fetch("/api/journal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(journal),
      });
      const json = await res.json();
      setJournal(json.journal);
      setStatus("저장됨");
    } catch {
      setStatus("저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function runReview(useAi: boolean) {
    setReviewing(true);
    setStatus(useAi ? "AI 복기 생성 중…" : "규칙 복기 생성 중…");
    try {
      await saveJournal();
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tradeId: trade.id,
          trade,
          riskDollars,
          useAi,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "review failed");
      setReview(json.review);
      setStatus(useAi ? "AI 복기 완료" : "규칙 복기 완료");
    } catch {
      setStatus("복기 실패");
    } finally {
      setReviewing(false);
    }
  }

  return (
    <div className="detail-panel">
      <header className="detail-header">
        <div>
          <p className="eyebrow">Trade journal</p>
          <h2>
            {trade.symbol} · {trade.side.toUpperCase()}
          </h2>
        </div>
        <div className={`pnl-lg ${trade.pnl >= 0 ? "up" : "down"}`}>
          {trade.pnl >= 0 ? "+" : ""}
          ${trade.pnl.toFixed(2)}
        </div>
      </header>

      <div className="meta-grid">
        <div>
          <span>Entry</span>
          <strong>{trade.entryPrice.toFixed(2)}</strong>
        </div>
        <div>
          <span>Exit</span>
          <strong>{trade.exitPrice.toFixed(2)}</strong>
        </div>
        <div>
          <span>Size</span>
          <strong>{trade.size} BTC</strong>
        </div>
        <div>
          <span>Risk 1R</span>
          <strong>${riskDollars}</strong>
        </div>
      </div>

      <label className="field">
        <span>진입 근거 (MSS / Fib / CISD)</span>
        <textarea
          value={journal.entryReason}
          onChange={(e) =>
            setJournal((j) => ({ ...j, entryReason: e.target.value }))
          }
          placeholder="예: 1H bullish MSS 이후 0.5 discount에서 15m CISD 롱. 2R 타겟은 전고점."
          rows={4}
        />
      </label>

      <label className="field">
        <span>청산 / 반익절 메모</span>
        <textarea
          value={journal.exitReason}
          onChange={(e) =>
            setJournal((j) => ({ ...j, exitReason: e.target.value }))
          }
          placeholder="예: 2R에서 50% 익절, 나머지 BE 후 구조 이탈로 종료."
          rows={3}
        />
      </label>

      <div className="checklist">
        <p className="section-title">규칙 체크리스트</p>
        {checklistEntries.map((item) => (
          <label key={item.key} className="check-row">
            <input
              type="checkbox"
              checked={item.value}
              onChange={(e) =>
                setJournal((j) => ({
                  ...j,
                  checklist: {
                    ...j.checklist,
                    [item.key]: e.target.checked,
                  },
                }))
              }
            />
            <span>{item.label}</span>
          </label>
        ))}
      </div>

      <div className="actions">
        <button type="button" onClick={saveJournal} disabled={saving}>
          저장
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => runReview(false)}
          disabled={reviewing}
        >
          규칙 복기
        </button>
        <button
          type="button"
          className="accent"
          onClick={() => runReview(true)}
          disabled={reviewing}
        >
          AI 복기
        </button>
      </div>
      {status ? <p className="status">{status}</p> : null}

      {review ? (
        <section className={`review-card verdict-${review.verdict}`}>
          <div className="review-top">
            <strong>{verdictLabel[review.verdict]}</strong>
            <span>
              {review.estimatedR !== null
                ? `${review.estimatedR.toFixed(2)}R`
                : "R n/a"}{" "}
              · {review.mode}
            </span>
          </div>
          <p>{review.summary}</p>
          <p className="muted">{review.marketNote}</p>
          {review.broken.length ? (
            <div>
              <span className="mini-label">지키지 않음</span>
              <ul>
                {review.broken.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {review.kept.length ? (
            <div>
              <span className="mini-label">지킴</span>
              <ul>
                {review.kept.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {review.suggestions.length ? (
            <div>
              <span className="mini-label">다음 액션</span>
              <ul>
                {review.suggestions.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
