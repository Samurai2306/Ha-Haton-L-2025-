"use client";

import { useEffect, useMemo, useState } from "react";
import LineChart from "@/components/LineChart";
import FilterBar, { type Filters } from "@/components/FilterBar";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN;

function qs(f: Filters): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) u.set(k, String(v));
  return u.toString() ? `?${u.toString()}` : "";
}

export default function OverviewPage() {
  const [filters, setFilters] = useState<Filters>({});
  const [overview, setOverview] = useState<any | null>(null);
  const [ts, setTs] = useState<{ items: any[]; forecast: any[] }>({ items: [], forecast: [] });
  const [error, setError] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiText, setAiText] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    async function run() {
      try {
        setError(null);
        const h = TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
        const [ovr, tss] = await Promise.all([
          fetch(`${API}/metrics/overview${qs(filters)}`, { headers: h, cache: "no-store", signal: ctl.signal }).then((r) => r.json()),
          fetch(`${API}/metrics/timeseries${qs(filters)}`, { headers: h, cache: "no-store", signal: ctl.signal }).then((r) => r.json()),
        ]);
        setOverview(ovr || null);
        setTs({
          items: Array.isArray(tss?.items) ? tss.items : [],
          forecast: Array.isArray(tss?.forecast) ? tss.forecast : [],
        });
      } catch (e: any) {
        if (e.name !== "AbortError") setError(e.message || String(e));
      }
    }
    run();
    return () => ctl.abort();
  }, [filters]);

  const factSeries = useMemo(() => (Array.isArray(ts?.items) ? ts.items : []).map((d) => ({ x: d.date, y: d.flights_cnt })), [ts]);
  const forecastSeries = useMemo(() => (Array.isArray(ts?.forecast) ? ts.forecast : []).map((f) => ({ x: f.date, y: f.yhat })), [ts]);

  return (
    <main className="max-w-6xl mx-auto p-6 neo-surface">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Обзор</h1>
        <div className="flex gap-3">
          <a className="neo-link text-sm" href={`${API}/export.csv${qs(filters)}`} target="_blank" rel="noreferrer">
            Экспорт CSV
          </a>
          <a className="neo-link text-sm" href={`${API}/export.pdf${qs(filters)}`} target="_blank" rel="noreferrer">
            Экспорт PDF
          </a>
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
                  body: JSON.stringify(filters || {}),
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

      <FilterBar value={filters} onChange={setFilters} />

      {error && <div className="text-red-600 mt-3">Ошибка: {error}</div>}

      {overview && (
        <>
          <div className="grid grid-cols-4 gap-4 my-6">
            <div className="neo-card">
              <div className="text-sm text-gray-500">Полётов (всего)</div>
              <div className="text-2xl font-semibold">{overview.flights_total}</div>
            </div>
            <div className="neo-card">
              <div className="text-sm text-gray-500">Регионов</div>
              <div className="text-2xl font-semibold">{overview.regions_count}</div>
            </div>
            <div className="neo-card">
              <div className="text-sm text-gray-500">DoD</div>
              <div className="text-2xl font-semibold">{overview.deltas?.dod_pct == null ? "—" : `${overview.deltas.dod_pct}%`}</div>
            </div>
            <div className="neo-card">
              <div className="text-sm text-gray-500">WoW</div>
              <div className="text-2xl font-semibold">{overview.deltas?.wow_pct == null ? "—" : `${overview.deltas.wow_pct}%`}</div>
            </div>
          </div>

          <div className="neo-card mb-6">
            <h2 className="font-semibold mb-3">Динамика: факт + прогноз</h2>
            <LineChart
              series={[
                { name: "Факт", color: "#9ecbff", data: factSeries },
                { name: "Прогноз", color: "#f6c177", dashed: true, data: forecastSeries },
              ]}
            />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="neo-card">
              <h2 className="font-semibold mb-2">ТОП‑регионы</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left p-2">Регион</th>
                    <th className="text-right p-2">Полётов</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.top_regions?.map((r: any) => (
                    <tr key={r.region} className="border-t">
                      <td className="p-2">{r.region}</td>
                      <td className="p-2 text-right">{r.flights_cnt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="neo-card">
              <h2 className="font-semibold mb-2">ТОП‑зоны</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left p-2">Зона</th>
                    <th className="text-right p-2">Полётов</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.top_zones?.map((z: any, i: number) => (
                    <tr key={i} className="border-t">
                      <td className="p-2">{z.zone}</td>
                      <td className="p-2 text-right">{z.flights_cnt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {overview.altitude_distribution?.length > 0 && (
            <div className="neo-card mt-6">
              <h2 className="font-semibold mb-2">Распределение по высоте</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left p-2">Категория</th>
                    <th className="text-right p-2">Полётов</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.altitude_distribution.map((a: any) => (
                    <tr key={a.altitude_category} className="border-t">
                      <td className="p-2">{a.altitude_category}</td>
                      <td className="p-2 text-right">{a.flights_cnt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {aiText && (
            <div className="neo-card mt-6">
              <h2 className="font-semibold mb-2">Аналитический отчёт (ИИ)</h2>
              <pre className="whitespace-pre-wrap text-sm text-gray-700">{aiText}</pre>
            </div>
          )}
          {aiError && <div className="text-red-600 mt-3">Ошибка ИИ: {aiError}</div>}
        </>
      )}
    </main>
  );
}
