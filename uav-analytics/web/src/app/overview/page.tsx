export const dynamic = "force-dynamic";

async function fetchJSON(path: string) {
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const token = process.env.NEXT_PUBLIC_API_TOKEN;
  const res = await fetch(`${base}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default async function OverviewPage() {
  const summary = await fetchJSON(`/metrics/summary`);
  const daily = await fetchJSON(`/metrics/daily`);
  return (
    <main className="max-w-6xl mx-auto p-6 neo-surface">
      <h1 className="text-2xl font-bold mb-4">Overview</h1>
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="neo-card">
          <div className="text-sm text-gray-500">Flights</div>
          <div className="text-2xl font-semibold">{summary.flights_total}</div>
        </div>
        <div className="neo-card">
          <div className="text-sm text-gray-500">Regions</div>
          <div className="text-2xl font-semibold">{summary.regions_count}</div>
        </div>
        <div className="neo-card">
          <div className="text-sm text-gray-500">Top Region</div>
          <div className="text-2xl font-semibold">{summary.top_regions?.[0]?.region || '-'}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="neo-card">
          <h2 className="font-semibold mb-2">Top Regions</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="text-left p-2">Region</th>
                <th className="text-right p-2">Flights</th>
              </tr>
            </thead>
            <tbody>
              {summary.top_regions?.map((r: any) => (
                <tr key={r.region} className="border-t">
                  <td className="p-2">{r.region}</td>
                  <td className="p-2 text-right">{r.flights_cnt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="neo-card">
          <h2 className="font-semibold mb-2">Top Zones</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="text-left p-2">Zone</th>
                <th className="text-right p-2">Flights</th>
              </tr>
            </thead>
            <tbody>
              {summary.top_zones?.map((z: any, i: number) => (
                <tr key={i} className="border-t">
                  <td className="p-2">{z.zone}</td>
                  <td className="p-2 text-right">{z.flights_cnt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="mt-8 neo-card">
        <h2 className="font-semibold mb-2">Daily (first 30)</h2>
        <div className="overflow-auto max-h-96">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="p-2 text-left">Date</th>
                <th className="p-2 text-left">Region</th>
                <th className="p-2 text-right">Flights</th>
              </tr>
            </thead>
            <tbody>
              {daily.slice(0, 30).map((d: any, i: number) => (
                <tr key={i} className="border-t">
                  <td className="p-2">{d.date}</td>
                  <td className="p-2">{d.region}</td>
                  <td className="p-2 text-right">{d.flights_cnt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
