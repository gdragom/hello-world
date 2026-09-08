# LEDGER — BTC ICT Trading Journal

Bitget 선물 체결을 불러와 진입/청산을 차트에 표시하고, ICT 규칙 체크리스트 + 규칙엔진/AI로 복기하는 로컬 대시보드입니다.

## Quick start

```bash
cd journal
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

- **Demo**: API 키 없이 샘플 BTC 체결 + 합성 캔들
- **Sync Bitget**: `.env.local`에 키를 넣은 뒤 버튼 클릭

## Env

| Key | Purpose |
|-----|---------|
| `BITGET_API_KEY` / `BITGET_SECRET_KEY` / `BITGET_PASSPHRASE` | Same as official Bitget MCP |
| `DEFAULT_RISK_USD` | legacy / fallback |
| `OPENAI_API_KEY` | 선택. AI 복기 |
| `JOURNAL_FORCE_DEMO` | `1`이면 항상 데모 |
| `SITE_PASSWORD` | Vercel 접속 잠금 |
| `TV_WEBHOOK_SECRET` | TradingView webhook 인증 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 셋업 푸시 |
| `R2_*` | 스크린샷 영구 저장 (see R2 doc) |

Legacy aliases `BITGET_API_SECRET` / `BITGET_API_PASSPHRASE` still work.

## Bitget MCP (Cursor)

See [`../docs/BITGET-MCP.md`](../docs/BITGET-MCP.md). LEDGER sync uses `@bitget-ai/bitget-agent-sdk` (UTA v3), the same stack as `@bitget-ai/bitget-agent-mcp`.

## Workflow

1. Closed trades 목록에서 매매 선택
2. 차트에서 IN/OUT 마커·가격선 확인
3. Notion 대신 **진입 근거 / 청산 메모 / 규칙 체크리스트** 작성
4. **규칙 복기** → 프로세스 승·패 구분 (결과와 분리)
5. (선택) **AI 복기** → OpenAI로 코칭 문장 보강

저널/복기 데이터는 로컬에서 `journal/data/*.json`에 저장됩니다. Vercel `/tmp`는 임시입니다. 스크린샷은 [Cloudflare R2](../docs/R2-STORAGE.md)를 권장합니다.

## TradingView alerts

장중 알림은 Bitget이 아니라 **TradingView webhook** → `/api/tv-webhook` → 대시보드 + (선택) Telegram.

See [`../docs/TV-WEBHOOK.md`](../docs/TV-WEBHOOK.md).

Stages: `SETUP_ARMED` (1H) → `ENTRY_READY` (5m) → optional `INVALID`.

## Vercel

`journal/`을 루트로 배포하고 환경 변수에 Bitget 키, `SITE_PASSWORD`, (선택) `TV_WEBHOOK_SECRET` / Telegram / R2를 넣습니다.

### CI/CD (GitHub Actions)

`.github/workflows/deploy-journal.yml`이 `journal/**` 변경을 푸시하면 [ledger-ict-journal.vercel.app](https://ledger-ict-journal.vercel.app)에 자동 배포합니다. PR은 preview입니다.

1. [Vercel token](https://vercel.com/account/tokens)을 만듭니다.
2. GitHub 저장소 **Settings → Secrets and variables → Actions**에 `VERCEL_TOKEN`을 추가합니다.
3. 이 워크플로 파일을 포함한 커밋을 푸시합니다.

## Notes

- Official Bitget MCP for Cursor: `@bitget-ai/bitget-agent-mcp` (see `docs/BITGET-MCP.md`).
- LEDGER uses `@bitget-ai/bitget-agent-sdk` for Sync Bitget (UTA v3 history + candles).
- API keys: prefer **read-only** permissions for journaling.
- Chart candles are public; position history is signed.
