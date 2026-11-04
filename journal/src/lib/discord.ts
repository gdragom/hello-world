import { alertEmbedColor, buildAlertMessage } from "./alert-message";
import type { ExecResult } from "./bitget-exec";
import type { SetupAlert } from "./types";

function isDiscordWebhookUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return (
      (u.hostname === "discord.com" || u.hostname === "discordapp.com") &&
      u.pathname.includes("/api/webhooks/")
    );
  } catch {
    return false;
  }
}

/** Post TV alert to a Discord channel webhook (DISCORD_WEBHOOK_URL). */
export async function notifyDiscord(
  alert: SetupAlert,
  exec?: ExecResult
): Promise<boolean> {
  const url = process.env.DISCORD_WEBHOOK_URL?.trim();
  if (!url || !isDiscordWebhookUrl(url)) return false;

  const content = buildAlertMessage(alert, exec);
  const title =
    alert.stage === "SETUP_ARMED"
      ? "SETUP_ARMED"
      : alert.stage === "ENTRY_READY"
        ? "ENTRY_READY"
        : "INVALID";

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "LEDGER",
      embeds: [
        {
          title: `LEDGER · ${title}`,
          description: content.slice(0, 4000),
          color: alertEmbedColor(alert),
          timestamp: new Date(alert.createdAt || Date.now()).toISOString(),
        },
      ],
    }),
  });

  return res.ok;
}
