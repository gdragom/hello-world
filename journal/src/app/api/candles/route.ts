import { NextResponse } from "next/server";
import { fetchBitgetCandles, hasBitgetCredentials } from "@/lib/bitget";
import { DEMO_TRADES, buildDemoCandles } from "@/lib/demo-data";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const tradeId = searchParams.get("tradeId");
  const symbol = searchParams.get("symbol") ?? "BTCUSDT";
  const granularity = searchParams.get("granularity") ?? "15m";
  const forceDemo =
    searchParams.get("mode") === "demo" ||
    process.env.JOURNAL_FORCE_DEMO === "1";

  const trade = DEMO_TRADES.find((t) => t.id === tradeId);

  try {
    if (!forceDemo && hasBitgetCredentials()) {
      const open = Number(searchParams.get("openTime") ?? 0);
      const close = Number(searchParams.get("closeTime") ?? Date.now());
      const pad = 90 * 15 * 60 * 1000;
      const candles = await fetchBitgetCandles({
        symbol,
        granularity,
        startTime: open ? open - pad : undefined,
        endTime: close ? close + pad : undefined,
        limit: 300,
      });
      return NextResponse.json({ source: "bitget", candles });
    }

    return NextResponse.json({
      source: "demo",
      candles: buildDemoCandles(trade),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({
      source: "demo",
      candles: buildDemoCandles(trade),
      error: message,
    });
  }
}
