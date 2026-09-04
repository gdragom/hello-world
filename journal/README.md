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
| `DEFAULT_RISK_USD` | 1R 달러 (기본 25) |
| `OPENAI_API_KEY` | 선택. 있으면 AI 복기 문구 강화 |
| `JOURNAL_FORCE_DEMO` | `1`이면 항상 데모 |

Legacy aliases `BITGET_API_SECRET` / `BITGET_API_PASSPHRASE` still work.

## Bitget MCP (Cursor)

See [`../docs/BITGET-MCP.md`](../docs/BITGET-MCP.md). LEDGER sync uses `@bitget-ai/bitget-agent-sdk` (UTA v3), the same stack as `@bitget-ai/bitget-agent-mcp`.

## Workflow

1. Closed trades 목록에서 매매 선택
2. 차트에서 IN/OUT 마커·가격선 확인
3. Notion 대신 **진입 근거 / 청산 메모 / 규칙 체크리스트** 작성
4. **규칙 복기** → 프로세스 승·패 구분 (결과와 분리)
5. (선택) **AI 복기** → OpenAI로 코칭 문장 보강

저널/복기 데이터는 `journal/data/*.json`에 저장됩니다.

## Notes

- Official Bitget MCP for Cursor: `@bitget-ai/bitget-agent-mcp` (see `docs/BITGET-MCP.md`).
- LEDGER uses `@bitget-ai/bitget-agent-sdk` for Sync Bitget (UTA v3 history + candles).
- API keys: prefer **read-only** permissions for journaling.
- Chart candles are public; position history is signed.
