export default function Home() {
  const links = [
    { href: "/overview", label: "Обзор", desc: "KPI, топ‑регионы, факт + прогноз" },
    { href: "/map", label: "Карта", desc: "Точки/координаты и сводка" },
    { href: "/trends", label: "Тренды", desc: "Временные ряды и прогноз 14 дн." },
    { href: "/about", label: "О системе", desc: "Эндпоинты API и проверка" },
  ];
  return (
    <main className="max-w-5xl mx-auto p-8 neo-surface">
      <h1 className="text-3xl font-bold mb-2">UAV Analytics — дашборд</h1>
      <p className="text-gray-600 mb-6">Метрики, карта активности и краткосрочный прогноз.</p>
      <ul className="grid grid-cols-2 gap-4">
        {links.map((l) => (
          <li key={l.href}>
            <a className="neo-card block p-6" href={l.href}>
              <div className="text-lg font-semibold">{l.label}</div>
              <div className="text-sm text-gray-600">{l.desc}</div>
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
