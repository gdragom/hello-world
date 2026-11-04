import type {
  AlertAction,
  AlertOrderType,
  AlertSide,
  AlertStage,
  SetupAlert,
} from "./types";

const STAGES: AlertStage[] = ["SETUP_ARMED", "ENTRY_READY", "INVALID"];

function asStage(v: unknown): AlertStage {
  const s = String(v ?? "")
    .trim()
    .toUpperCase();
  if (STAGES.includes(s as AlertStage)) return s as AlertStage;
  if (s.includes("ENTRY") || s.includes("CISD") || s.includes("READY")) {
    return "ENTRY_READY";
  }
  if (s.includes("INVALID") || s.includes("EXPIRE") || s.includes("FLAT")) {
    return "INVALID";
  }
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

function asAction(v: unknown, stage: AlertStage): AlertAction {
  const s = String(v ?? "")
    .trim()
    .toLowerCase();
  if (s === "enter" || s === "entry" || s === "open") return "enter";
  if (s === "flatten" || s === "close" || s === "exit") return "flatten";
  if (stage === "ENTRY_READY") return "enter";
  return "none";
}

function asOrderType(v: unknown): AlertOrderType {
  const s = String(v ?? "")
    .trim()
    .toLowerCase();
  return s === "limit" ? "limit" : "market";
}

function asPrice(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function asBool(v: unknown): boolean {
  if (typeof v === "boolean") return v;
  const s = String(v ?? "")
    .trim()
    .toLowerCase();
  return s === "1" || s === "true" || s === "yes";
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
  const entry = asPrice(data.entry ?? data.entryPrice ?? data.price ?? data.close);
  const sl = asPrice(data.sl ?? data.stop ?? data.stopLoss ?? data.stop_loss);
  const tp = asPrice(data.tp ?? data.takeProfit ?? data.take_profit ?? data.limit);
  const qty = asPrice(data.qty ?? data.size ?? data.quantity);
  const riskUsd = asPrice(data.riskUsd ?? data.risk ?? data.risk_usd);
  const confidence = asPrice(data.confidence ?? data.conf);
  const trailActivate = asPrice(
    data.trailActivate ?? data.trail_activate ?? data.activationPrice
  );
  const trailRatio = asPrice(
    data.trailRatio ?? data.trail_ratio ?? data.trailVariance
  );
  const clientOid = data.clientOid ?? data.client_oid ?? data.oid;
  const bias = data.bias != null ? String(data.bias).slice(0, 40) : null;
  const message = String(data.message ?? data.msg ?? data.text ?? "").slice(
    0,
    500
  );
  const action = asAction(data.action ?? data.cmd, stage);
  const orderType = asOrderType(data.orderType ?? data.order_type ?? data.type);
  const trail =
    data.trail != null
      ? asBool(data.trail)
      : trailActivate != null && trailRatio != null;

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
    action,
    entry,
    sl,
    tp,
    qty,
    riskUsd,
    orderType,
    clientOid: clientOid != null ? String(clientOid).slice(0, 32) : null,
    trail,
    trailActivate,
    trailRatio,
    confidence,
    bias,
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
