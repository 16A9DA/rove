export const ROVE_API_BASE = "http://127.0.0.1:8000";

declare global {
  interface Window {
    rove?: { getToken: () => Promise<string> };
  }
}

let cachedToken = "";

// Inside Electron the token comes from the main process (preload bridge). In a plain browser
// (dev only) it must be supplied via NEXT_PUBLIC_ROVE_TOKEN in frontend/.env.local.
async function getToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const token = typeof window !== "undefined" && window.rove ? await window.rove.getToken() : (process.env.NEXT_PUBLIC_ROVE_TOKEN ?? "");
  if (token) cachedToken = token; // never cache "": the backend may not have created it yet
  return token;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Rove-Token", await getToken());
  return fetch(`${ROVE_API_BASE}${path}`, { ...init, headers });
}

// Server-sent events over fetch, so the token travels in a header instead of a URL (which
// would end up in server logs). Return true from onEvent to stop reading.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function streamEvents(path: string, onEvent: (event: any) => boolean | void, signal: AbortSignal): Promise<void> {
  const response = await apiFetch(path, { signal });
  if (!response.ok || !response.body) throw new Error(`stream failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      if (frame.startsWith("data: ") && onEvent(JSON.parse(frame.slice(6))) === true) {
        await reader.cancel();
        return;
      }
    }
  }
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`request failed (${response.status})`);
  return URL.createObjectURL(await response.blob());
}
