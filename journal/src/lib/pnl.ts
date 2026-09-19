import type { ClosedTrade } from "./types";

function pad(n: number) {
  return String(n).padStart(2, "0");
}

export function dayKey(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function monthKey(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

export function monthLabel(key: string): string {
  const [, month] = key.split("-");
  return `${Number(month)}월`;
}

export function recentMonthKeys(count = 3, from = new Date()): string[] {
  const keys: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(from.getFullYear(), from.getMonth() - i, 1);
    keys.push(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`);
  }
  return keys;
}

export function dailyTotals(trades: ClosedTrade[]): Record<string, number> {
  const map: Record<string, number> = {};
  for (const trade of trades) {
    const key = dayKey(trade.closeTime);
    map[key] = (map[key] ?? 0) + trade.pnl;
  }
  return map;
}

export type MonthPoint = {
  key: string;
  label: string;
  pnl: number;
  count: number;
};

export function monthlySeries(trades: ClosedTrade[]): MonthPoint[] {
  const map = new Map<string, MonthPoint>();
  for (const trade of trades) {
    const key = monthKey(trade.closeTime);
    const prev = map.get(key) ?? {
      key,
      label: monthLabel(key),
      pnl: 0,
      count: 0,
    };
    prev.pnl += trade.pnl;
    prev.count += 1;
    map.set(key, prev);
  }
  return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
}

export function filterTrades(
  trades: ClosedTrade[],
  month: string | "all",
  day: string | null
): ClosedTrade[] {
  return trades.filter((trade) => {
    if (day) return dayKey(trade.closeTime) === day;
    if (month !== "all") return monthKey(trade.closeTime) === month;
    return true;
  });
}

export function calendarCells(month: string) {
  const [year, mon] = month.split("-").map(Number);
  const first = new Date(year, mon - 1, 1);
  const startPad = first.getDay();
  const daysInMonth = new Date(year, mon, 0).getDate();
  const cells: Array<{ date: string | null; day: number | null }> = [];
  for (let i = 0; i < startPad; i++) cells.push({ date: null, day: null });
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({
      date: `${year}-${pad(mon)}-${pad(day)}`,
      day,
    });
  }
  while (cells.length % 7 !== 0) cells.push({ date: null, day: null });
  return cells;
}
