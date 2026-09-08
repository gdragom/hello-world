# Cloudflare R2 for LEDGER screenshots

Vercel disk/`/tmp` is ephemeral. Put TradingView screenshots on R2 and store only the URL in the journal.

## Free-tier setup

1. Cloudflare → R2 → Create bucket (e.g. `ledger-shots`)
2. R2 → Manage R2 API Tokens → Create API token (Object Read & Write)
3. Note **Account ID**, **Access Key ID**, **Secret Access Key**
4. Enable public access **or** attach a custom domain / r2.dev public URL
5. Vercel project env:

```env
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=ledger-shots
R2_PUBLIC_BASE_URL=https://pub-xxxxx.r2.dev
```

6. Redeploy

Without R2, `/api/upload` falls back to inline `dataUrl` (fine locally, weak on Vercel).
