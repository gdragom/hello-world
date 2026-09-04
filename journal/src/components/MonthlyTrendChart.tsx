"use client";

import type { MonthPoint } from "@/lib/pnl";

type Props = {
  series: MonthPoint[];
};

export function MonthlyTrendChart({ series }: Props) {
  const width = 420;
  const height = 180;
  const pad = { top: 16, right: 12, bottom: 28, left: 40 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  if (!series.length) {
    return (
      <section className="trend-card">
        <p className="eyebrow">Monthly profit</p>
        <h3>월별 프로핏</h3>
        <p className="empty">체결이 생기면 여기에 추세가 그려집니다.</p>
      </section>
    );
  }

  const maxAbs = Math.max(...series.map((s) => Math.abs(s.pnl)), 1);
  const barW = Math.max(18, innerW / series.length - 10);
  const zeroY = pad.top + innerH / 2;
  const points = series.map((s, i) => {
    const x = pad.left + (i + 0.5) * (innerW / series.length);
    const y = zeroY - (s.pnl / maxAbs) * (innerH / 2 - 8);
    return { ...s, x, y };
  });
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  const rising = prev ? last.pnl >= prev.pnl : last.pnl >= 0;

  return (
    <section className="trend-card">
      <header className="calendar-head">
        <div>
          <p className="eyebrow">Monthly profit</p>
          <h3>월별 프로핏 추세</h3>
        </div>
        <strong className={rising ? "up" : "down"}>
          {rising ? "상승" : "하락"}
        </strong>
      </header>
      <svg
        className="trend-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="월별 손익 차트"
      >
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={zeroY}
          y2={zeroY}
          stroke="rgba(243,236,226,0.15)"
        />
        {points.map((p) => {
          const barH = Math.abs(p.y - zeroY);
          const y = p.pnl >= 0 ? p.y : zeroY;
          return (
            <rect
              key={`${p.key}-bar`}
              x={p.x - barW / 2}
              y={y}
              width={barW}
              height={Math.max(barH, 2)}
              rx="4"
              fill={p.pnl >= 0 ? "rgba(61,186,126,0.45)" : "rgba(212,84,60,0.45)"}
            />
          );
        })}
        <polyline
          fill="none"
          stroke="#e8a838"
          strokeWidth="2"
          points={line}
        />
        {points.map((p) => (
          <g key={p.key}>
            <circle cx={p.x} cy={p.y} r="3.5" fill="#e8a838" />
            <text
              x={p.x}
              y={height - 8}
              textAnchor="middle"
              fill="#9e9486"
              fontSize="11"
            >
              {p.label}
            </text>
          </g>
        ))}
      </svg>
      <ul className="trend-legend">
        {series.map((s) => (
          <li key={s.key}>
            <span>{s.label}</span>
            <strong className={s.pnl >= 0 ? "up" : "down"}>
              {s.pnl >= 0 ? "+" : ""}${s.pnl.toFixed(2)}
            </strong>
            <em>{s.count} trades</em>
          </li>
        ))}
      </ul>
    </section>
  );
}
