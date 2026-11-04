import { buildAlertMessage } from "./alert-message";
import type { ExecResult } from "./bitget-exec";
import type { SetupAlert } from "./types";

export async function notifyTelegram(
  alert: SetupAlert,
  exec?: ExecResult
): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_CHAT_ID?.trim();
  if (!token || !chatId) return false;

  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: buildAlertMessage(alert, exec),
      disable_web_page_preview: true,
    }),
  });

  return res.ok;
}
