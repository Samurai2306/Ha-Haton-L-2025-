export default function Home() {
  const links = [
    { href: "/overview", label: "Overview" },
    { href: "/map", label: "Map" },
    { href: "/trends", label: "Trends" },
    { href: "/about", label: "About" },
  ];
  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-4">UAV Analytics Dashboard</h1>
      <p className="text-gray-600 mb-6">Explore daily metrics, map activity, and short-term forecasts.</p>
      <ul className="grid grid-cols-2 gap-4">
        {links.map((l) => (
          <li key={l.href}>
            <a className="block rounded border p-6 hover:bg-gray-50" href={l.href}>
              <div className="text-lg font-semibold">{l.label}</div>
              <div className="text-sm text-gray-500">/{l.href.replace("/", "")}</div>
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
