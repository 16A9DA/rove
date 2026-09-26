"use client";

import { useEffect, useState } from "react";
import { ROVE_API_BASE } from "@/lib/roveApi";

type Provider = "anthropic" | "openai";

type AppSettings = {
  provider: Provider;
  model: string | null;
  has_anthropic_key: boolean;
  has_openai_key: boolean;
};

type ModelInfo = { id: string; display_name: string };

const PROVIDER_LABEL: Record<Provider, string> = { anthropic: "Claude (Anthropic)", openai: "ChatGPT (OpenAI)" };

export function Settings({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    fetch(`${ROVE_API_BASE}/api/settings`)
      .then((res) => res.json())
      .then((data: AppSettings) => {
        setSettings(data);
        setProvider(data.provider);
        setModel(data.model ?? "");
      })
      .catch(() => setSaveState("error"));
  }, []);

  const hasKey = provider === "anthropic" ? settings?.has_anthropic_key : settings?.has_openai_key;
  const availableModels = hasKey ? models : [];

  useEffect(() => {
    if (!hasKey) return;
    fetch(`${ROVE_API_BASE}/api/models?provider=${provider}`)
      .then((res) => res.json().then((body) => ({ ok: res.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) throw new Error(body.detail ?? "could not load models");
        setModelsError(null);
        setModels(body.models);
      })
      .catch((err) => setModelsError(err instanceof Error ? err.message : "could not load models"));
  }, [provider, hasKey]);

  const handleSave = async () => {
    setSaveState("saving");
    try {
      const body: Record<string, string> = { provider, model };
      if (apiKey) body[provider === "anthropic" ? "anthropic_api_key" : "openai_api_key"] = apiKey;

      const response = await fetch(`${ROVE_API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error();
      setSettings(await response.json());
      setApiKey("");
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-sm font-medium text-white/80">Settings</h1>
        <button
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-sm text-white/50 transition-colors duration-150 hover:bg-white/[0.06] hover:text-white/90"
        >
          Close
        </button>
      </div>

      <div className="mx-auto w-full max-w-md space-y-6 px-6 py-8">
        <div>
          <label className="mb-1 block text-sm text-white/80">Provider</label>
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value as Provider);
              setApiKey("");
              setModel("");
            }}
            className="w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/80"
          >
            {(Object.keys(PROVIDER_LABEL) as Provider[]).map((p) => (
              <option key={p} value={p} className="bg-neutral-900">
                {PROVIDER_LABEL[p]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm text-white/80">API key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={hasKey ? "•••••••••••• (saved, leave blank to keep)" : "sk-…"}
            className="w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/80 placeholder:text-white/30"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm text-white/80">Model</label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={!hasKey || availableModels.length === 0}
            className="w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/80 disabled:opacity-40"
          >
            <option value="" className="bg-neutral-900">
              {modelsError ?? (hasKey ? "Loading models…" : "Save an API key to load models")}
            </option>
            {availableModels.map((m) => (
              <option key={m.id} value={m.id} className="bg-neutral-900">
                {m.display_name}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleSave}
          disabled={saveState === "saving"}
          className="w-full rounded-lg bg-white/90 px-3 py-2 text-sm font-medium text-black transition-colors duration-150 hover:bg-white disabled:opacity-50"
        >
          {saveState === "saving" ? "Saving…" : "Save"}
        </button>
        {saveState === "saved" && <p className="text-sm text-emerald-400">Saved.</p>}
        {saveState === "error" && <p className="text-sm text-red-400">Could not save settings.</p>}

        <div>
          <p className="mb-1 text-sm text-white/80">Permissions</p>
          <p className="text-sm text-white/40">
            Rove will ask before high-risk actions: sending email, purchases, deleting files.
          </p>
        </div>
      </div>
    </div>
  );
}
