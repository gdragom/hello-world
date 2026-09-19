import type { Candle, ClosedTrade } from "./types";

/** Demo closed trades inspired by the user's recent BTCUSDT journal. */
export const DEMO_TRADES: ClosedTrade[] = [
  {
    id: "demo-1",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-09-03T06:47:00Z"),
    closeTime: Date.parse("2026-09-03T14:58:00Z"),
    entryPrice: 77150,
    exitPrice: 78630.7,
    size: 0.02,
    pnl: 28.85,
    fundingFee: -0.12,
    openFee: 0.62,
    closeFee: 0.63,
    source: "demo",
  },
  {
    id: "demo-2",
    symbol: "BTCUSDT",
    side: "short",
    marginMode: "crossed",
    openTime: Date.parse("2026-09-02T12:10:00Z"),
    closeTime: Date.parse("2026-09-02T18:40:00Z"),
    entryPrice: 79210,
    exitPrice: 79956,
    size: 0.04,
    pnl: -29.84,
    fundingFee: -0.2,
    openFee: 1.05,
    closeFee: 1.06,
    source: "demo",
  },
  {
    id: "demo-3",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-09-01T09:20:00Z"),
    closeTime: Date.parse("2026-09-01T16:05:00Z"),
    entryPrice: 76880,
    exitPrice: 77407.5,
    size: 0.04,
    pnl: 21.1,
    fundingFee: -0.08,
    openFee: 1.02,
    closeFee: 1.03,
    source: "demo",
  },
  {
    id: "demo-4",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-08-28T10:00:00Z"),
    closeTime: Date.parse("2026-08-28T15:30:00Z"),
    entryPrice: 75200,
    exitPrice: 76079.25,
    size: 0.04,
    pnl: 35.17,
    fundingFee: -0.15,
    openFee: 1.01,
    closeFee: 1.02,
    source: "demo",
  },
  {
    id: "demo-5",
    symbol: "BTCUSDT",
    side: "short",
    marginMode: "crossed",
    openTime: Date.parse("2026-08-26T11:15:00Z"),
    closeTime: Date.parse("2026-08-26T17:50:00Z"),
    entryPrice: 74550,
    exitPrice: 75454.5,
    size: 0.04,
    pnl: -36.2,
    fundingFee: -0.22,
    openFee: 1.04,
    closeFee: 1.05,
    source: "demo",
  },
  {
    id: "demo-6",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-08-22T08:40:00Z"),
    closeTime: Date.parse("2026-08-22T13:10:00Z"),
    entryPrice: 73100,
    exitPrice: 73912.25,
    size: 0.04,
    pnl: 32.49,
    fundingFee: -0.1,
    openFee: 0.98,
    closeFee: 0.99,
    source: "demo",
  },
  {
    id: "demo-7",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-09-04T07:00:00Z"),
    closeTime: Date.parse("2026-09-04T11:20:00Z"),
    entryPrice: 77820,
    exitPrice: 78712.5,
    size: 0.04,
    pnl: 35.7,
    fundingFee: -0.09,
    openFee: 1.03,
    closeFee: 1.04,
    source: "demo",
  },
  {
    id: "demo-8",
    symbol: "BTCUSDT",
    side: "short",
    marginMode: "crossed",
    openTime: Date.parse("2026-09-04T12:30:00Z"),
    closeTime: Date.parse("2026-09-04T14:10:00Z"),
    entryPrice: 78400,
    exitPrice: 79000,
    size: 0.04,
    pnl: -24.0,
    fundingFee: -0.05,
    openFee: 1.02,
    closeFee: 1.03,
    source: "demo",
  },
  {
    id: "demo-9",
    symbol: "BTCUSDT",
    side: "long",
    marginMode: "crossed",
    openTime: Date.parse("2026-07-18T09:10:00Z"),
    closeTime: Date.parse("2026-07-18T15:40:00Z"),
    entryPrice: 68240,
    exitPrice: 69110,
    size: 0.03,
    pnl: 26.1,
    source: "demo",
  },
  {
    id: "demo-10",
    symbol: "BTCUSDT",
    side: "short",
    marginMode: "crossed",
    openTime: Date.parse("2026-07-09T11:00:00Z"),
    closeTime: Date.parse("2026-07-09T16:20:00Z"),
    entryPrice: 67880,
    exitPrice: 68420,
    size: 0.03,
    pnl: -16.2,
    source: "demo",
  },
];

function seededNoise(seed: number): number {
  const x = Math.sin(seed * 999) * 10000;
  return x - Math.floor(x);
}

/** Synthetic 15m candles covering demo trade windows. */
export function buildDemoCandles(
  aroundTrade?: ClosedTrade,
  bars = 180
): Candle[] {
  const anchor = aroundTrade?.openTime ?? Date.parse("2026-09-03T00:00:00Z");
  const start = anchor - 90 * 15 * 60 * 1000;
  let price = aroundTrade?.entryPrice
    ? aroundTrade.entryPrice * 0.992
    : 77000;

  const out: Candle[] = [];
  for (let i = 0; i < bars; i++) {
    const t = start + i * 15 * 60 * 1000;
    const n = seededNoise(i + price);
    const drift =
      aroundTrade && t >= aroundTrade.openTime && t <= aroundTrade.closeTime
        ? aroundTrade.side === "long"
          ? 18
          : -18
        : (n - 0.5) * 12;
    const open = price;
    const close = Math.max(1000, open + drift + (n - 0.5) * 40);
    const high = Math.max(open, close) + n * 35;
    const low = Math.min(open, close) - (1 - n) * 35;
    out.push({
      time: Math.floor(t / 1000),
      open,
      high,
      low,
      close,
      volume: 50 + n * 120,
    });
    price = close;
  }

  // Force exact entry/exit levels near those timestamps for clearer markers.
  if (aroundTrade) {
    const openIdx = out.findIndex((c) => c.time * 1000 >= aroundTrade.openTime);
    const closeIdx = out.findIndex(
      (c) => c.time * 1000 >= aroundTrade.closeTime
    );
    if (openIdx >= 0) {
      out[openIdx] = {
        ...out[openIdx],
        low: Math.min(out[openIdx].low, aroundTrade.entryPrice),
        high: Math.max(out[openIdx].high, aroundTrade.entryPrice),
        close: aroundTrade.entryPrice,
      };
    }
    if (closeIdx >= 0) {
      out[closeIdx] = {
        ...out[closeIdx],
        low: Math.min(out[closeIdx].low, aroundTrade.exitPrice),
        high: Math.max(out[closeIdx].high, aroundTrade.exitPrice),
        close: aroundTrade.exitPrice,
      };
    }
  }

  return out;
}
