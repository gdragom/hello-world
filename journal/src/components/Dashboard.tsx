"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { StatsBar } from "@/components/StatsBar";
import { TradeChart } from "@/components/TradeChart";
import { TradeDetail } from "@/components/TradeDetail";
import { TradeList } from "@/components/TradeList";
import { MonthlyTrendChart } from "@/components/MonthlyTrendChart";
import { PnLCalendar } from "@/components/PnLCalendar";
import { averageStopRisk, computeStats } from "@/lib/rules";
import {
  dailyTotals,
  filterTrades,
  monthKey,
  monthlySeries,
  recentMonthKeys,
} from "@/lib/pnl";
import type { Candle, ClosedTrade } from "@/lib/types";

export function Dashboard() {
  const [trades, setTrades] = useState<ClosedTrade[]>([]);
  const [source, setSource] = useState("loading");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<ClosedTrade | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [mobileTab, setMobileTab] = useState<
    "trades" | "calendar" | "journal"
  >("trades");
  const [monthFilter, setMonthFilter] = useState<string | "all">("all");
  const [dayFilter, setDayFilter] = useState<string | null>(null);

  const monthOptions = useMemo(() => {
    const keys = new Set(recentMonthKeys(3));
    for (const trade of trades) keys.add(monthKey(trade.closeTime));
    return ["all", ...[...keys].sort().reverse()] as Array<string | "all">;
  }, [trades]);

  const filtered = useMemo(
    () => filterTrades(trades, monthFilter, dayFilter),
    [trades, monthFilter, dayFilter]
  );
  const stats = useMemo(() => computeStats(filtered), [filtered]);
  const avgRisk = useMemo(() => averageStopRisk(filtered), [filtered]);
  const daily = useMemo(() => dailyTotals(trades), [trades]);
  const months = useMemo(() => monthlySeries(trades), [trades]);
  const calendarMonth =
    monthFilter === "all"
      ? recentMonthKeys(1)[0]
      : monthFilter;

  const loadTrades = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/trades?mode=demo");
      const json = await res.json();
      setTrades(json.trades ?? []);
      setSource(json.source ?? "unknown");
      setMessage(json.message ?? json.error ?? "");
      setSelected((prev) => {
        if (prev && json.trades?.some((t: ClosedTrade) => t.id === prev.id)) {
          return prev;
        }
        return json.trades?.[0] ?? null;
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLive = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/trades");
      const json = await res.json();
      setTrades(json.trades ?? []);
      setSource(json.source ?? "unknown");
      setMessage(json.message ?? json.error ?? "");
      setSelected(json.trades?.[0] ?? null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTrades();
  }, [loadTrades]);

  useEffect(() => {
    if (!selected) {
      setCandles([]);
      return;
    }
    let cancelled = false;
    (async () => {
      const qs = new URLSearchParams({
        tradeId: selected.id,
        symbol: selected.symbol,
        openTime: String(selected.openTime),
        closeTime: String(selected.closeTime),
        mode: source === "demo" ? "demo" : "live",
      });
      const res = await fetch(`/api/candles?${qs.toString()}`);
      const json = await res.json();
      if (!cancelled) setCandles(json.candles ?? []);
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, source]);

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="brand">LEDGER</p>
          <h1>BTC ICT Journal</h1>
          <p className="lede">
            Bitget 체결을 차트에 올리고 ICT 규칙으로 복기합니다.
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" onClick={() => void loadTrades()}>
            Demo
          </button>
          <button
            type="button"
            className="accent"
            onClick={() => void loadLive()}
          >
            Sync Bitget
          </button>
        </div>
      </header>

      {message ? <p className="banner">{message}</p> : null}

      <StatsBar stats={stats} source={source} riskDollars={avgRisk} />

      <div className="month-filters">
        {monthOptions.map((key) => (
          <button
            key={key}
            type="button"
            className={monthFilter === key ? "accent" : "secondary"}
            onClick={() => {
              setMonthFilter(key);
              setDayFilter(null);
            }}
          >
            {key === "all" ? "전체" : `${Number(key.slice(5))}월`}
          </button>
        ))}
        {dayFilter ? (
          <button
            type="button"
            className="secondary"
            onClick={() => setDayFilter(null)}
          >
            {dayFilter} 해제
          </button>
        ) : null}
      </div>

      <nav className="mobile-tabs" aria-label="모바일 화면">
        <button
          type="button"
          className={mobileTab === "trades" ? "active" : ""}
          onClick={() => setMobileTab("trades")}
        >
          체결
        </button>
        <button
          type="button"
          className={mobileTab === "calendar" ? "active" : ""}
          onClick={() => setMobileTab("calendar")}
        >
          캘린더
        </button>
        <button
          type="button"
          className={mobileTab === "journal" ? "active" : ""}
          onClick={() => setMobileTab("journal")}
        >
          복기
        </button>
      </nav>

      <div
        className={`analytics-row ${mobileTab === "calendar" ? "is-visible" : ""}`}
      >
        <PnLCalendar
          month={calendarMonth}
          daily={daily}
          selectedDay={dayFilter}
          onSelectDay={(day) => {
            setDayFilter(day);
            if (day) {
              setMonthFilter(day.slice(0, 7));
              const first = filterTrades(trades, day.slice(0, 7), day)[0];
              if (first) setSelected(first);
            }
          }}
        />
        <MonthlyTrendChart series={months} />
      </div>

      <div className={`workspace show-${mobileTab}`}>
        <aside className="sidebar">
          <div className="sidebar-head">
            <h3>Closed trades</h3>
            <span>{loading ? "…" : `${filtered.length}`}</span>
          </div>
          <TradeList
            trades={filtered}
            selectedId={selected?.id ?? null}
            onSelect={(trade) => {
              setSelected(trade);
              setMobileTab("journal");
            }}
          />
        </aside>

        <main className="main-pane">
          <TradeChart candles={candles} trade={selected} />
          {selected ? (
            <TradeDetail trade={selected} />
          ) : (
            <div className="empty">트레이드를 선택하세요.</div>
          )}
        </main>
      </div>
    </div>
  );
}
