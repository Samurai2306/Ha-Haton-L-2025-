"use client";

import { useEffect, useMemo, useState } from "react";

type Flight = {
  date: string;
  region: string | null;
  dep_lat?: number | null;
  dep_lon?: number | null;
  arr_lat?: number | null;
  arr_lon?: number | null;
  dep_point?: string | null;
  arr_point?: string | null;
  zone?: string | null;
  duration_min?: number | null;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN;

export default function MapPage() {
  const [items, setItems] = useState<Flight[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState<string>("");

  useEffect(() => {
    const ctl = new AbortController();
    async function run() {
      try {
        setLoading(true);
        setError(null);
        const qs = new URLSearchParams({ limit: "1000" });
        if (region) qs.set("region", region);
        const res = await fetch(`${API}/flights?${qs.toString()}`, {
          headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {},
          signal: ctl.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setItems(data.items || []);
      } catch (e: any) {
        if (e.name !== "AbortError") setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
    }
    run();
    return () => ctl.abort();
  }, [region]);

  const withCoords = useMemo(
    () =>
      items.filter(
        (f) =>
          (typeof f.dep_lat === "number" && typeof f.dep_lon === "number") ||
          (typeof f.arr_lat === "number" && typeof f.arr_lon === "number")
      ),
    [items]
  );

  const regions = useMemo(() => {
    const s = new Set<string>();
    for (const f of items) if (f.region) s.add(f.region);
    return Array.from(s).sort();
  }, [items]);

  return (
    <main className="max-w-6xl mx-auto p-6 neo-surface">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Карта</h1>
        <div className="flex gap-2 items-center">
          <label className="text-sm text-gray-600">Регион:</label>
          <select
            className="neo-card p-2 text-sm"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            <option value="">Все</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="text-gray-500 neo-card inline-block px-3 py-2">Загрузка…</div>}
      {error && (
        <div className="text-red-600">Ошибка загрузки данных: {error}</div>
      )}

      <div className="mb-6 neo-card">
        <h2 className="font-semibold mb-2">Точки с координатами (до 1000 записей)</h2>
        {withCoords.length === 0 ? (
          <div className="text-gray-600">
            Координаты не найдены. Это нормально, если входные данные содержат мало координат. Карта
            (Leaflet) будет подключена, как только появятся координаты.
          </div>
        ) : (
          <div className="overflow-auto max-h-[480px]">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-left">Регион</th>
                  <th className="p-2 text-left">DEP (lat, lon)</th>
                  <th className="p-2 text-left">ARR (lat, lon)</th>
                  <th className="p-2 text-left">Zone</th>
                </tr>
              </thead>
              <tbody>
                {withCoords.slice(0, 500).map((f, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2">{f.date}</td>
                    <td className="p-2">{f.region}</td>
                    <td className="p-2">
                      {typeof f.dep_lat === "number" && typeof f.dep_lon === "number"
                        ? `${f.dep_lat.toFixed(4)}, ${f.dep_lon.toFixed(4)}`
                        : "—"}
                    </td>
                    <td className="p-2">
                      {typeof f.arr_lat === "number" && typeof f.arr_lon === "number"
                        ? `${f.arr_lat.toFixed(4)}, ${f.arr_lon.toFixed(4)}`
                        : "—"}
                    </td>
                    <td className="p-2">{f.zone || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="neo-card">
        <h2 className="font-semibold mb-2">Сводка по регионам (по загруженным точкам)</h2>
        <div className="text-sm text-gray-600 mb-2">Это агрегирование на клиенте по полученным записям.</div>
        <RegionSummary items={items} />
      </div>
    </main>
  );
}

function RegionSummary({ items }: { items: Flight[] }) {
  const byRegion = useMemo(() => {
    const m = new Map<string, number>();
    for (const f of items) {
      const key = f.region || "—";
      m.set(key, (m.get(key) || 0) + 1);
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [items]);

  if (byRegion.length === 0) return <div className="text-gray-600">Нет данных.</div>;

  return (
    <div className="overflow-auto max-h-[360px] border rounded">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 sticky top-0">
          <tr>
            <th className="p-2 text-left">Регион</th>
            <th className="p-2 text-right">Количество записей</th>
          </tr>
        </thead>
        <tbody>
          {byRegion.map(([r, cnt]) => (
            <tr key={r} className="border-t">
              <td className="p-2">{r}</td>
              <td className="p-2 text-right">{cnt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
