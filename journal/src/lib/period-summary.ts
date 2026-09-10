import {
  DEFAULT_CHECKLIST,
  RULE_LABELS,
  STRATEGY_BRIEF,
  computeStats,
  normalizeChecklist,
} from "./rules";
import type {
  ClosedTrade,
  JournalEntry,
  PeriodSummaryResult,
  RuleChecklistState,
} from "./types";

function fmtMoney(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

export function filterTradesByRange(
  trades: ClosedTrade[],
  from: number,
  to: number
): ClosedTrade[] {
  return trades.filter((t) => t.closeTime >= from && t.closeTime <= to);
}

export function resolvePeriodRange(
  range: "week" | "month" | "filtered",
  options?: { month?: string; now?: number }
): { from: number; to: number; rangeLabel: string } {
  const now = options?.now ?? Date.now();
  if (range === "week") {
    const to = now;
    const from = to - 7 * 24 * 60 * 60 * 1000;
    return { from, to, rangeLabel: "최근 7일" };
  }
  if (range === "month") {
    const month = options?.month;
    if (month && /^\d{4}-\d{2}$/.test(month)) {
      const [y, m] = month.split("-").map(Number);
      const from = new Date(y, m - 1, 1).getTime();
      const to = new Date(y, m, 0, 23, 59, 59, 999).getTime();
      return { from, to, rangeLabel: `${y}년 ${m}월` };
    }
    const d = new Date(now);
    const from = new Date(d.getFullYear(), d.getMonth(), 1).getTime();
    const to = now;
    return {
      from,
      to,
      rangeLabel: `${d.getFullYear()}년 ${d.getMonth() + 1}월 (오늘까지)`,
    };
  }
  return { from: 0, to: now, rangeLabel: "선택 구간" };
}

export function buildPeriodSummary(options: {
  trades: ClosedTrade[];
  journals: Record<string, JournalEntry>;
  from: number;
  to: number;
  rangeLabel: string;
}): PeriodSummaryResult {
  const trades = filterTradesByRange(options.trades, options.from, options.to);
  const stats = computeStats(trades);
  const keys = Object.keys(DEFAULT_CHECKLIST) as (keyof RuleChecklistState)[];

  const journaled = trades.filter((t) => {
    const j = options.journals[t.id];
    return j && (j.updatedAt ?? 0) > 0;
  });

  const checklistHits: Record<string, { yes: number; n: number }> = {};
  for (const key of keys) checklistHits[key] = { yes: 0, n: 0 };

  const brokenCount = new Map<string, number>();

  for (const trade of journaled) {
    const checklist = normalizeChecklist(options.journals[trade.id]?.checklist);
    for (const key of keys) {
      checklistHits[key].n += 1;
      if (checklist[key]) checklistHits[key].yes += 1;
      else {
        const label = RULE_LABELS[key];
        brokenCount.set(label, (brokenCount.get(label) ?? 0) + 1);
      }
    }
  }

  const checklistRates = keys.map((key) => ({
    key,
    label: RULE_LABELS[key],
    n: checklistHits[key].n,
    rate: checklistHits[key].n
      ? checklistHits[key].yes / checklistHits[key].n
      : 0,
  }));

  const topBroken = [...brokenCount.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  const longs = trades.filter((t) => t.side === "long");
  const shorts = trades.filter((t) => t.side === "short");

  let biggestWin: PeriodSummaryResult["biggestWin"] = null;
  let biggestLoss: PeriodSummaryResult["biggestLoss"] = null;
  for (const t of trades) {
    if (!biggestWin || t.pnl > biggestWin.pnl) {
      biggestWin = { id: t.id, pnl: t.pnl };
    }
    if (!biggestLoss || t.pnl < biggestLoss.pnl) {
      biggestLoss = { id: t.id, pnl: t.pnl };
    }
  }

  const studyPoints: string[] = [];
  if (trades.length === 0) {
    studyPoints.push("이 구간에 체결이 없습니다. 기간을 바꾸거나 Sync Bitget을 다시 하세요.");
  } else {
    if (journaled.length / trades.length < 0.5) {
      studyPoints.push(
        `저널 작성률 ${pct(journaled.length / Math.max(trades.length, 1))} — 복기 전에 체크리스트부터 채우면 요약 품질이 올라갑니다.`
      );
    }
    for (const row of checklistRates) {
      if (row.n >= 2 && row.rate < 0.5) {
        studyPoints.push(
          `「${row.label}」 준수 ${pct(row.rate)} (${row.n}건) — 다음 주 포커스 규칙으로 고정하세요.`
        );
      }
    }
    if (stats.winRate < 0.4 && stats.count >= 5) {
      studyPoints.push(
        `승률 ${pct(stats.winRate)} · 기대값 ${fmtMoney(stats.expectancy)} — 빈도보다 필터(Aligned / Wait / FVG·OB)를 먼저 점검하세요.`
      );
    }
    if (shorts.length && shorts.reduce((s, t) => s + t.pnl, 0) < -Math.abs(stats.netPnl) * 0.3) {
      studyPoints.push("숏 PnL이 구간 손실을 크게 깎습니다. 숏은 Aligned/MSS만 허용하는 실험을 하세요.");
    }
    if (longs.length && longs.reduce((s, t) => s + t.pnl, 0) > 0 && stats.netPnl < 0) {
      studyPoints.push("롱은 플러스인데 전체는 마이너스 — 숏·과매매 쪽이 계좌를 깎는지 분리 복기하세요.");
    }
    if (biggestLoss && biggestLoss.pnl < -50) {
      studyPoints.push(
        `최대 손실 ${fmtMoney(biggestLoss.pnl)} — 해당 체결의 진입 근거·세션·2R 전 반익절 여부를 차트와 함께 다시 보세요.`
      );
    }
    if (topBroken[0]) {
      studyPoints.push(
        `가장 자주 깨진 규칙: ${topBroken[0].label} (${topBroken[0].count}회). 다음 5매매는 이 항목만 강제 체크하세요.`
      );
    }
    if (studyPoints.length === 0) {
      studyPoints.push("큰 프로세스 구멍은 안 보입니다. 같은 셋업 템플릿을 유지하고 사이즈만 과욕 없이 가세요.");
    }
  }

  const summary =
    trades.length === 0
      ? `${options.rangeLabel}: 복기할 체결이 없습니다.`
      : `${options.rangeLabel}: ${trades.length}건 · WR ${pct(stats.winRate)} · 순손익 ${fmtMoney(stats.netPnl)} · 저널 ${journaled.length}/${trades.length}건. ` +
        (topBroken[0]
          ? `가장 자주 깨진 규칙「${topBroken[0].label}」.`
          : "체크리스트 위반이 두드러지지 않습니다.");

  return {
    rangeLabel: options.rangeLabel,
    from: options.from,
    to: options.to,
    tradeCount: trades.length,
    journaledCount: journaled.length,
    stats,
    longCount: longs.length,
    shortCount: shorts.length,
    longPnl: longs.reduce((s, t) => s + t.pnl, 0),
    shortPnl: shorts.reduce((s, t) => s + t.pnl, 0),
    checklistRates,
    topBroken,
    biggestWin,
    biggestLoss,
    studyPoints: studyPoints.slice(0, 6),
    summary,
    mode: "rules",
    generatedAt: Date.now(),
  };
}

async function aiEnrichPeriod(
  base: PeriodSummaryResult,
  sampleNotes: { tradeId: string; entryReason: string; exitReason: string }[]
): Promise<PeriodSummaryResult> {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return base;

  const prompt = `
당신은 ICT 트레이딩 코치입니다. 주/월 복기용 JSON만 반환하세요.
키: summary(string), studyPoints(string[] 최대 6개).
공부/프로세스 개선에 초점을 두고, PnL 자랑/탓보다 규칙을 말하세요.

전략:
${STRATEGY_BRIEF}

기간 요약(규칙엔진):
${JSON.stringify(base, null, 2)}

샘플 노트:
${JSON.stringify(sampleNotes, null, 2)}
`.trim();

  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL ?? "gpt-4o-mini",
        temperature: 0.3,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content:
              "Return compact Korean study-review JSON. Direct, actionable, no fluff.",
          },
          { role: "user", content: prompt },
        ],
      }),
    });
    if (!res.ok) return base;
    const json = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    const content = json.choices?.[0]?.message?.content;
    if (!content) return base;
    const parsed = JSON.parse(content) as {
      summary?: string;
      studyPoints?: string[];
    };
    return {
      ...base,
      summary: parsed.summary?.trim() || base.summary,
      studyPoints:
        parsed.studyPoints && parsed.studyPoints.length
          ? parsed.studyPoints.slice(0, 6)
          : base.studyPoints,
      mode: "ai",
      generatedAt: Date.now(),
    };
  } catch {
    return base;
  }
}

export async function buildPeriodSummaryWithOptionalAi(options: {
  trades: ClosedTrade[];
  journals: Record<string, JournalEntry>;
  from: number;
  to: number;
  rangeLabel: string;
  useAi?: boolean;
}): Promise<PeriodSummaryResult> {
  const base = buildPeriodSummary(options);
  if (!options.useAi) return base;

  const sampleNotes = options.trades
    .filter((t) => t.closeTime >= options.from && t.closeTime <= options.to)
    .slice(0, 12)
    .map((t) => {
      const j = options.journals[t.id];
      return {
        tradeId: t.id,
        entryReason: j?.entryReason ?? "",
        exitReason: j?.exitReason ?? "",
      };
    })
    .filter((n) => n.entryReason || n.exitReason);

  return aiEnrichPeriod(base, sampleNotes);
}
