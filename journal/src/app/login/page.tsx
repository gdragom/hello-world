"use client";

import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json.error || "로그인 실패");
      }
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <form className="login-card" onSubmit={onSubmit}>
        <p className="brand">LEDGER</p>
        <h1>접속 비밀번호</h1>
        <p className="lede">
          공개 URL에서 Bitget 동기화를 막기 위해 비밀번호가 필요합니다.
        </p>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="accent" disabled={busy || !password}>
          {busy ? "확인 중…" : "들어가기"}
        </button>
        {error ? <p className="status">{error}</p> : null}
      </form>
    </div>
  );
}
