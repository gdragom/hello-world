"use client";

import { useEffect, useState } from "react";
import { calendarCells, monthLabel } from "@/lib/pnl";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

type Props = {
  month: string;
  daily: Record<string, number>;
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
};

export function PnLCalendar({
  month,
  daily,
  selectedDay,
  onSelectDay,
}: Props) {
  const [monthNote, setMonthNote] = useState("");
  const [dayNote, setDayNote] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/periods?id=month:${month}`);
      const json = await res.json();
      if (!cancelled) setMonthNote(json.note?.note ?? "");
    })();
    return () => {
      cancelled = true;
    };
  }, [month]);

  useEffect(() => {
    if (!selectedDay) {
      setDayNote("");
      return;
    }
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/periods?id=day:${selectedDay}`);
      const json = await res.json();
      if (!cancelled) setDayNote(json.note?.note ?? "");
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDay]);

  async function save(id: string, note: string) {
    setStatus("저장 중…");
    try {
      await fetch("/api/periods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, note }),
      });
      try {
        localStorage.setItem(`ledger-period:${id}`, note);
      } catch {
        /* ignore */
      }
      setStatus("기록 저장됨");
    } catch {
      setStatus("저장 실패");
    }
  }

  const cells = calendarCells(month);
  const monthPnl = Object.entries(daily)
    .filter(([key]) => key.startsWith(month))
    .reduce((sum, [, pnl]) => sum + pnl, 0);

  return (
    <section className="calendar-card">
      <header className="calendar-head">
        <div>
          <p className="eyebrow">Calendar</p>
          <h3>{monthLabel(month)} 일별 손익</h3>
        </div>
        <strong className={monthPnl >= 0 ? "up" : "down"}>
          {monthPnl >= 0 ? "+" : ""}${monthPnl.toFixed(2)}
        </strong>
      </header>

      <div className="cal-weekdays">
        {WEEKDAYS.map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className="cal-grid">
        {cells.map((cell, i) => {
          if (!cell.date) return <div key={`e-${i}`} className="cal-cell empty" />;
          const pnl = daily[cell.date];
          const tone =
            pnl === undefined ? "" : pnl >= 0 ? "plus" : "minus";
          return (
            <button
              key={cell.date}
              type="button"
              className={`cal-cell ${tone} ${selectedDay === cell.date ? "active" : ""}`}
              onClick={() =>
                onSelectDay(selectedDay === cell.date ? null : cell.date)
              }
            >
              <span className="cal-day">{cell.day}</span>
              {pnl !== undefined ? (
                <span className="cal-pnl">
                  {pnl >= 0 ? "+" : ""}
                  {pnl.toFixed(0)}
                </span>
              ) : (
                <span className="cal-pnl muted">—</span>
              )}
            </button>
          );
        })}
      </div>

      <label className="field">
        <span>{monthLabel(month)} 메모</span>
        <textarea
          rows={2}
          value={monthNote}
          onChange={(e) => setMonthNote(e.target.value)}
          placeholder="이번 달 한 줄 복기"
        />
      </label>
      <button
        type="button"
        className="secondary"
        onClick={() => void save(`month:${month}`, monthNote)}
      >
        월 기록 저장
      </button>

      {selectedDay ? (
        <>
          <label className="field" style={{ marginTop: 12 }}>
            <span>{selectedDay} 메모</span>
            <textarea
              rows={2}
              value={dayNote}
              onChange={(e) => setDayNote(e.target.value)}
              placeholder="오늘 Daily Bias / 결과"
            />
          </label>
          <button
            type="button"
            className="secondary"
            onClick={() => void save(`day:${selectedDay}`, dayNote)}
          >
            일 기록 저장
          </button>
        </>
      ) : null}
      {status ? <p className="status">{status}</p> : null}
    </section>
  );
}
