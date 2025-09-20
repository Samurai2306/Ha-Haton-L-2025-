"use client";

import { useEffect, useState } from "react";

export default function AboutPage() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const hasToken = Boolean(process.env.NEXT_PUBLIC_API_TOKEN);
  const [health, setHealth] = useState<{ status?: string; version?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    (async () => {
      try {
        setError(null);
        const res = await fetch(`${apiBase}/health`, {
          cache: "no-store",
          signal: ctl.signal,
          headers: hasToken && process.env.NEXT_PUBLIC_API_TOKEN
            ? { Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_TOKEN}` }
            : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setHealth(data);
      } catch (e: any) {
        if (e.name !== "AbortError") setError(e.message || String(e));
      }
    })();
    return () => ctl.abort();
  }, [apiBase, hasToken]);

  const endpoints = [
    { href: "/metrics/daily", label: "GET /metrics/daily" },
    { href: "/metrics/summary", label: "GET /metrics/summary" },
    { href: "/flights?limit=10", label: "GET /flights" },
    { href: "/forecast?region=REGION", label: "GET /forecast" },
    { href: "/export.csv", label: "GET /export.csv" },
    { href: "/export.pdf", label: "GET /export.pdf" },
  ];

  return (
    <main className="max-w-5xl mx-auto p-8 neo-surface">
      <h1 className="text-3xl font-bold mb-6">О сервисе</h1>

      <div className="grid md:grid-cols-2 gap-6 mb-6">
        <div className="neo-card">
          <div className="text-sm text-gray-600 mb-1">API базовый URL</div>
          <div className="text-lg font-semibold break-all">{apiBase}</div>
          <div className="mt-3 flex items-center gap-3">
            <span className={`neo-chip ${hasToken ? "neo-chip-ok" : ""}`}>
              {hasToken ? "TOKEN: задан" : "TOKEN: не задан"}
            </span>
            {health?.status === "ok" ? (
              <span className="neo-chip neo-chip-ok">HEALTH: ok</span>
            ) : (
              <span className="neo-chip">HEALTH: неизвестно</span>
            )}
          </div>
          {error && <div className="mt-3 text-red-600">Ошибка: {error}</div>}
          {health?.version && (
            <div className="mt-2 text-sm text-gray-600">Версия: {health.version}</div>
          )}
        </div>

        <div className="neo-card">
          <div className="text-sm text-gray-600 mb-2">Эндпоинты</div>
          <ul className="space-y-2">
            {endpoints.map((e) => (
              <li key={e.href}>
                <a
                  className="neo-link"
                  href={`${apiBase}${e.href}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {e.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="neo-card">
        <h2 className="text-xl font-semibold mb-3">Как подключиться из браузера</h2>
        <ol className="list-decimal pl-5 space-y-2 text-gray-700">
          <li>
            В терминале перед запуском веба задайте:{" "}
            <code className="neo-code">NEXT_PUBLIC_API_BASE</code>{" "}
            (и при необходимости <code className="neo-code">NEXT_PUBLIC_API_TOKEN</code>).
          </li>
          <li>
            Запустите веб: <code className="neo-code">npm run dev</code>, откройте странички
            <code className="neo-code">/overview</code>, <code className="neo-code">/map</code>,
            <code className="neo-code">/trends</code>.
          </li>
          <li>
            Для прямой проверки API используйте ссылки выше или curl.
          </li>
        </ol>
      </div>
    </main>
  );
}

