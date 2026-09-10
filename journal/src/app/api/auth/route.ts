import { NextResponse } from "next/server";

const COOKIE = "ledger_gate";

export async function POST(request: Request) {
  const password = process.env.SITE_PASSWORD?.trim();
  if (!password) {
    return NextResponse.json({ ok: true });
  }

  const body = (await request.json().catch(() => null)) as {
    password?: string;
  } | null;
  if (!body?.password || body.password !== password) {
    return NextResponse.json({ error: "비밀번호가 틀렸습니다." }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, password, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.VERCEL === "1",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
