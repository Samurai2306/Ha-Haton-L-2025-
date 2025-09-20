"use client";

import { useState } from "react";

export type Filters = {
  date_from?: string;
  date_to?: string;
  region?: string;
  zone?: string;
  altitude_category?: string;
};

export default function FilterBar({ value, onChange }: { value?: Filters; onChange: (f: Filters) => void }) {
  const [f, setF] = useState<Filters>(value || {});

  function set<K extends keyof Filters>(k: K, v: Filters[K]) {
    const nv = { ...f, [k]: v };
    setF(nv);
    onChange(nv);
  }

  return (
    <div className="neo-card flex flex-wrap gap-3 items-end">
      <div>
        <label className="block text-xs text-gray-600 mb-1">Дата с</label>
        <input className="neo-card p-2" type="date" value={f.date_from || ""} onChange={(e) => set("date_from", e.target.value || undefined)} />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Дата по</label>
        <input className="neo-card p-2" type="date" value={f.date_to || ""} onChange={(e) => set("date_to", e.target.value || undefined)} />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Регион</label>
        <input className="neo-card p-2" type="text" placeholder="точное имя" value={f.region || ""} onChange={(e) => set("region", e.target.value || undefined)} />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Зона</label>
        <input className="neo-card p-2" type="text" value={f.zone || ""} onChange={(e) => set("zone", e.target.value || undefined)} />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Высота</label>
        <select className="neo-card p-2" value={f.altitude_category || ""} onChange={(e) => set("altitude_category", (e.target.value || undefined) as any)}>
          <option value="">—</option>
          <option value="LOW">LOW</option>
          <option value="MID">MID</option>
          <option value="HIGH">HIGH</option>
        </select>
      </div>
      <div className="ml-auto text-sm text-gray-600">Фильтры применяются мгновенно</div>
    </div>
  );
}

