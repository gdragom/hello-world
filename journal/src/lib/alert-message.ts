import type { ExecResult } from "./bitget-exec";
import type { SetupAlert } from "./types";

export function buildAlertMessage(
  alert: SetupAlert,
  exec?: ExecResult
): string {
  const stageLabel =
    alert.stage === "SETUP_ARMED"
      ? "1H 셋업 열림"
      : alert.stage === "ENTRY_READY"
        ? "진입 신호"
        : "셋업 만료";

  const lines = [
    `LEDGER · ${stageLabel}`,
    `${alert.symbol} ${alert.side.toUpperCase()} · ${alert.timeframe}`,
    alert.price != null ? `price ${alert.price}` : null,
    alert.entry != null ? `entry ${alert.entry}` : null,
    alert.sl != null ? `sl ${alert.sl}` : null,
    alert.tp != null ? `tp ${alert.tp}` : null,
    alert.qty != null ? `qty ${alert.qty}` : null,
    alert.orderType ? `order ${alert.orderType}` : null,
    alert.trail
      ? `trail @ ${alert.trailActivate ?? "?"} ratio ${alert.trailRatio ?? "?"}%`
      : null,
    alert.message || null,
  ];

  if (exec?.attempted) {
    if (exec.mode === "dry_run") {
      lines.push(
        `exec DRY-RUN oid=${exec.clientOid ?? "?"} qty=${exec.qty ?? "?"}`
      );
    } else if (exec.error) {
      lines.push(`exec LIVE FAIL: ${exec.error}`);
    } else {
      lines.push(`exec LIVE OK oid=${exec.clientOid ?? "?"}`);
    }
  } else if (exec?.skipped && exec.mode !== "off") {
    lines.push(`exec skip: ${exec.skipped}`);
  }

  return lines.filter(Boolean).join("\n");
}

export function alertEmbedColor(alert: SetupAlert): number {
  if (alert.stage === "INVALID") return 0x888888;
  if (alert.side === "long") return 0x3dba7e;
  if (alert.side === "short") return 0xd4543c;
  return 0x4a7cff;
}
