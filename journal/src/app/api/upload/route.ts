import { NextResponse } from "next/server";
import { hasR2, uploadToR2 } from "@/lib/r2";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get("file");
  const tradeId = String(form.get("tradeId") ?? "misc");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "file required" }, { status: 400 });
  }
  if (!file.type.startsWith("image/")) {
    return NextResponse.json({ error: "image only" }, { status: 400 });
  }
  if (file.size > 4_500_000) {
    return NextResponse.json({ error: "max 4.5MB" }, { status: 400 });
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const safeName = file.name.replace(/[^\w.\-]+/g, "_").slice(0, 80);
  const key = `ledger/${tradeId}/${Date.now()}-${safeName}`;

  if (!hasR2()) {
    const dataUrl = `data:${file.type};base64,${bytes.toString("base64")}`;
    return NextResponse.json({
      mode: "inline",
      screenshot: {
        id: key,
        name: file.name,
        dataUrl,
        createdAt: Date.now(),
      },
      message:
        "R2 not configured — stored inline (ok for local; use R2 on Vercel).",
    });
  }

  try {
    const url = await uploadToR2({
      key,
      body: bytes,
      contentType: file.type || "image/jpeg",
    });
    return NextResponse.json({
      mode: "r2",
      screenshot: {
        id: key,
        name: file.name,
        url,
        createdAt: Date.now(),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "upload failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
