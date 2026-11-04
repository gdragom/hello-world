# Cloudflare R2 for LEDGER screenshots + durable journal JSON

Vercel `/tmp` is ephemeral. Screenshots and journal/reviews/alerts/period notes go to R2.

## Free-tier setup (shots)

1. Cloudflare → R2 → Create bucket (e.g. `ledger-shots`) — enable **Public development URL**
2. R2 → Manage R2 API Tokens → Create API token (Object Read & Write)
3. Note **Account ID**, **Access Key ID**, **Secret Access Key**
4. Vercel env:

```env
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=ledger-shots
R2_PUBLIC_BASE_URL=https://pub-xxxxx.r2.dev
```

## Private data bucket (recommended)

If `ledger-shots` is public, journal JSON would also be guessable via `pub-…/app-data/journal.json`.

1. Create a second bucket `ledger-data` — **do not** enable public access  
2. Same API token must cover both buckets (or account-wide R2 write)  
3. Add:

```env
R2_DATA_BUCKET=ledger-data
```

App writes `app-data/journal.json`, `reviews.json`, `periods.json`, `alerts.json` there via signed S3 API only.

Without `R2_DATA_BUCKET`, data uses `R2_BUCKET` (same as shots).

## Billing / free tier

- Free: ~10 GB storage, Class A/B ops allowances, **egress free**
- Card on file: free allowance still applies; **overage bills automatically**
- Cloudflare has **budget alerts** (email), not a hard spend cap — usage does not auto-stop
- Personal journal + ~1k screenshots stays well under 10 GB

Set alerts: Manage Account → Billing → Billable Usage → Budget alerts (e.g. $1 / $5).

Redeploy after env changes.

Without R2, `/api/upload` falls back to inline `dataUrl` and stores use local/`/tmp`.
