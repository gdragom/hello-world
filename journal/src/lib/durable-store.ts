import { promises as fs } from "fs";
import path from "path";
import { getJsonFromR2, hasR2, putJsonToR2 } from "./r2";

const DATA_DIR = process.env.VERCEL
  ? path.join("/tmp", "ledger-data")
  : path.join(process.cwd(), "data");

const R2_PREFIX = "app-data";

async function ensureDataDir() {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

/**
 * Durable JSON: R2 when configured (survives Vercel redeploy), else local/tmp.
 * Keys live under app-data/ in R2_DATA_BUCKET (or R2_BUCKET).
 */
export async function readDurableJson<T>(
  name: string,
  fallback: T
): Promise<T> {
  if (hasR2()) {
    return getJsonFromR2<T>(`${R2_PREFIX}/${name}`, fallback);
  }
  try {
    const raw = await fs.readFile(path.join(DATA_DIR, name), "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export async function writeDurableJson(
  name: string,
  value: unknown
): Promise<void> {
  if (hasR2()) {
    await putJsonToR2(`${R2_PREFIX}/${name}`, value);
    return;
  }
  await ensureDataDir();
  await fs.writeFile(
    path.join(DATA_DIR, name),
    JSON.stringify(value, null, 2),
    "utf8"
  );
}
