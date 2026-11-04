import { BitgetRestClient, loadConfig } from "@bitget-ai/bitget-agent-sdk";
import {
  fetchBitgetAccountBalance,
  getBitgetCredentials,
  hasBitgetCredentials,
} from "./bitget";
import { livePackFromEnv, planLiveOrder, type LivePlan } from "./bitget-sizing";
import { readDurableJson, writeDurableJson } from "./durable-store";
import type { AlertOrderType, AlertSide, SetupAlert } from "./types";

export type ExecMode = "off" | "dry_run" | "live";

export type ExecResult = {
  mode: ExecMode;
  attempted: boolean;
  skipped?: string;
  clientOid?: string;
  qty?: number;
  plan?: LivePlan;
  order?: Record<string, unknown>;
  trail?: Record<string, unknown> | null;
  response?: unknown;
  trailResponse?: unknown;
  error?: string;
};

type SeenOid = { oid: string; at: number };

function execMode(): ExecMode {
  const raw = (process.env.BITGET_EXECUTE ?? "off").trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "live") return "live";
  if (raw === "dry" || raw === "dry_run" || raw === "dry-run") return "dry_run";
  return "off";
}

function allowlist(): Set<string> {
  const raw = process.env.BITGET_SYMBOL_ALLOWLIST ?? "BTCUSDT";
  return new Set(
    raw
      .split(",")
      .map((s) => s.trim().toUpperCase().replace(/\.P$/i, ""))
      .filter(Boolean)
  );
}

function numEnv(key: string, fallback: number): number {
  const n = Number(process.env[key]);
  return Number.isFinite(n) ? n : fallback;
}

function createTradeClient(): BitgetRestClient {
  const { apiKey, secretKey, passphrase } = getBitgetCredentials();
  const config = loadConfig({
    modules: "account,trade,market",
    readOnly: false,
    apiKey,
    secretKey,
    passphrase,
  });
  return new BitgetRestClient(config);
}

function fmtQty(q: number): string {
  // BTCUSDT typical step 0.001; keep 3dp unless smaller.
  const maxDecimals = numEnv("BITGET_QTY_DECIMALS", 3);
  const fixed = q.toFixed(maxDecimals);
  return fixed.replace(/\.?0+$/, "") || "0";
}

function fmtPrice(p: number): string {
  const maxDecimals = numEnv("BITGET_PRICE_DECIMALS", 1);
  return p.toFixed(maxDecimals);
}

function sanitizeOid(raw: string | null | undefined, side: AlertSide): string {
  const base = (raw ?? "").replace(/[^\.A-Za-z0-9_:-]/g, "").slice(0, 32);
  if (base.length >= 4) return base;
  const prefix = side === "short" ? "es" : "el";
  return `${prefix}${Date.now()}`.slice(0, 32);
}

async function oidSeen(oid: string): Promise<boolean> {
  const all = await readDurableJson<SeenOid[]>("exec-oids.json", []);
  return all.some((row) => row.oid === oid);
}

async function rememberOid(oid: string): Promise<void> {
  const all = await readDurableJson<SeenOid[]>("exec-oids.json", []);
  all.unshift({ oid, at: Date.now() });
  await writeDurableJson("exec-oids.json", all.slice(0, 200));
}

async function resolvePlan(
  alert: SetupAlert,
  liveEquityUsdt?: number | null
): Promise<LivePlan | { error: string }> {
  const riskOverride = numEnv("BITGET_RISK_USD", 0);
  const sized = { ...alert };
  if (riskOverride > 0 && sized.qty == null) {
    const entry = sized.entry ?? sized.price;
    const sl = sized.sl;
    if (entry != null && sl != null && Math.abs(entry - sl) > 0) {
      sized.qty = riskOverride / Math.abs(entry - sl);
    }
  }
  const plan = planLiveOrder(sized, livePackFromEnv(liveEquityUsdt));
  if ("error" in plan) return plan;
  const maxQty = numEnv("BITGET_MAX_QTY", 5);
  if (plan.qty > maxQty) {
    return { error: `qty ${plan.qty} exceeds BITGET_MAX_QTY=${maxQty}` };
  }
  return plan;
}

async function hasOpenPosition(
  client: BitgetRestClient,
  symbol: string
): Promise<boolean> {
  try {
    const result = await client.callOperation<unknown>("getPositionInfo", {
      category: "USDT-FUTURES",
      symbol,
    });
    const data = result.data as Record<string, unknown> | unknown[] | null;
    const list = Array.isArray(data)
      ? data
      : data && typeof data === "object" && Array.isArray((data as { list?: unknown }).list)
        ? ((data as { list: unknown[] }).list)
        : data
          ? [data]
          : [];
    return list.some((row) => {
      if (!row || typeof row !== "object") return false;
      const r = row as Record<string, unknown>;
      const size = Number(r.total ?? r.size ?? r.available ?? r.pos ?? 0);
      return Number.isFinite(size) && Math.abs(size) > 0;
    });
  } catch {
    // If position query fails, still allow dry_run; for live, fail closed below.
    return false;
  }
}

function buildOrderBody(alert: SetupAlert, qty: number, clientOid: string) {
  const symbol = alert.symbol.replace(/\.P$/i, "").toUpperCase();
  const side: "buy" | "sell" = alert.side === "short" ? "sell" : "buy";
  const posSide = alert.side === "short" ? "short" : "long";
  const orderType: AlertOrderType = alert.orderType ?? "market";
  const body: Record<string, unknown> = {
    category: "USDT-FUTURES",
    symbol,
    qty: fmtQty(qty),
    side,
    posSide,
    orderType,
    clientOid,
  };
  if (orderType === "limit") {
    const px = alert.entry ?? alert.price;
    if (px == null) throw new Error("limit order needs entry/price");
    body.price = fmtPrice(px);
    body.timeInForce = "gtc";
  }
  if (alert.sl != null && Number.isFinite(alert.sl)) {
    body.stopLoss = fmtPrice(alert.sl);
    body.slTriggerBy = "mark";
    body.slOrderType = "market";
  }
  if (alert.tp != null && Number.isFinite(alert.tp)) {
    body.takeProfit = fmtPrice(alert.tp);
    body.tpTriggerBy = "mark";
    body.tpOrderType = "market";
  }
  return body;
}

function buildTrailBody(alert: SetupAlert, qty: number, clientOid: string) {
  if (!alert.trail || alert.trailActivate == null || alert.trailRatio == null) {
    return null;
  }
  const symbol = alert.symbol.replace(/\.P$/i, "").toUpperCase();
  const posSide = alert.side === "short" ? "short" : "long";
  // Close long with sell; close short with buy.
  const side = alert.side === "short" ? "buy" : "sell";
  return {
    category: "USDT-FUTURES",
    symbol,
    type: "trailing_stop",
    side,
    posSide,
    qty: fmtQty(qty),
    clientOid: `t${clientOid}`.slice(0, 32),
    trailingStopParams: [
      {
        activationPrice: fmtPrice(alert.trailActivate),
        activationType: "mark",
        trailType: "ratio",
        trailVariance: String(alert.trailRatio),
        preOrderType: "market",
      },
    ],
  };
}

/**
 * Turn an ENTRY_READY alert into a Bitget USDT-FUTURES order.
 * Default mode is off; set BITGET_EXECUTE=dry_run|live.
 */
export async function maybeExecuteBitget(alert: SetupAlert): Promise<ExecResult> {
  const mode = execMode();
  if (mode === "off") {
    return { mode, attempted: false, skipped: "BITGET_EXECUTE=off" };
  }
  if (alert.stage !== "ENTRY_READY") {
    return { mode, attempted: false, skipped: `stage=${alert.stage}` };
  }
  if (alert.action && alert.action !== "enter") {
    return { mode, attempted: false, skipped: `action=${alert.action}` };
  }
  if (alert.side !== "long" && alert.side !== "short") {
    return { mode, attempted: false, skipped: "side unknown" };
  }

  const symbol = alert.symbol.replace(/\.P$/i, "").toUpperCase();
  if (!allowlist().has(symbol)) {
    return { mode, attempted: false, skipped: `symbol ${symbol} not allowlisted` };
  }

  let liveEquity: number | null = null;
  if (hasBitgetCredentials()) {
    try {
      const bal = await fetchBitgetAccountBalance({ coin: "USDT" });
      const eq = bal?.equity ?? bal?.available ?? 0;
      if (eq > 0) liveEquity = eq;
    } catch {
      // fall back to BITGET_ACCOUNT_USDT / MARGIN env
    }
  }

  const plan = await resolvePlan(alert, liveEquity);
  if ("error" in plan) {
    return { mode, attempted: false, skipped: plan.error };
  }
  const sized: SetupAlert = {
    ...alert,
    qty: plan.qty,
    sl: plan.sl,
    tp: plan.tp,
    entry: plan.entry,
  };

  const clientOid = sanitizeOid(alert.clientOid, alert.side);
  if (await oidSeen(clientOid)) {
    return { mode, attempted: false, skipped: `duplicate clientOid ${clientOid}`, clientOid };
  }

  let order: Record<string, unknown>;
  try {
    order = buildOrderBody(sized, plan.qty, clientOid);
  } catch (e) {
    return {
      mode,
      attempted: false,
      error: e instanceof Error ? e.message : String(e),
      clientOid,
    };
  }
  const trail = buildTrailBody(sized, plan.qty, clientOid);

  if (mode === "dry_run") {
    await rememberOid(clientOid);
    return {
      mode,
      attempted: true,
      clientOid,
      qty: plan.qty,
      plan,
      order,
      trail,
    };
  }

  if (!hasBitgetCredentials()) {
    return {
      mode,
      attempted: false,
      error: "Bitget credentials missing for live execute",
      clientOid,
    };
  }

  const client = createTradeClient();
  const open = await hasOpenPosition(client, symbol);
  if (open && (process.env.BITGET_ALLOW_PYRAMID ?? "0") !== "1") {
    return {
      mode,
      attempted: false,
      skipped: "open position exists (set BITGET_ALLOW_PYRAMID=1 to override)",
      clientOid,
      qty: plan.qty,
      plan,
      order,
    };
  }

  const leverage = plan.leverage > 0 ? plan.leverage : numEnv("BITGET_LEVERAGE", 0);
  if (leverage > 0) {
    try {
      await client.callOperation("setLeverage", {
        category: "USDT-FUTURES",
        symbol,
        leverage: String(leverage),
        holdSide: alert.side === "short" ? "short" : "long",
      });
    } catch {
      // non-fatal — account may already be set
    }
  }

  try {
    const placed = await client.callOperation("placeOrder", order);
    let trailResponse: unknown = null;
    if (trail) {
      try {
        trailResponse = await client.callOperation("placeStrategyOrder", trail);
      } catch (te) {
        trailResponse = {
          error: te instanceof Error ? te.message : String(te),
        };
      }
    }
    await rememberOid(clientOid);
    return {
      mode,
      attempted: true,
      clientOid,
      qty: plan.qty,
      plan,
      order,
      trail,
      response: placed.data ?? placed,
      trailResponse,
    };
  } catch (e) {
    return {
      mode,
      attempted: true,
      clientOid,
      qty: plan.qty,
      plan,
      order,
      trail,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
