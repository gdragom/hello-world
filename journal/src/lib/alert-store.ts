import { promises as fs } from "fs";
import path from "path";
import type { SetupAlert } from "./types";

const DATA_DIR = process.env.VERCEL
  ? path.join("/tmp", "ledger-data")
  : path.join(process.cwd(), "data");
const FILE = path.join(DATA_DIR, "alerts.json");

const MAX = 100;

async function readAll(): Promise<SetupAlert[]> {
  try {
    return JSON.parse(await fs.readFile(FILE, "utf8")) as SetupAlert[];
  } catch {
    return [];
  }
}

async function writeAll(alerts: SetupAlert[]) {
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.writeFile(FILE, JSON.stringify(alerts, null, 2), "utf8");
}

export async function listAlerts(limit = 40): Promise<SetupAlert[]> {
  const all = await readAll();
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
  const all = await readAll();
  all.unshift(alert);
  await writeAll(all.slice(0, MAX));
  return alert;
}
