"use client";

export function Settings({ onClose }: { onClose: () => void }) {
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
        <Field label="Groq model" value="openai/gpt-oss-120b" />
        <Field label="Groq API key" value="••••••••••••" />

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

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="mb-1 block text-sm text-white/80">{label}</label>
      <div className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/60">
        {value}
      </div>
    </div>
  );
}
