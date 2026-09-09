import type { SetupAlert } from "./types";
import { readDurableJson, writeDurableJson } from "./durable-store";

const MAX = 100;

export async function listAlerts(limit = 40): Promise<SetupAlert[]> {
  const all = await readDurableJson<SetupAlert[]>("alerts.json", []);
  return all.slice(0, limit);
}

export async function addAlert(
  partial: Omit<SetupAlert, "id" | "createdAt" | "source"> & {
    source?: SetupAlert["source"];
  }
): Promise<SetupAlert> {
  const alert: SetupAlert = {
    ...partial,
    id: `tv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    source: partial.source ?? "tradingview",
    createdAt: Date.now(),
  };
  const all = await readDurableJson<SetupAlert[]>("alerts.json", []);
  all.unshift(alert);
  await writeDurableJson("alerts.json", all.slice(0, MAX));
  return alert;
}
