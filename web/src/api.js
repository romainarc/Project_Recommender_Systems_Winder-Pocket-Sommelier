// Calls to the FastAPI service. Same origin in production (FastAPI serves this app);
// in development, vite.config.js proxies these paths to http://localhost:8000.

async function call(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export const api = {
  options: () => call("/options"),
  health: () => call("/health"),
  onboard: (body) => call("/onboard", { method: "POST", body: JSON.stringify(body) }),
  recommend: (body) => call("/recommend", { method: "POST", body: JSON.stringify(body) }),
  log: (body) => call("/log_interaction", { method: "POST", body: JSON.stringify(body) }),
};

export function newUserId() {
  return "web-" + Math.random().toString(36).slice(2, 10);
}
