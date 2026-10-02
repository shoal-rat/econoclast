// The window talks to the engine directly through pywebview's bridge. The developer
// preview (econoclast app --browser, ?bridge=http) uses a tiny RPC with the same names.

const httpMode = new URLSearchParams(location.search).get("bridge") === "http";

function waitForNative(timeoutMs = 4000) {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve(true);
    const t = setTimeout(() => resolve(false), timeoutMs);
    window.addEventListener("pywebviewready", () => { clearTimeout(t); resolve(true); }, { once: true });
  });
}

async function rpc(name, args) {
  const r = await fetch(`/rpc/${name}`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args) });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || "rpc failed");
  return j.result;
}

let native = false;
export async function connect() {
  native = httpMode ? false : await waitForNative();
  return native;
}

export function isNative() { return native; }

export const api = new Proxy({}, {
  get(_, name) {
    return (...args) => {
      if (native) return window.pywebview.api[name](...args);
      return rpc(name, args);
    };
  },
});
