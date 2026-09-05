import { promises as fs } from "fs";
import path from "path";
import type { PeriodNote } from "./types";

const DATA_DIR = process.env.VERCEL
  ? path.join("/tmp", "ledger-data")
  : path.join(process.cwd(), "data");
const FILE = path.join(DATA_DIR, "periods.json");

type PeriodMap = Record<string, PeriodNote>;

async function readAll(): Promise<PeriodMap> {
  try {
    return JSON.parse(await fs.readFile(FILE, "utf8")) as PeriodMap;
  } catch {
    return {};
  }
}

async function writeAll(value: PeriodMap) {
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.writeFile(FILE, JSON.stringify(value, null, 2), "utf8");
}

export async function getPeriodNote(id: string): Promise<PeriodNote> {
  const all = await readAll();
  return all[id] ?? { id, note: "", updatedAt: 0 };
}

export async function upsertPeriodNote(
  id: string,
  note: string
): Promise<PeriodNote> {
  const all = await readAll();
  const next: PeriodNote = { id, note, updatedAt: Date.now() };
  all[id] = next;
  await writeAll(all);
  return next;
}
