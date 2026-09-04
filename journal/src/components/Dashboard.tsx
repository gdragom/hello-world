"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { StatsBar } from "@/components/StatsBar";
import { TradeChart } from "@/components/TradeChart";
import { TradeDetail } from "@/components/TradeDetail";
import { TradeList } from "@/components/TradeList";
import { computeStats } from "@/lib/rules";
import type { Candle, ClosedTrade } from "@/lib/types";

export function Dashboard() {
  const [trades, setTrades] = useState<ClosedTrade[]>([]);
  const [source, setSource] = useState("loading");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<ClosedTrade | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [riskDollars, setRiskDollars] = useState(25);
  const [loading, setLoading] = useState(true);

  const stats = useMemo(() => computeStats(trades), [trades]);

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
            Bitget 체결을 불러오고, 진입·청산을 차트에 표시한 뒤, 규칙 준수
            여부를 AI/룰엔진과 함께 복기합니다. Cursor에서는 공식 Bitget MCP도
            같이 쓸 수 있습니다.
          </p>
        </div>
        <div className="hero-actions">
          <label className="risk-input">
            1R ($)
            <input
              type="number"
              min={1}
              step={1}
              value={riskDollars}
              onChange={(e) => setRiskDollars(Number(e.target.value) || 25)}
            />
          </label>
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

      <StatsBar stats={stats} source={source} riskDollars={riskDollars} />

      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-head">
            <h3>Closed trades</h3>
            <span>{loading ? "…" : `${trades.length}`}</span>
          </div>
          <TradeList
            trades={trades}
            selectedId={selected?.id ?? null}
            riskDollars={riskDollars}
            onSelect={setSelected}
          />
        </aside>

        <main className="main-pane">
          <TradeChart candles={candles} trade={selected} />
          {selected ? (
            <TradeDetail trade={selected} riskDollars={riskDollars} />
          ) : (
            <div className="empty">트레이드를 선택하세요.</div>
          )}
        </main>
      </div>
    </div>
  );
}
