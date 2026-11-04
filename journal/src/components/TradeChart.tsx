"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type CandlestickData,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { Candle, ClosedTrade } from "@/lib/types";

type Props = {
  candles: Candle[];
  trade: ClosedTrade | null;
};

function nearestTime(candles: Candle[], ms: number): Time | null {
  if (!candles.length) return null;
  const target = Math.floor(ms / 1000);
  let best = candles[0];
  let bestDist = Math.abs(best.time - target);
  for (const c of candles) {
    const d = Math.abs(c.time - target);
    if (d < bestDist) {
      best = c;
      bestDist = d;
    }
  }
  return best.time as Time;
}

export function TradeChart({ candles, trade }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const markersApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#12110f" },
        textColor: "#c8c0b4",
        fontFamily: "IBM Plex Mono, ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: "rgba(200,192,180,0.06)" },
        horzLines: { color: "rgba(200,192,180,0.06)" },
      },
      rightPriceScale: { borderColor: "rgba(200,192,180,0.15)" },
      timeScale: { borderColor: "rgba(200,192,180,0.15)", timeVisible: true },
      crosshair: {
        vertLine: { color: "rgba(232,168,56,0.35)" },
        horzLine: { color: "rgba(232,168,56,0.35)" },
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#3dba7e",
      downColor: "#d4543c",
      borderVisible: false,
      wickUpColor: "#3dba7e",
      wickDownColor: "#d4543c",
    });

    chartRef.current = chart;
    seriesRef.current = series;
    markersApiRef.current = createSeriesMarkers(series, []);

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      markersApiRef.current = null;
      linesRef.current = [];
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;

    const data: CandlestickData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    series.setData(data);

    for (const line of linesRef.current) {
      series.removePriceLine(line);
    }
    linesRef.current = [];

    if (trade && candles.length) {
      const entryTime = nearestTime(candles, trade.openTime);
      const exitTime = nearestTime(candles, trade.closeTime);
      const win = trade.pnl >= 0;

      const markers: SeriesMarker<Time>[] = [];
      if (entryTime) {
        markers.push({
          time: entryTime,
          position: trade.side === "long" ? "belowBar" : "aboveBar",
          color: "#e8a838",
          shape: trade.side === "long" ? "arrowUp" : "arrowDown",
          text: `IN ${trade.entryPrice.toFixed(1)}`,
        });
      }
      if (exitTime) {
        markers.push({
          time: exitTime,
          position: trade.side === "long" ? "aboveBar" : "belowBar",
          color: win ? "#3dba7e" : "#d4543c",
          shape: "circle",
          text: `OUT ${trade.exitPrice.toFixed(1)}`,
        });
      }
      markersApiRef.current?.setMarkers(markers);

      linesRef.current.push(
        series.createPriceLine({
          price: trade.entryPrice,
          color: "rgba(232,168,56,0.7)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "Entry",
        }),
        series.createPriceLine({
          price: trade.exitPrice,
          color: win ? "rgba(61,186,126,0.7)" : "rgba(212,84,60,0.7)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "Exit",
        })
      );
    } else {
      markersApiRef.current?.setMarkers([]);
    }

    chart.timeScale().fitContent();
  }, [candles, trade]);

  return (
    <div className="chart-shell">
      <div ref={containerRef} className="chart-canvas" />
    </div>
  );
}
