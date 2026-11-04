import { NextResponse } from "next/server";
import { z } from "zod";
import { DEMO_TRADES } from "@/lib/demo-data";
import { fetchBitgetClosedPositions, hasBitgetCredentials } from "@/lib/bitget";
import { listJournals } from "@/lib/journal-store";
import {
  buildPeriodSummaryWithOptionalAi,
  filterTradesByRange,
  resolvePeriodRange,
} from "@/lib/period-summary";
import type { ClosedTrade } from "@/lib/types";

export const dynamic = "force-dynamic";

const bodySchema = z.object({
  range: z.enum(["week", "month", "filtered"]),
  month: z.string().optional(),
  from: z.number().optional(),
  to: z.number().optional(),
  useAi: z.boolean().optional(),
  trades: z
    .array(
      z.object({
        id: z.string(),
        symbol: z.string(),
        side: z.enum(["long", "short"]),
        marginMode: z.string(),
        openTime: z.number(),
        closeTime: z.number(),
        entryPrice: z.number(),
        exitPrice: z.number(),
        size: z.number(),
        pnl: z.number(),
        source: z.enum(["bitget", "demo"]),
      })
    )
    .optional(),
});

async function loadTrades(): Promise<ClosedTrade[]> {
  if (hasBitgetCredentials()) {
    try {
      return await fetchBitgetClosedPositions({ limit: 100 });
    } catch {
      /* fall through */
    }
  }
  return DEMO_TRADES;
}

export async function POST(request: Request) {
  try {
    const parsed = bodySchema.safeParse(await request.json());
    if (!parsed.success) {
      return NextResponse.json({ error: "invalid body" }, { status: 400 });
    }

    const { range, month, useAi } = parsed.data;
    let from = parsed.data.from;
    let to = parsed.data.to;
    let rangeLabel: string;

    if (range === "filtered" && from != null && to != null) {
      rangeLabel = "선택 구간";
    } else {
      const resolved = resolvePeriodRange(range === "filtered" ? "week" : range, {
        month,
      });
      from = resolved.from;
      to = resolved.to;
      rangeLabel = resolved.rangeLabel;
    }

    const allTrades = parsed.data.trades?.length
      ? (parsed.data.trades as ClosedTrade[])
      : await loadTrades();

    // For filtered: client may send already-filtered trades — use their min/max close
    if (range === "filtered" && parsed.data.trades?.length) {
      const times = parsed.data.trades.map((t) => t.closeTime);
      from = Math.min(...times);
      to = Math.max(...times);
      rangeLabel = `선택 ${parsed.data.trades.length}건`;
    }

    const journals = await listJournals();
    const summary = await buildPeriodSummaryWithOptionalAi({
      trades: allTrades,
      journals,
      from: from!,
      to: to!,
      rangeLabel,
      useAi: useAi === true,
    });

    const inRange = filterTradesByRange(allTrades, from!, to!);

    return NextResponse.json({
      summary,
      tradeIds: inRange.map((t) => t.id),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "summary failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
