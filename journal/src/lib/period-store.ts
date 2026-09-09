import type { PeriodNote } from "./types";
import { readDurableJson, writeDurableJson } from "./durable-store";

type PeriodMap = Record<string, PeriodNote>;

export async function getPeriodNote(id: string): Promise<PeriodNote> {
  const all = await readDurableJson<PeriodMap>("periods.json", {});
  return all[id] ?? { id, note: "", updatedAt: 0 };
}

export async function upsertPeriodNote(
  id: string,
  note: string
): Promise<PeriodNote> {
  const all = await readDurableJson<PeriodMap>("periods.json", {});
  const next: PeriodNote = { id, note, updatedAt: Date.now() };
  all[id] = next;
  await writeDurableJson("periods.json", all);
  return next;
}
