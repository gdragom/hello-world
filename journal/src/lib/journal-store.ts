import { DEFAULT_CHECKLIST, normalizeChecklist } from "./rules";
import type { JournalEntry, ReviewResult } from "./types";
import { readDurableJson, writeDurableJson } from "./durable-store";

type JournalMap = Record<string, JournalEntry>;
type ReviewMap = Record<string, ReviewResult>;

export async function getJournal(tradeId: string): Promise<JournalEntry> {
  const all = await readDurableJson<JournalMap>("journal.json", {});
  const stored = all[tradeId];
  if (!stored) {
    return {
      tradeId,
      entryReason: "",
      exitReason: "",
      checklist: { ...DEFAULT_CHECKLIST },
      tags: [],
      screenshots: [],
      updatedAt: 0,
    };
  }
  return {
    ...stored,
    checklist: normalizeChecklist(stored.checklist),
    screenshots: stored.screenshots ?? [],
  };
}

export async function upsertJournal(
  partial: Partial<JournalEntry> & { tradeId: string }
): Promise<JournalEntry> {
  const all = await readDurableJson<JournalMap>("journal.json", {});
  const prev = all[partial.tradeId] ?? {
    tradeId: partial.tradeId,
    entryReason: "",
    exitReason: "",
    checklist: { ...DEFAULT_CHECKLIST },
    tags: [],
    screenshots: [],
    updatedAt: 0,
  };

  const next: JournalEntry = {
    ...prev,
    ...partial,
    checklist: normalizeChecklist({
      ...prev.checklist,
      ...(partial.checklist ?? {}),
    }),
    updatedAt: Date.now(),
  };

  all[partial.tradeId] = next;
  await writeDurableJson("journal.json", all);
  return next;
}

export async function listJournals(): Promise<JournalMap> {
  return readDurableJson<JournalMap>("journal.json", {});
}

export async function getReview(tradeId: string): Promise<ReviewResult | null> {
  const all = await readDurableJson<ReviewMap>("reviews.json", {});
  return all[tradeId] ?? null;
}

export async function saveReview(review: ReviewResult): Promise<ReviewResult> {
  const all = await readDurableJson<ReviewMap>("reviews.json", {});
  all[review.tradeId] = review;
  await writeDurableJson("reviews.json", all);
  return review;
}
