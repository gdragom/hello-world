"use client";

import { useCallback, useEffect, useState } from "react";
import type { SetupAlert } from "@/lib/types";

const stageLabel: Record<SetupAlert["stage"], string> = {
  SETUP_ARMED: "1H 셋업",
  ENTRY_READY: "5m 진입",
  INVALID: "만료",
};

function fmtTime(ms: number) {
  return new Date(ms).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AlertFeed() {
  const [alerts, setAlerts] = useState<SetupAlert[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/alerts?limit=20");
      const json = await res.json();
      setAlerts(json.alerts ?? []);
      setError("");
    } catch {
      setError("알림을 불러오지 못했습니다");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <section className="alert-feed">
      <header className="calendar-head">
        <div>
          <p className="eyebrow">TradingView</p>
          <h3>셋업 알림</h3>
        </div>
        <button type="button" className="secondary" onClick={() => void load()}>
          새로고침
        </button>
      </header>
      {error ? <p className="status">{error}</p> : null}
      {!alerts.length ? (
        <p className="empty">
          TradingView 웹훅이 아직 없습니다. 1H SETUP_ARMED / 5m ENTRY_READY
          알림을 연결하세요.
        </p>
      ) : (
        <ul className="alert-list">
          {alerts.map((a) => (
            <li key={a.id} className={`alert-row stage-${a.stage}`}>
              <div className="alert-top">
                <span className="alert-stage">{stageLabel[a.stage]}</span>
                <span className="alert-time">{fmtTime(a.createdAt)}</span>
              </div>
              <strong>
                {a.symbol} · {a.side} · {a.timeframe}
                {a.price != null ? ` · ${a.price}` : ""}
              </strong>
              {a.message ? <p>{a.message}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
