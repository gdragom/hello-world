import { NextResponse } from "next/server";
import { addAlert } from "@/lib/alert-store";
import { maybeExecuteBitget } from "@/lib/bitget-exec";
import { notifyDiscord } from "@/lib/discord";
import { notifyTelegram } from "@/lib/telegram";
import {
  parseTradingViewPayload,
  verifyWebhookSecret,
} from "@/lib/tv-webhook";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const headerSecret =
    request.headers.get("x-ledger-secret") ??
    request.headers.get("x-webhook-secret");

  let raw: unknown;
  const contentType = request.headers.get("content-type") ?? "";
  try {
    if (contentType.includes("application/json")) {
      raw = await request.json();
    } else {
      const text = await request.text();
      try {
        raw = JSON.parse(text);
      } catch {
        raw = text;
      }
    }
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  if (!verifyWebhookSecret(raw, headerSecret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const parsed = parseTradingViewPayload(raw);
  const alert = await addAlert(parsed);
  const exec = await maybeExecuteBitget(alert).catch((e: unknown) => ({
    mode: "off" as const,
    attempted: false,
    error: e instanceof Error ? e.message : String(e),
  }));
  const [telegram, discord] = await Promise.all([
    notifyTelegram(alert, exec).catch(() => false),
    notifyDiscord(alert, exec).catch(() => false),
  ]);

  return NextResponse.json({ ok: true, alert, telegram, discord, exec });
}
