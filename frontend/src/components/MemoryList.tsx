"use client";

import { useEffect, useState } from "react";
import { ROVE_API_BASE } from "@/lib/roveApi";

type MemoryItem = { id: number; category: string; content: string };

export function MemoryList() {
  const [items, setItems] = useState<MemoryItem[] | null>(null);

  useEffect(() => {
    fetch(`${ROVE_API_BASE}/api/memories`)
      .then((response) => response.json())
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  const remove = async (id: number) => {
    await fetch(`${ROVE_API_BASE}/api/memories/${id}`, { method: "DELETE" }).catch(() => undefined);
    setItems((prev) => prev?.filter((item) => item.id !== id) ?? null);
  };

  return (
    <div>
      <p className="mb-1 text-sm text-white/80">Memory</p>
      <p className="mb-2 text-sm text-white/40">What Rove remembers between tasks. Remove anything you don&apos;t want kept.</p>
      {items === null ? null : items.length === 0 ? (
        <p className="text-sm text-white/30">Nothing saved yet.</p>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {items.map((item) => (
            <li key={item.id} className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/70">
              <span className="shrink-0 text-xs text-white/40">{item.category}</span>
              <span className="flex-1 break-words">{item.content}</span>
              <button onClick={() => remove(item.id)} aria-label="Remove memory" className="shrink-0 text-white/40 hover:text-white/80">
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
