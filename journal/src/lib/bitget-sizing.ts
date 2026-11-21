import type { AlertSide, SetupAlert } from "./types";

export type LivePlan = {
  entry: number;
  qty: number;
  sl: number | null;
  tp: number | null;
  marginUsdt: number;
  equityUsdt: number;
  sizedBaseUsdt: number;
  leverage: number;
  notional: number;
  slPct: number;
  tpPct: number;
  riskUsd: number;
  rewardUsd: number;
  targetSlUsd: number;
  targetTpUsd: number;
};

function numEnv(key: string, fallback: number): number {
  const n = Number(process.env[key]);
  return Number.isFinite(n) ? n : fallback;
}

export type LivePack = {
  /** Live / fallback wallet equity (informational). */
  equityUsdt: number;
  /** Tier used for margin + 5%/10% risk (e.g. 200 until 300). */
  sizedBaseUsdt: number;
  marginUsdt: number;
  leverage: number;
  slPct: number;
  tpPct: number;
  /**
   * Price-distance targets (fallback when alert has no sl/tp).
   * Long TV Fixed: SL $500 / TP $1100. Short Fixed: SL $1000 / TP $2100.
   */
  targetSlUsd: number;
  targetTpUsd: number;
  /** Cash loss / gain. 0 = use slPct/tpPct of sized base (5%/11% on $100 → $5/$11). */
  targetRiskUsd: number;
  targetRewardUsd: number;
};

/** Floor equity to SIZE_STEP, never below SIZE_MIN (default 100 → 200 → 300…). */
export function tierSizedBase(equityUsdt: number): number {
  const step = Math.max(1, numEnv("BITGET_SIZE_STEP", 100));
  const min = Math.max(step, numEnv("BITGET_SIZE_MIN", 100));
  if (!(equityUsdt > 0)) return min;
  const stepped = Math.floor(equityUsdt / step) * step;
  return Math.max(min, stepped);
}

/** TV Fixed price distances by side (overridable via env). */
export function targetDistancesForSide(side?: AlertSide | null): {
  targetSlUsd: number;
  targetTpUsd: number;
} {
  // Short must not inherit shared BITGET_TARGET_*_USD=500/1100 from Long packs.
  if (side === "short") {
    return {
      targetSlUsd: numEnv("BITGET_TARGET_SL_USD_SHORT", 1000),
      targetTpUsd: numEnv("BITGET_TARGET_TP_USD_SHORT", 2100),
    };
  }
  return {
    targetSlUsd: numEnv(
      "BITGET_TARGET_SL_USD_LONG",
      numEnv("BITGET_TARGET_SL_USD", 500)
    ),
    targetTpUsd: numEnv(
      "BITGET_TARGET_TP_USD_LONG",
      numEnv("BITGET_TARGET_TP_USD", 1100)
    ),
  };
}

/**
 * Starter pack from env. Pass `liveEquityUsdt` (Bitget wallet) so each trade
 * tiers size (200 / 300 / 400…) and sizes SL/TP off that base.
 * Pass `side` so Short uses SL $1000 / TP $2100 when alert prices are missing.
 */
export function livePackFromEnv(
  liveEquityUsdt?: number | null,
  side?: AlertSide | null
): LivePack {
  const marginEnv = numEnv("BITGET_MARGIN_USDT", 0);
  const accountEnv = numEnv("BITGET_ACCOUNT_USDT", 100);
  const live =
    liveEquityUsdt != null && Number.isFinite(liveEquityUsdt) && liveEquityUsdt > 0
      ? liveEquityUsdt
      : 0;
  const equityUsdt = live > 0 ? live : accountEnv > 0 ? accountEnv : marginEnv;
  const sizedBaseUsdt =
    marginEnv > 0 ? marginEnv : tierSizedBase(equityUsdt > 0 ? equityUsdt : accountEnv);
  const { targetSlUsd, targetTpUsd } = targetDistancesForSide(side);
  return {
    equityUsdt: equityUsdt > 0 ? equityUsdt : sizedBaseUsdt,
    sizedBaseUsdt,
    marginUsdt: sizedBaseUsdt,
    leverage: numEnv("BITGET_LEVERAGE", 10),
    slPct: numEnv("BITGET_SL_PCT", 5),
    tpPct: numEnv("BITGET_TP_PCT", 11),
    targetSlUsd,
    targetTpUsd,
    targetRiskUsd: numEnv("BITGET_TARGET_RISK_USD", 0),
    targetRewardUsd: numEnv("BITGET_TARGET_REWARD_USD", 0),
  };
}

export function slTpFromBalance(
  side: AlertSide,
  entry: number,
  qty: number,
  equityUsdt: number,
  slPct: number,
  tpPct: number
): { sl: number | null; tp: number | null; riskUsd: number; rewardUsd: number } {
  const long = side !== "short";
  const riskUsd = slPct > 0 ? equityUsdt * (slPct / 100) : 0;
  const rewardUsd = tpPct > 0 ? equityUsdt * (tpPct / 100) : 0;
  const distSl = qty > 0 && riskUsd > 0 ? riskUsd / qty : 0;
  const distTp = qty > 0 && rewardUsd > 0 ? rewardUsd / qty : 0;
  const sl = distSl > 0 ? (long ? entry - distSl : entry + distSl) : null;
  const tp = distTp > 0 ? (long ? entry + distTp : entry - distTp) : null;
  return { sl, tp, riskUsd, rewardUsd };
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/**
 * Live sizing from the TV Fixed pack.
 * Long: SL $500 / TP $1100. Short: SL $1000 / TP $2100 (risk cash still SL_PCT of base).
 * On a $100 wallet, default 5% risk → $5 cash SL; Short qty ≈ 0.005 vs Long ≈ 0.01
 * at those price distances. Alert sl/tp prices override env targets when present.
 */
export function planLiveOrder(
  alert: Pick<SetupAlert, "side" | "entry" | "price" | "sl" | "tp" | "qty">,
  pack = livePackFromEnv(undefined, alert.side)
): LivePlan | { error: string } {
  const entry = alert.entry ?? alert.price;
  if (entry == null || !Number.isFinite(entry) || entry <= 0) {
    return { error: "entry/price missing for live sizing" };
  }

  const base = pack.sizedBaseUsdt > 0 ? pack.sizedBaseUsdt : pack.marginUsdt;
  if (!(base > 0)) {
    return {
      error:
        "sizing base missing — set BITGET_ACCOUNT_USDT=100 or BITGET_MARGIN_USDT",
    };
  }

  const slPct = pack.slPct > 0 ? pack.slPct : 5;
  const tpPct = pack.tpPct > 0 ? pack.tpPct : 10;
  const wantRisk = pack.targetRiskUsd > 0 ? pack.targetRiskUsd : base * (slPct / 100);
  const wantReward = pack.targetRewardUsd > 0 ? pack.targetRewardUsd : base * (tpPct / 100);

  let qty: number;
  let leverage: number;
  let distSl: number;
  let distTp: number;
  let riskUsd = wantRisk;
  let rewardUsd = wantReward;
  let targetSlUsd = pack.targetSlUsd;
  let targetTpUsd = pack.targetTpUsd;

  const alertSl = alert.sl;
  const alertTp = alert.tp;
  if (alertSl != null && Number.isFinite(alertSl) && Math.abs(entry - alertSl) > 0) {
    targetSlUsd = Math.abs(entry - alertSl);
  }
  if (alertTp != null && Number.isFinite(alertTp) && Math.abs(entry - alertTp) > 0) {
    targetTpUsd = Math.abs(entry - alertTp);
  }

  if (targetSlUsd > 0) {
    if (!(targetTpUsd > 0)) targetTpUsd = targetSlUsd * (wantReward / Math.max(wantRisk, 1e-9));
    distSl = targetSlUsd;
    distTp = targetTpUsd;
    qty = wantRisk / distSl;
    leverage = (qty * entry) / base;
    const levMin = numEnv("BITGET_LEVERAGE_MIN", 1);
    const levMax = numEnv("BITGET_LEVERAGE_MAX", 20);
    if (leverage > levMax || leverage < levMin) {
      leverage = clamp(leverage, levMin, levMax);
      qty = (base * leverage) / entry;
    }
    riskUsd = qty * distSl;
    rewardUsd = qty * distTp;
  } else {
    leverage = pack.leverage > 0 ? pack.leverage : 10;
    qty = (base * leverage) / entry;
    distSl = qty > 0 ? wantRisk / qty : 0;
    distTp = qty > 0 ? wantReward / qty : 0;
    targetSlUsd = distSl;
    targetTpUsd = distTp;
    riskUsd = qty * distSl;
    rewardUsd = qty * distTp;
  }

  if (!Number.isFinite(qty) || qty <= 0) {
    return { error: "qty calc failed — check equity / leverage / targets" };
  }

  const long = alert.side !== "short";
  const sl = distSl > 0 ? (long ? entry - distSl : entry + distSl) : alert.sl ?? null;
  const tp = distTp > 0 ? (long ? entry + distTp : entry - distTp) : alert.tp ?? null;

  return {
    entry,
    qty,
    sl,
    tp,
    marginUsdt: base,
    equityUsdt: pack.equityUsdt,
    sizedBaseUsdt: base,
    leverage,
    notional: qty * entry,
    slPct,
    tpPct,
    riskUsd,
    rewardUsd,
    targetSlUsd,
    targetTpUsd,
  };
}
