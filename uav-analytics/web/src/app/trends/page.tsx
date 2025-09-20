"use client";

import { useEffect, useMemo, useState } from "react";

type DayRow = {
  date: string;
  region: string | null;
  flights_cnt: number;
};
type FcRow = { date: string; yhat: number; method: string };

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN;

export default function TrendsPage() {
  const [daily, setDaily] = useState<DayRow[]>([]);
  const [region, setRegion] = useState<string>("");
  const [forecast, setForecast] = useState<FcRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load daily
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
    const arr = Array.from(s).sort();
    return arr;
  }, [daily]);

  // default region
  useEffect(() => {
    if (!region && regions.length) setRegion(regions[0]);
  }, [regions, region]);

  // Load forecast for region
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
      .slice(-60);
    return { fact, forecast };
  }, [daily, region, forecast]);

  return (
    <main className="max-w-6xl mx-auto p-6 neo-surface">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Trends</h1>
        <div className="flex gap-2 items-center">
          <label className="text-sm text-gray-600">Регион:</label>
          <select
            className="neo-card p-2 text-sm"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="text-gray-500">Загрузка…</div>}
      {error && (
        <div className="text-red-600">Ошибка загрузки данных: {error}</div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="neo-card">
          <h2 className="font-semibold mb-2">Факт (последние 60 дней)</h2>
          <div className="overflow-auto max-h-[420px]">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-right">Рейсов</th>
                </tr>
              </thead>
              <tbody>
                {series.fact.map((d, i) => (
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
                {series.forecast.map((f, i) => (
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
    </main>
  );
}
