import { NextResponse } from "next/server";
import { listAlerts } from "@/lib/alert-store";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const limit = Number(new URL(request.url).searchParams.get("limit") ?? 40);
  const alerts = await listAlerts(
    Number.isFinite(limit) ? Math.min(limit, 100) : 40
  );
  return NextResponse.json({ alerts });
}
