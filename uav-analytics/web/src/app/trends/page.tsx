"use client";

import { useEffect, useMemo, useState } from "react";
import LineChart from "@/components/LineChart";

type DayRow = { date: string; region: string | null; flights_cnt: number };
type FcRow = { date: string; yhat: number; method: string };

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN;

export default function TrendsPage() {
  const [daily, setDaily] = useState<DayRow[]>([]);
  const [region, setRegion] = useState<string>("");
  const [forecast, setForecast] = useState<FcRow[]>([]);
  const [period, setPeriod] = useState<7 | 30 | 90>(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiText, setAiText] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    async function run() {
      try {
        setLoading(true);
        const res = await fetch(`${API}/metrics/daily`, {
          headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {},
          cache: "no-store",
          signal: ctl.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setDaily(data);
      } catch (e: any) {
        if (e.name !== "AbortError") setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
    }
    run();
    return () => ctl.abort();
  }, []);

  const regions = useMemo(() => {
    const s = new Set<string>();
    for (const d of daily) if (d.region) s.add(d.region);
    return Array.from(s).sort();
  }, [daily]);

  useEffect(() => {
    if (!region && regions.length) setRegion(regions[0]);
  }, [regions, region]);

  useEffect(() => {
    const ctl = new AbortController();
    async function run() {
      if (!region) return;
      try {
        const u = new URL(`${API}/forecast`);
        u.searchParams.set("region", region);
        const res = await fetch(u.toString(), {
          headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {},
          signal: ctl.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setForecast(data.items || []);
      } catch (e: any) {
        if (e.name !== "AbortError") setError(e.message || String(e));
      }
    }
    run();
    return () => ctl.abort();
  }, [region]);

  const series = useMemo(() => {
    const fact = daily
      .filter((d) => d.region === region)
      .sort((a, b) => (a.date < b.date ? -1 : 1))
      .slice(-period)
      .map((d) => ({ x: d.date, y: d.flights_cnt }));
    const fc = (forecast || []).map((f) => ({ x: f.date, y: Math.max(0, Math.round(f.yhat)) }));
    return { fact, fc };
  }, [daily, region, forecast, period]);

  // Compute date_from/date_to for the selected region and period
  const range = useMemo(() => {
    const rows = daily
      .filter((d) => d.region === region)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    if (rows.length === 0) return { date_from: undefined as string | undefined, date_to: undefined as string | undefined };
    const date_to = rows[rows.length - 1].date;
    const date_from = rows[Math.max(0, rows.length - period)].date;
    return { date_from, date_to };
  }, [daily, region, period]);

  return (
    <main className="max-w-6xl mx-auto p-6 neo-surface">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Тренды</h1>
        <div className="flex gap-3 items-center">
          <div className="flex gap-2 items-center">
            <label className="text-sm text-gray-600">Регион:</label>
            <select className="neo-card p-2 text-sm" value={region} onChange={(e) => setRegion(e.target.value)}>
              {regions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-1 text-sm">
            {[7, 30, 90].map((p) => (
              <button
                key={p}
                className={`neo-chip ${period === p ? "neo-chip-ok" : ""}`}
                onClick={() => setPeriod(p as 7 | 30 | 90)}
              >
                {p} дн.
              </button>
            ))}
          </div>
          <button
            className="neo-link text-sm"
            onClick={async () => {
              try {
                setAiLoading(true);
                setAiError(null);
                setAiText(null);
                const res = await fetch(`${API}/ai/analyze`, {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
                  },
                  body: JSON.stringify({ region, ...range }),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                setAiText(data.analysis || "");
              } catch (e: any) {
                setAiError(e.message || String(e));
              } finally {
                setAiLoading(false);
              }
            }}
          >
            {aiLoading ? "Анализ…" : "Анализ ИИ"}
          </button>
        </div>
      </div>

      {loading && <div className="text-gray-500">Загрузка…</div>}
      {error && <div className="text-red-600">Ошибка загрузки данных: {error}</div>}

      <div className="neo-card mb-6">
        <h2 className="font-semibold mb-3">Факт + прогноз</h2>
        <LineChart
          series={[
            { name: "Факт", color: "#9ecbff", data: series.fact },
            { name: "Прогноз", color: "#f6c177", dashed: true, data: series.fc },
          ]}
        />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="neo-card">
          <h2 className="font-semibold mb-2">Факт (последние {period} дней)</h2>
          <div className="overflow-auto max-h-[420px]">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-right">Рейсов</th>
                </tr>
              </thead>
              <tbody>
                {daily
                  .filter((d) => d.region === region)
                  .sort((a, b) => (a.date < b.date ? -1 : 1))
                  .slice(-period)
                  .map((d, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-2">{d.date}</td>
                      <td className="p-2 text-right">{d.flights_cnt}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="neo-card">
          <h2 className="font-semibold mb-2">Прогноз (14 дней)</h2>
          <div className="overflow-auto max-h-[420px]">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-right">Прогноз</th>
                  <th className="p-2 text-left">Метод</th>
                </tr>
              </thead>
              <tbody>
                {forecast.map((f, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2">{f.date}</td>
                    <td className="p-2 text-right">{Math.round(f.yhat)}</td>
                    <td className="p-2">{f.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {aiText && (
        <div className="neo-card mt-6">
          <h2 className="font-semibold mb-2">Аналитический отчёт (ИИ)</h2>
          <pre className="whitespace-pre-wrap text-sm text-gray-700">{aiText}</pre>
        </div>
      )}
      {aiError && <div className="text-red-600 mt-3">Ошибка ИИ: {aiError}</div>}
    </main>
  );
}
