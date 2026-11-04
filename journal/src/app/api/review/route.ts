import { NextResponse } from "next/server";
import { DEMO_TRADES } from "@/lib/demo-data";
import { fetchBitgetClosedPositions, hasBitgetCredentials } from "@/lib/bitget";
import { getJournal, getReview, saveReview, upsertJournal } from "@/lib/journal-store";
import { buildReview } from "@/lib/review";
import type { ClosedTrade, JournalEntry } from "@/lib/types";
import { z } from "zod";

export const dynamic = "force-dynamic";

const bodySchema = z.object({
  tradeId: z.string().min(1),
  trade: z
    .object({
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
    .optional(),
  riskDollars: z.number().positive().optional(),
  useAi: z.boolean().optional(),
  journal: z
    .object({
      tradeId: z.string(),
      entryReason: z.string().optional(),
      exitReason: z.string().optional(),
      tags: z.array(z.string()).optional(),
      checklist: z.record(z.string(), z.boolean()).optional(),
    })
    .optional(),
});

async function resolveTrade(
  tradeId: string,
  embedded?: ClosedTrade
): Promise<ClosedTrade | null> {
  if (embedded && embedded.id === tradeId) return embedded;
  const demo = DEMO_TRADES.find((t) => t.id === tradeId);
  if (demo) return demo;
  if (hasBitgetCredentials()) {
    const trades = await fetchBitgetClosedPositions({ limit: 100 });
    return trades.find((t) => t.id === tradeId) ?? null;
  }
  return null;
}

export async function GET(request: Request) {
  const tradeId = new URL(request.url).searchParams.get("tradeId");
  if (!tradeId) {
    return NextResponse.json({ error: "tradeId required" }, { status: 400 });
  }
  const review = await getReview(tradeId);
  return NextResponse.json({ review });
}

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const trade = await resolveTrade(
    parsed.data.tradeId,
    parsed.data.trade as ClosedTrade | undefined
  );
  if (!trade) {
    return NextResponse.json({ error: "Trade not found" }, { status: 404 });
  }

  if (parsed.data.journal) {
    await upsertJournal({
      tradeId: trade.id,
      entryReason: parsed.data.journal.entryReason,
      exitReason: parsed.data.journal.exitReason,
      tags: parsed.data.journal.tags,
      checklist: parsed.data.journal.checklist as unknown as
        | JournalEntry["checklist"]
        | undefined,
    });
  }
  const journal = await getJournal(trade.id);
  const review = await buildReview({
    trade,
    journal,
    riskDollars: parsed.data.riskDollars,
    useAi: parsed.data.useAi,
  });
  await saveReview(review);
  return NextResponse.json({ review });
}
