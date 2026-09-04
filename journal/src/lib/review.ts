import {
  RULE_LABELS,
  STRATEGY_BRIEF,
  estimateR,
  outcomeOf,
} from "./rules";
import type {
  ClosedTrade,
  JournalEntry,
  ReviewResult,
  RuleChecklistState,
} from "./types";

function brokenRules(checklist: RuleChecklistState): string[] {
  return (Object.keys(checklist) as (keyof RuleChecklistState)[])
    .filter((k) => !checklist[k])
    .map((k) => RULE_LABELS[k]);
}

function keptRules(checklist: RuleChecklistState): string[] {
  return (Object.keys(checklist) as (keyof RuleChecklistState)[])
    .filter((k) => checklist[k])
    .map((k) => RULE_LABELS[k]);
}

function rulesBasedReview(
  trade: ClosedTrade,
  journal: JournalEntry,
  riskDollars: number
): ReviewResult {
  const kept = keptRules(journal.checklist);
  const broken = brokenRules(journal.checklist);
  const r = estimateR(trade, riskDollars);
  const outcome = outcomeOf(trade);
  const processScore = kept.length / Object.keys(journal.checklist).length;

  let verdict: ReviewResult["verdict"] = "unclear";
  let summary = "";
  let marketNote = "";
  const suggestions: string[] = [];

  if (processScore >= 0.85 && outcome === "loss") {
    verdict = "process_win";
    summary =
      "프로세스는 대체로 지켰고 결과가 손실입니다. 이 케이스는 ‘틀린 매매’보다 ‘허용된 손실(1R)’에 가깝습니다.";
    marketNote =
      "차트/유동성이 예상과 다르게 움직인 구간으로 분류하세요. 규칙을 바꾼 이유가 되지 않습니다.";
  } else if (processScore >= 0.85 && outcome === "win") {
    verdict = "process_win";
    summary =
      "규칙도 지켰고 결과도 플러스입니다. 이런 셋업의 공통점(세션, MSS 위치, CISD 품질)을 템플릿화하세요.";
    marketNote = "엣지가 발현된 케이스입니다. 사이즈/청산만 과욕 없이 유지하면 됩니다.";
  } else if (processScore < 0.6 && outcome === "win") {
    verdict = "mixed";
    summary =
      "돈은 벌었지만 프로세스 위반이 있습니다. 이런 승리는 장기적으로 계좌를 망가뜨리는 ‘나쁜 습관 강화’입니다.";
    marketNote =
      "결과로 규칙을 정당화하지 마세요. 같은 위반이 손실로 이어지면 기대값이 무너집니다.";
    suggestions.push("승리여도 위반 항목을 다음 주 리뷰 카드에 고정하세요.");
  } else if (processScore < 0.6) {
    verdict = "process_loss";
    summary =
      "결과와 별개로 핵심 규칙을 충분히 지키지 못했습니다. 복기의 초점은 PnL이 아니라 위반 항목입니다.";
    marketNote =
      "시장 탓으로 넘기기 전에, 진입 필터(2R 경로/세션/CISD)부터 다시 점검하세요.";
  } else {
    verdict = "mixed";
    summary =
      "일부 규칙은 지켰고 일부는 빠졌습니다. ‘거의 지킴’ 상태가 0수렴의 전형적인 원인입니다.";
    marketNote = "애매한 셋업은 스킵 비율을 높이는 쪽이 챌린지 계좌에 유리합니다.";
  }

  if (!journal.checklist.noEarlyPartialBefore2R) {
    suggestions.push(
      "2R 전 반익절을 했다면, 다음부터는 TP1을 손절 거리 ×2에만 두세요."
    );
  }
  if (!journal.checklist.targetAtLeast2R) {
    suggestions.push("진입 전 ‘2R까지 길이’가 없으면 패스 규칙을 강제하세요.");
  }
  if (!journal.checklist.sessionOk) {
    suggestions.push("아시아 세션 체결이 섞였는지 시간을 확인하세요.");
  }
  if (r !== null && r > 0 && r < 1.2 && outcome === "win") {
    suggestions.push(
      `이번 승은 약 ${r.toFixed(2)}R입니다. 목표(≥1.5~2R)보다 짧으면 손익비가 다시 1:1로 수렴합니다.`
    );
  }
  if (r !== null && r <= -0.9 && r >= -1.2) {
    suggestions.push("손실 크기가 1R 근처면 리스크 관리 자체는 정상입니다.");
  }
  if (!journal.entryReason.trim()) {
    suggestions.push("진입 근거를 한 줄이라도 남기면 주간 AI 복기 품질이 올라갑니다.");
  }

  return {
    tradeId: trade.id,
    verdict,
    summary,
    kept,
    broken,
    marketNote,
    suggestions,
    estimatedR: r,
    generatedAt: Date.now(),
    mode: "rules",
  };
}

async function aiEnrich(
  base: ReviewResult,
  trade: ClosedTrade,
  journal: JournalEntry
): Promise<ReviewResult> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return base;

  const prompt = `
당신은 ICT 트레이딩 코치입니다. 아래 전략 규칙과 실제 매매/노트를 비교해
JSON만 반환하세요. 키: summary, marketNote, suggestions(string[]), verdict
(verdict는 process_win|process_loss|mixed|unclear).

전략:
${STRATEGY_BRIEF}

매매:
${JSON.stringify(trade, null, 2)}

저널:
${JSON.stringify(journal, null, 2)}

규칙엔진 초안:
${JSON.stringify(base, null, 2)}
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
        temperature: 0.2,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content:
              "Return compact Korean coaching JSON. Be direct. Distinguish process error vs adverse market.",
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
    const parsed = JSON.parse(content) as Partial<ReviewResult>;

    return {
      ...base,
      summary: parsed.summary || base.summary,
      marketNote: parsed.marketNote || base.marketNote,
      suggestions:
        parsed.suggestions && parsed.suggestions.length
          ? parsed.suggestions
          : base.suggestions,
      verdict: parsed.verdict || base.verdict,
      mode: "ai",
      generatedAt: Date.now(),
    };
  } catch {
    return base;
  }
}

export async function buildReview(options: {
  trade: ClosedTrade;
  journal: JournalEntry;
  riskDollars?: number;
  useAi?: boolean;
}): Promise<ReviewResult> {
  const risk = options.riskDollars ?? Number(process.env.DEFAULT_RISK_USD ?? 25);
  const base = rulesBasedReview(options.trade, options.journal, risk);
  if (options.useAi === false) return base;
  return aiEnrich(base, options.trade, options.journal);
}
