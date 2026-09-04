import { promises as fs } from "fs";
import path from "path";
import { DEFAULT_CHECKLIST, normalizeChecklist } from "./rules";
import type { JournalEntry, ReviewResult } from "./types";

const DATA_DIR = process.env.VERCEL
  ? path.join("/tmp", "ledger-data")
  : path.join(process.cwd(), "data");
const JOURNAL_FILE = path.join(DATA_DIR, "journal.json");
const REVIEW_FILE = path.join(DATA_DIR, "reviews.json");

type JournalMap = Record<string, JournalEntry>;
type ReviewMap = Record<string, ReviewResult>;

async function ensureDataDir() {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    const raw = await fs.readFile(file, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

async function writeJson(file: string, value: unknown) {
  await ensureDataDir();
  await fs.writeFile(file, JSON.stringify(value, null, 2), "utf8");
}

export async function getJournal(tradeId: string): Promise<JournalEntry> {
  const all = await readJson<JournalMap>(JOURNAL_FILE, {});
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
  const all = await readJson<JournalMap>(JOURNAL_FILE, {});
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
  await writeJson(JOURNAL_FILE, all);
  return next;
}

export async function listJournals(): Promise<JournalMap> {
  return readJson<JournalMap>(JOURNAL_FILE, {});
}

export async function getReview(tradeId: string): Promise<ReviewResult | null> {
  const all = await readJson<ReviewMap>(REVIEW_FILE, {});
  return all[tradeId] ?? null;
}

export async function saveReview(review: ReviewResult): Promise<ReviewResult> {
  const all = await readJson<ReviewMap>(REVIEW_FILE, {});
  all[review.tradeId] = review;
  await writeJson(REVIEW_FILE, all);
  return review;
}
