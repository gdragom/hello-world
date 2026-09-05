import { NextResponse } from "next/server";
import { getPeriodNote, upsertPeriodNote } from "@/lib/period-store";
import { z } from "zod";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "id required" }, { status: 400 });
  }
  const note = await getPeriodNote(id);
  return NextResponse.json({ note });
}

const bodySchema = z.object({
  id: z.string().min(1),
  note: z.string(),
});

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten() },
      { status: 400 }
    );
  }
  const note = await upsertPeriodNote(parsed.data.id, parsed.data.note);
  return NextResponse.json({ note });
}
