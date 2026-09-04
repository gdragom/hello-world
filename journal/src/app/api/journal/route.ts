import { NextResponse } from "next/server";
import { getJournal, listJournals, upsertJournal } from "@/lib/journal-store";
import { normalizeChecklist } from "@/lib/rules";
import { z } from "zod";

export const dynamic = "force-dynamic";

const bodySchema = z.object({
  tradeId: z.string().min(1),
  entryReason: z.string().optional(),
  exitReason: z.string().optional(),
  tags: z.array(z.string()).optional(),
  screenshots: z
    .array(
      z.object({
        id: z.string(),
        name: z.string(),
        dataUrl: z.string(),
        createdAt: z.number(),
      })
    )
    .optional(),
  checklist: z
    .object({
      dailyBias: z.boolean().optional(),
      mssConfirmed: z.boolean().optional(),
      fibDiscountOk: z.boolean().optional(),
      cisdConfirmed: z.boolean().optional(),
      sessionOk: z.boolean().optional(),
      noEarlyPartialBefore2R: z.boolean().optional(),
    })
    .optional(),
});

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const tradeId = searchParams.get("tradeId");
  if (!tradeId) {
    const all = await listJournals();
    return NextResponse.json({ journals: all });
  }
  const journal = await getJournal(tradeId);
  return NextResponse.json({ journal });
}

export async function POST(request: Request) {
  const json = await request.json();
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const journal = await upsertJournal({
    tradeId: parsed.data.tradeId,
    entryReason: parsed.data.entryReason,
    exitReason: parsed.data.exitReason,
    tags: parsed.data.tags,
    screenshots: parsed.data.screenshots,
    checklist: normalizeChecklist(parsed.data.checklist),
  });

  return NextResponse.json({ journal });
}
