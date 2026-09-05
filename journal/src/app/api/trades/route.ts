import { NextResponse } from "next/server";
import { fetchBitgetClosedPositions, hasBitgetCredentials } from "@/lib/bitget";
import { DEMO_TRADES } from "@/lib/demo-data";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const mode = searchParams.get("mode");
  const forceDemo = mode === "demo" || process.env.JOURNAL_FORCE_DEMO === "1";

  try {
    if (!forceDemo && hasBitgetCredentials()) {
      const trades = await fetchBitgetClosedPositions({
        symbol: searchParams.get("symbol") ?? "BTCUSDT",
        limit: Number(searchParams.get("limit") ?? 50),
      });
      return NextResponse.json({
        source: "bitget",
        trades,
      });
    }

    return NextResponse.json({
      source: "demo",
      trades: DEMO_TRADES,
      message:
        "Bitget API 키가 없어 데모 데이터를 표시합니다. .env.local에 BITGET_API_KEY/SECRET/PASSPHRASE를 넣으면 실거래가 동기화됩니다.",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      {
        source: "demo",
        trades: DEMO_TRADES,
        error: message,
        message: "Bitget 동기화 실패 → 데모 데이터로 폴백했습니다.",
      },
      { status: 200 }
    );
  }
}
