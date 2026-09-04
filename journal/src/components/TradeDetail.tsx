"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { compressImage } from "@/lib/image";
import { RULE_LABELS } from "@/lib/rules";
import type {
  ClosedTrade,
  JournalEntry,
  JournalScreenshot,
  ReviewResult,
  RuleChecklistState,
} from "@/lib/types";
import {
  DEFAULT_CHECKLIST,
  estimateR,
  normalizeChecklist,
  stopLossUsd,
  stopRange,
} from "@/lib/rules";

type Props = {
  trade: ClosedTrade;
};

const verdictLabel: Record<ReviewResult["verdict"], string> = {
  process_win: "프로세스 승 (잘한 손실/수익)",
  process_loss: "프로세스 패",
  mixed: "혼합",
  unclear: "판단 보류",
};

export function TradeDetail({ trade }: Props) {
  const risk = stopLossUsd(trade);
  const range = stopRange(trade);
  const rMultiple = estimateR(trade);
  const [journal, setJournal] = useState<JournalEntry>({
    tradeId: trade.id,
    entryReason: "",
    exitReason: "",
    checklist: { ...DEFAULT_CHECKLIST },
    tags: [],
    screenshots: [],
    updatedAt: 0,
  });
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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
      const remote = jJson.journal as JournalEntry;
      let next = remote;
      try {
        const raw = localStorage.getItem(`ledger-journal:${trade.id}`);
        if (raw) {
          const local = JSON.parse(raw) as JournalEntry;
          if ((local.updatedAt ?? 0) >= (remote.updatedAt ?? 0)) next = local;
        }
      } catch {
        /* ignore */
      }
      setJournal({
        ...next,
        checklist: normalizeChecklist(next.checklist),
        screenshots: next.screenshots ?? [],
      });
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

  async function addFiles(files: FileList | File[]) {
    const list = [...files].filter((f) => f.type.startsWith("image/"));
    if (!list.length) return;
    setStatus("차트 첨부 중…");
    try {
      const added: JournalScreenshot[] = [];
      for (const file of list.slice(0, 4)) {
        const dataUrl = await compressImage(file);
        added.push({
          id: `${Date.now()}-${file.name}`,
          name: file.name,
          dataUrl,
          createdAt: Date.now(),
        });
      }
      setJournal((j) => ({
        ...j,
        screenshots: [...(j.screenshots ?? []), ...added].slice(0, 6),
      }));
      setStatus("차트 첨부됨 · 저장을 누르세요");
    } catch {
      setStatus("첨부 실패");
    }
  }

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
      try {
        localStorage.setItem(
          `ledger-journal:${trade.id}`,
          JSON.stringify(json.journal)
        );
      } catch {
        /* ignore */
      }
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
          useAi,
          journal,
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
          <span>손절 범위</span>
          <strong>{range.toFixed(1)}</strong>
        </div>
        <div>
          <span>1R (SL)</span>
          <strong>{risk !== null ? `$${risk.toFixed(2)}` : "—"}</strong>
        </div>
        <div>
          <span>실현 R</span>
          <strong>{rMultiple !== null ? `${rMultiple.toFixed(2)}R` : "—"}</strong>
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

      <div className="attach-block">
        <div className="attach-row">
          <p className="section-title">TradingView 차트</p>
          <button
            type="button"
            className="secondary"
            onClick={() => fileRef.current?.click()}
          >
            첨부
          </button>
        </div>
        <p className="attach-hint">
          스크린샷을 고르거나, 이 칸에 붙여넣기(Ctrl+V) 하세요.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) void addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div
          className="attach-drop"
          tabIndex={0}
          onPaste={(e) => {
            const files = [...e.clipboardData.files];
            if (files.length) {
              e.preventDefault();
              void addFiles(files);
            }
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void addFiles(e.dataTransfer.files);
          }}
        >
          {(journal.screenshots ?? []).length ? (
            <div className="shot-grid">
              {journal.screenshots.map((shot) => (
                <figure key={shot.id} className="shot-card">
                  <button
                    type="button"
                    className="shot-open"
                    onClick={() => setPreview(shot.dataUrl)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={shot.dataUrl} alt={shot.name} />
                  </button>
                  <button
                    type="button"
                    className="shot-remove"
                    onClick={() =>
                      setJournal((j) => ({
                        ...j,
                        screenshots: j.screenshots.filter((s) => s.id !== shot.id),
                      }))
                    }
                  >
                    삭제
                  </button>
                </figure>
              ))}
            </div>
          ) : (
            <span>아직 첨부한 차트가 없습니다.</span>
          )}
        </div>
      </div>

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

      {preview ? (
        <button
          type="button"
          className="lightbox"
          onClick={() => setPreview(null)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={preview} alt="TradingView 차트" />
        </button>
      ) : null}
    </div>
  );
}
