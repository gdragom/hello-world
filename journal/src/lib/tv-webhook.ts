import type { AlertSide, AlertStage, SetupAlert } from "./types";

const STAGES: AlertStage[] = ["SETUP_ARMED", "ENTRY_READY", "INVALID"];

function asStage(v: unknown): AlertStage {
  const s = String(v ?? "")
    .trim()
    .toUpperCase();
  if (STAGES.includes(s as AlertStage)) return s as AlertStage;
  if (s.includes("ENTRY") || s.includes("CISD") || s.includes("READY")) {
    return "ENTRY_READY";
  }
  if (s.includes("INVALID") || s.includes("EXPIRE")) return "INVALID";
  return "SETUP_ARMED";
}

function asSide(v: unknown): AlertSide {
  const s = String(v ?? "")
    .trim()
    .toLowerCase();
  if (s === "long" || s === "buy" || s === "bull") return "long";
  if (s === "short" || s === "sell" || s === "bear") return "short";
  return "unknown";
}

function asPrice(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Accept JSON object or TradingView text message. */
export function parseTradingViewPayload(raw: unknown): Omit<
  SetupAlert,
  "id" | "createdAt" | "source"
> {
  let data: Record<string, unknown> = {};

  if (typeof raw === "string") {
    const trimmed = raw.trim();
    try {
      data = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      const parts = Object.fromEntries(
        trimmed
          .split(/[\n,|]/)
          .map((p) => p.trim())
          .filter(Boolean)
          .map((p) => {
            const [k, ...rest] = p.split(/[:=]/);
            return [k.trim().toLowerCase(), rest.join(":").trim()];
          })
      );
      data = parts;
    }
  } else if (raw && typeof raw === "object") {
    data = raw as Record<string, unknown>;
  }

  const stage = asStage(data.stage ?? data.status ?? data.event);
  const symbol = String(
    data.symbol ?? data.ticker ?? data.sym ?? "BTCUSDT"
  )
    .replace(".P", "")
    .toUpperCase();
  const side = asSide(data.side ?? data.direction ?? data.bias);
  const timeframe = String(data.timeframe ?? data.tf ?? data.interval ?? "60");
  const price = asPrice(data.price ?? data.close);
  const message = String(data.message ?? data.msg ?? data.text ?? "").slice(
    0,
    500
  );

  return {
    stage,
    symbol,
    side,
    timeframe,
    price,
    message:
      message ||
      `${stage} ${symbol} ${side} ${timeframe}${
        price != null ? ` @ ${price}` : ""
      }`,
  };
}

export function verifyWebhookSecret(payload: unknown, headerSecret?: string | null) {
  const expected = process.env.TV_WEBHOOK_SECRET?.trim();
  if (!expected) return true;

  if (headerSecret && headerSecret === expected) return true;

  if (payload && typeof payload === "object" && "secret" in payload) {
    return String((payload as { secret?: unknown }).secret) === expected;
  }

  if (typeof payload === "string" && payload.includes(expected)) return true;

  return false;
}
