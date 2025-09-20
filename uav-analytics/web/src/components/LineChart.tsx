"use client";

type Point = { x: string | Date; y: number | null };
type Series = { name: string; color: string; dashed?: boolean; data: Point[] };

function toDate(x: string | Date): Date {
  return x instanceof Date ? x : new Date(x);
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function LineChart({
  series,
  height = 220,
  padding = { top: 16, right: 16, bottom: 28, left: 44 },
}: {
  series: Series[];
  height?: number;
  padding?: { top: number; right: number; bottom: number; left: number };
}) {
  const allPoints = series.flatMap((s) => s.data);
  if (allPoints.length === 0) return <div className="text-gray-600">Нет данных для графика.</div>;

  // Compute domains
  const dates = allPoints.map((p) => toDate(p.x)).filter((d) => !isNaN(d.getTime()));
  const xs = dates.map((d) => d.getTime());
  const ys = allPoints.map((p) => (p.y ?? 0));
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMax = Math.max(1, Math.ceil(Math.max(...ys) * 1.1));

  const width = 800; // viewBox width; scaled by CSS
  const vb = { w: width, h: height };
  const pad = padding;
  const innerW = vb.w - pad.left - pad.right;
  const innerH = vb.h - pad.top - pad.bottom;

  const xScale = (t: number) => pad.left + ((t - xMin) / (xMax - xMin || 1)) * innerW;
  const yScale = (v: number) => pad.top + innerH - (v / (yMax || 1)) * innerH;

  function pathFor(points: Point[]): string {
    const pts = points
      .filter((p) => p.y !== null && p.y !== undefined)
      .map((p) => ({ x: xScale(toDate(p.x).getTime()), y: yScale(p.y as number) }))
      .sort((a, b) => a.x - b.x);
    if (pts.length === 0) return "";
    return "M " + pts.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" L ");
  }

  // Build simple x-axis ticks (max 8)
  const tickCount = Math.min(8, Math.max(2, Math.floor(innerW / 100)));
  const ticks: { x: number; label: string }[] = [];
  for (let i = 0; i < tickCount; i++) {
    const t = xMin + (i / (tickCount - 1)) * (xMax - xMin);
    const d = new Date(t);
    ticks.push({ x: xScale(t), label: formatDate(d) });
  }

  // y-axis ticks (4)
  const yTicks: { y: number; label: string }[] = [];
  const yTickCount = 4;
  for (let i = 0; i <= yTickCount; i++) {
    const v = (i / yTickCount) * yMax;
    yTicks.push({ y: yScale(v), label: Math.round(v).toString() });
  }

  return (
    <div className="neo-card" style={{ padding: 0 }}>
      <svg viewBox={`0 0 ${vb.w} ${vb.h}`} width="100%" height={vb.h}>
        {/* Axes */}
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={pad.top + innerH} stroke="#3a4655" />
        <line x1={pad.left} y1={pad.top + innerH} x2={pad.left + innerW} y2={pad.top + innerH} stroke="#3a4655" />

        {/* Y ticks and labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pad.left - 4} y1={t.y} x2={pad.left} y2={t.y} stroke="#3a4655" />
            <text x={pad.left - 8} y={t.y + 4} fontSize={10} fill="#aeb7c4" textAnchor="end">
              {t.label}
            </text>
            <line x1={pad.left} y1={t.y} x2={pad.left + innerW} y2={t.y} stroke="#1a222e" opacity={0.4} />
          </g>
        ))}

        {/* X ticks and labels */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={t.x} y1={pad.top + innerH} x2={t.x} y2={pad.top + innerH + 4} stroke="#3a4655" />
            <text x={t.x} y={pad.top + innerH + 16} fontSize={10} fill="#aeb7c4" textAnchor="middle">
              {t.label}
            </text>
          </g>
        ))}

        {/* Series */}
        {series.map((s, idx) => (
          <path
            key={idx}
            d={pathFor(s.data)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "6,4" : undefined}
          />
        ))}
      </svg>
      {/* Legend */}
      <div className="flex gap-4 p-3">
        {series.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
            <span
              style={{
                width: 20,
                height: 2,
                background: s.color,
                display: "inline-block",
                borderBottom: s.dashed ? "2px dashed " + s.color : undefined,
              }}
            />
            <span>{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

