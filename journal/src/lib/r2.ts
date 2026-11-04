import { createHash, createHmac } from "crypto";

function required(name: string): string {
  const v = process.env[name]?.trim();
  if (!v) throw new Error(`Missing ${name}`);
  return v;
}

export function hasR2(): boolean {
  return Boolean(
    process.env.R2_ACCOUNT_ID?.trim() &&
      process.env.R2_ACCESS_KEY_ID?.trim() &&
      process.env.R2_SECRET_ACCESS_KEY?.trim() &&
      process.env.R2_BUCKET?.trim()
  );
}

/** Optional private bucket for journal JSON (recommended if shots bucket is public). */
export function r2DataBucket(): string {
  return (
    process.env.R2_DATA_BUCKET?.trim() ||
    process.env.R2_BUCKET?.trim() ||
    ""
  );
}

function hmac(key: Buffer | string, data: string) {
  return createHmac("sha256", key).update(data, "utf8").digest();
}

function hashHex(data: Buffer | string) {
  return createHash("sha256").update(data).digest("hex");
}

function amzDate(d = new Date()) {
  const iso = d.toISOString().replace(/[:-]|\.\d{3}/g, "");
  return { amz: iso.slice(0, 16), date: iso.slice(0, 8) };
}

const EMPTY_HASH =
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

async function signedFetch(options: {
  method: "GET" | "PUT";
  bucket: string;
  key: string;
  body?: Buffer;
  contentType?: string;
}): Promise<Response> {
  const accountId = required("R2_ACCOUNT_ID");
  const accessKey = required("R2_ACCESS_KEY_ID");
  const secretKey = required("R2_SECRET_ACCESS_KEY");
  const host = `${accountId}.r2.cloudflarestorage.com`;
  const path = `/${options.bucket}/${options.key}`;
  const url = `https://${host}${path}`;
  const { amz, date } = amzDate();
  const region = "auto";
  const service = "s3";
  const payloadHash = options.body ? hashHex(options.body) : EMPTY_HASH;
  const contentType = options.contentType ?? "application/octet-stream";

  const canonicalHeaders =
    (options.method === "PUT" ? `content-type:${contentType}\n` : "") +
    `host:${host}\n` +
    `x-amz-content-sha256:${payloadHash}\n` +
    `x-amz-date:${amz}\n`;
  const signedHeaders =
    options.method === "PUT"
      ? "content-type;host;x-amz-content-sha256;x-amz-date"
      : "host;x-amz-content-sha256;x-amz-date";
  const canonicalRequest = [
    options.method,
    path,
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const credentialScope = `${date}/${region}/${service}/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amz,
    credentialScope,
    hashHex(canonicalRequest),
  ].join("\n");

  const kDate = hmac(`AWS4${secretKey}`, date);
  const kRegion = hmac(kDate, region);
  const kService = hmac(kRegion, service);
  const kSigning = hmac(kService, "aws4_request");
  const signature = createHmac("sha256", kSigning)
    .update(stringToSign, "utf8")
    .digest("hex");

  const authorization =
    `AWS4-HMAC-SHA256 Credential=${accessKey}/${credentialScope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  const headers: Record<string, string> = {
    Host: host,
    "x-amz-content-sha256": payloadHash,
    "x-amz-date": amz,
    Authorization: authorization,
  };
  if (options.method === "PUT") {
    headers["Content-Type"] = contentType;
  }

  return fetch(url, {
    method: options.method,
    headers,
    body: options.body ? new Uint8Array(options.body) : undefined,
  });
}

/** Upload bytes to Cloudflare R2 via S3 PutObject (SigV4). */
export async function uploadToR2(options: {
  key: string;
  body: Buffer;
  contentType: string;
  bucket?: string;
  publicUrl?: boolean;
}): Promise<string> {
  const bucket = options.bucket || required("R2_BUCKET");
  const publicBase = process.env.R2_PUBLIC_BASE_URL?.trim();

  const res = await signedFetch({
    method: "PUT",
    bucket,
    key: options.key,
    body: options.body,
    contentType: options.contentType,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`R2 upload failed: ${res.status} ${text.slice(0, 200)}`);
  }

  if (options.publicUrl !== false && publicBase && bucket === process.env.R2_BUCKET?.trim()) {
    return `${publicBase.replace(/\/$/, "")}/${options.key}`;
  }
  return `r2://${bucket}/${options.key}`;
}

/** Download object; returns null if missing. */
export async function getFromR2(options: {
  key: string;
  bucket?: string;
}): Promise<Buffer | null> {
  const bucket = options.bucket || r2DataBucket();
  if (!bucket) throw new Error("Missing R2 bucket");

  const res = await signedFetch({
    method: "GET",
    bucket,
    key: options.key,
  });

  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`R2 get failed: ${res.status} ${text.slice(0, 200)}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

export async function putJsonToR2(key: string, value: unknown): Promise<void> {
  const bucket = r2DataBucket();
  if (!bucket) throw new Error("Missing R2 data bucket");
  await uploadToR2({
    key,
    body: Buffer.from(JSON.stringify(value, null, 2), "utf8"),
    contentType: "application/json",
    bucket,
    publicUrl: false,
  });
}

export async function getJsonFromR2<T>(key: string, fallback: T): Promise<T> {
  try {
    const buf = await getFromR2({ key, bucket: r2DataBucket() });
    if (!buf) return fallback;
    return JSON.parse(buf.toString("utf8")) as T;
  } catch {
    return fallback;
  }
}
