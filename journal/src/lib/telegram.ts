import type { SetupAlert } from "./types";

export async function notifyTelegram(alert: SetupAlert): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_CHAT_ID?.trim();
  if (!token || !chatId) return false;

  const stageLabel =
    alert.stage === "SETUP_ARMED"
      ? "1H 셋업 열림"
      : alert.stage === "ENTRY_READY"
        ? "5m 진입 후보"
        : "셋업 만료";

  const lines = [
    `LEDGER · ${stageLabel}`,
    `${alert.symbol} ${alert.side.toUpperCase()} · ${alert.timeframe}`,
    alert.price != null ? `price ${alert.price}` : null,
    alert.message || null,
  ].filter(Boolean);

  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: lines.join("\n"),
      disable_web_page_preview: true,
    }),
  });

  return res.ok;
}
