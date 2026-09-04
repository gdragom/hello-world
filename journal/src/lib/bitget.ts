import { createHmac } from "crypto";
import type { Candle, ClosedTrade } from "./types";

const BITGET_BASE = process.env.BITGET_BASE_URL ?? "https://api.bitget.com";

export function hasBitgetCredentials(): boolean {
  return Boolean(
    process.env.BITGET_API_KEY &&
      process.env.BITGET_API_SECRET &&
      process.env.BITGET_API_PASSPHRASE
  );
}

function sign(
  timestamp: string,
  method: string,
  requestPath: string,
  body: string,
  secret: string
): string {
  const prehash = `${timestamp}${method.toUpperCase()}${requestPath}${body}`;
  return createHmac("sha256", secret).update(prehash).digest("base64");
}

async function bitgetFetch<T>(
  method: "GET" | "POST",
  pathWithQuery: string,
  bodyObj?: Record<string, unknown>
): Promise<T> {
  const apiKey = process.env.BITGET_API_KEY;
  const secret = process.env.BITGET_API_SECRET;
  const passphrase = process.env.BITGET_API_PASSPHRASE;

  if (!apiKey || !secret || !passphrase) {
    throw new Error("Bitget API credentials are not configured");
  }

  const timestamp = Date.now().toString();
  const body = bodyObj ? JSON.stringify(bodyObj) : "";
  const signature = sign(timestamp, method, pathWithQuery, body, secret);

  const res = await fetch(`${BITGET_BASE}${pathWithQuery}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "ACCESS-KEY": apiKey,
      "ACCESS-SIGN": signature,
      "ACCESS-TIMESTAMP": timestamp,
      "ACCESS-PASSPHRASE": passphrase,
      locale: "en-US",
    },
    body: method === "GET" ? undefined : body,
    cache: "no-store",
  });

  const json = (await res.json()) as {
    code: string;
    msg: string;
    data: T;
  };

  if (!res.ok || json.code !== "00000") {
    throw new Error(json.msg || `Bitget error (${res.status})`);
  }

  return json.data;
}

type BitgetHistoryPosition = {
  positionId?: string;
  symbol: string;
  holdSide: string;
  marginMode?: string;
  openAvgPrice?: string;
  closeAvgPrice?: string;
  openPriceAvg?: string;
  closePriceAvg?: string;
  ctime?: string;
  utime?: string;
  openTime?: string;
  closeTime?: string;
  achivedProfit?: string;
  realizedPnl?: string;
  pnl?: string;
  openFee?: string;
  closeFee?: string;
  totalFee?: string;
  openTotalPos?: string;
  closeTotalPos?: string;
  size?: string;
};

function num(v: string | undefined, fallback = 0): number {
  if (v === undefined || v === null || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function mapHistoryPosition(row: BitgetHistoryPosition): ClosedTrade {
  const side = row.holdSide?.toLowerCase().includes("short") ? "short" : "long";
  const entry = num(row.openAvgPrice ?? row.openPriceAvg);
  const exit = num(row.closeAvgPrice ?? row.closePriceAvg);
  const size = num(row.closeTotalPos ?? row.openTotalPos ?? row.size);
  const pnl = num(row.achivedProfit ?? row.realizedPnl ?? row.pnl);
  const openTime = num(row.ctime ?? row.openTime, Date.now());
  const closeTime = num(row.utime ?? row.closeTime, openTime);
  const id =
    row.positionId ||
    `${row.symbol}-${side}-${openTime}-${closeTime}-${entry}-${exit}`;

  return {
    id,
    symbol: row.symbol?.replace("_UMCBL", "") || "BTCUSDT",
    side,
    marginMode: row.marginMode || "crossed",
    openTime,
    closeTime,
    entryPrice: entry,
    exitPrice: exit,
    size,
    pnl,
    openFee: num(row.openFee),
    closeFee: num(row.closeFee),
    source: "bitget",
  };
}

export async function fetchBitgetClosedPositions(options?: {
  symbol?: string;
  limit?: number;
}): Promise<ClosedTrade[]> {
  const symbol = options?.symbol ?? "BTCUSDT";
  const limit = options?.limit ?? 50;
  const qs = new URLSearchParams({
    productType: "USDT-FUTURES",
    symbol,
    limit: String(limit),
  });

  const data = await bitgetFetch<BitgetHistoryPosition[] | { list?: BitgetHistoryPosition[] }>(
    "GET",
    `/api/v2/mix/position/history-position?${qs.toString()}`
  );

  const rows = Array.isArray(data) ? data : data.list ?? [];
  return rows.map(mapHistoryPosition).sort((a, b) => b.closeTime - a.closeTime);
}

type BitgetCandle = string[];

export async function fetchBitgetCandles(options: {
  symbol?: string;
  granularity?: string;
  startTime?: number;
  endTime?: number;
  limit?: number;
}): Promise<Candle[]> {
  const symbol = options.symbol ?? "BTCUSDT";
  const granularity = options.granularity ?? "15m";
  const limit = options.limit ?? 300;
  const qs = new URLSearchParams({
    symbol,
    productType: "USDT-FUTURES",
    granularity,
    limit: String(limit),
  });
  if (options.startTime) qs.set("startTime", String(options.startTime));
  if (options.endTime) qs.set("endTime", String(options.endTime));

  // Public market endpoint — still works without auth, but use same fetch helper path via unsigned GET
  const url = `${BITGET_BASE}/api/v2/mix/market/candles?${qs.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  const json = (await res.json()) as {
    code: string;
    msg: string;
    data: BitgetCandle[];
  };
  if (!res.ok || json.code !== "00000") {
    throw new Error(json.msg || "Failed to fetch candles");
  }

  // Bitget returns [ts, open, high, low, close, volume, quoteVolume] newest first often
  const candles = (json.data || []).map((row) => ({
    time: Math.floor(Number(row[0]) / 1000),
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[5] ?? 0),
  }));

  return candles.sort((a, b) => a.time - b.time);
}
