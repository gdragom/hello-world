import { BitgetRestClient, loadConfig } from "@bitget-ai/bitget-agent-sdk";
import type { Candle, ClosedTrade } from "./types";

function firstEnv(...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = process.env[key];
    if (value && value.trim()) return value.trim();
  }
  return undefined;
}

/** Align with official Bitget MCP env names; keep legacy aliases. */
export function getBitgetCredentials() {
  return {
    apiKey: firstEnv("BITGET_API_KEY"),
    secretKey: firstEnv("BITGET_SECRET_KEY", "BITGET_API_SECRET"),
    passphrase: firstEnv("BITGET_PASSPHRASE", "BITGET_API_PASSPHRASE"),
  };
}

export function hasBitgetCredentials(): boolean {
  const { apiKey, secretKey, passphrase } = getBitgetCredentials();
  return Boolean(apiKey && secretKey && passphrase);
}

function createClient(): BitgetRestClient {
  const { apiKey, secretKey, passphrase } = getBitgetCredentials();
  const config = loadConfig({
    modules: "account,trade,market",
    readOnly: true,
    apiKey,
    secretKey,
    passphrase,
  });
  return new BitgetRestClient(config);
}

type HistoryRow = Record<string, unknown>;

function num(v: unknown, fallback = 0): number {
  if (v === undefined || v === null || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function mapHistoryPosition(row: HistoryRow): ClosedTrade {
  const holdSide = str(row.holdSide || row.posSide || row.side).toLowerCase();
  const side =
    holdSide.includes("short") || holdSide.includes("sell") ? "short" : "long";
  const entry = num(row.openAvgPrice ?? row.openPriceAvg ?? row.avgOpenPrice);
  const exit = num(row.closeAvgPrice ?? row.closePriceAvg ?? row.avgClosePrice);
  const size = num(
    row.closeTotalPos ?? row.openTotalPos ?? row.size ?? row.qty ?? row.closedSize
  );
  const pnl = num(
    row.achivedProfit ??
      row.achievedProfit ??
      row.realizedPnl ??
      row.pnl ??
      row.netProfit
  );
  const openTime = num(row.ctime ?? row.openTime ?? row.createdTime, Date.now());
  const closeTime = num(
    row.utime ?? row.closeTime ?? row.updatedTime,
    openTime
  );
  const symbol = str(row.symbol || "BTCUSDT").replace(/_UMCBL$/i, "");
  const id =
    str(row.positionId || row.posId) ||
    `${symbol}-${side}-${openTime}-${closeTime}-${entry}-${exit}`;

  return {
    id,
    symbol,
    side,
    marginMode: str(row.marginMode || row.marginModeType || "crossed"),
    openTime,
    closeTime,
    entryPrice: entry,
    exitPrice: exit,
    size,
    pnl,
    openFee: num(row.openFee),
    closeFee: num(row.closeFee),
    fundingFee: num(row.fundingFee ?? row.totalFunding),
    source: "bitget",
  };
}

function unwrapList(data: unknown): HistoryRow[] {
  if (Array.isArray(data)) return data as HistoryRow[];
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.list)) return obj.list as HistoryRow[];
    if (Array.isArray(obj.data)) return obj.data as HistoryRow[];
  }
  return [];
}

function normalizeInterval(granularity: string): string {
  const map: Record<string, string> = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "1H": "1H",
    "4h": "4H",
    "4H": "4H",
    "1d": "1D",
    "1D": "1D",
  };
  return map[granularity] ?? "15m";
}

export async function fetchBitgetClosedPositions(options?: {
  symbol?: string;
  limit?: number;
}): Promise<ClosedTrade[]> {
  if (!hasBitgetCredentials()) {
    throw new Error(
      "Bitget credentials missing. Set BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE (same as Bitget MCP)."
    );
  }

  const client = createClient();
  const result = await client.callOperation<unknown>("getPositionsHistory", {
    category: "USDT-FUTURES",
    symbol: options?.symbol ?? "BTCUSDT",
    limit: String(options?.limit ?? 50),
  });

  return unwrapList(result.data)
    .map(mapHistoryPosition)
    .sort((a, b) => b.closeTime - a.closeTime);
}

export async function fetchBitgetCandles(options: {
  symbol?: string;
  granularity?: string;
  startTime?: number;
  endTime?: number;
  limit?: number;
}): Promise<Candle[]> {
  const client = createClient();
  const args: Record<string, unknown> = {
    category: "USDT-FUTURES",
    symbol: options.symbol ?? "BTCUSDT",
    interval: normalizeInterval(options.granularity ?? "15m"),
    limit: String(options.limit ?? 300),
  };
  if (options.startTime) args.startTime = String(options.startTime);
  if (options.endTime) args.endTime = String(options.endTime);

  const preferHistory = Boolean(options.startTime || options.endTime);
  let data: unknown;
  try {
    const result = await client.callOperation<unknown>(
      preferHistory ? "getKlineCandlestickHistory" : "getKlineCandlestick",
      args
    );
    data = result.data;
  } catch (error) {
    if (!preferHistory) throw error;
    const result = await client.callOperation<unknown>(
      "getKlineCandlestick",
      args
    );
    data = result.data;
  }

  const rows = unwrapList(data);
  const candles = rows.map((row) => {
    if (Array.isArray(row)) {
      const arr = row as unknown[];
      return {
        time: Math.floor(num(arr[0]) / 1000),
        open: num(arr[1]),
        high: num(arr[2]),
        low: num(arr[3]),
        close: num(arr[4]),
        volume: num(arr[5]),
      };
    }
    const obj = row as HistoryRow;
    const ts = num(obj.ts ?? obj.timestamp ?? obj.time);
    return {
      time: Math.floor((ts > 1e12 ? ts : ts * 1000) / 1000),
      open: num(obj.open),
      high: num(obj.high),
      low: num(obj.low),
      close: num(obj.close),
      volume: num(obj.volume ?? obj.baseVolume),
    };
  });

  return candles
    .filter((c) => c.time > 0)
    .sort((a, b) => a.time - b.time);
}
