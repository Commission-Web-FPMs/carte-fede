import { shouldSignalActivity } from "./session-activity.mjs";
let installed = false;
export function installDevSession() {
  if (installed) return;
  installed = true;
  let csrf = "", active = false, busy = false, lastSent = -Infinity, timer: ReturnType<typeof setTimeout>;
  const originalFetch = window.fetch.bind(window);
  const expire = () => { if (!active) return; active = false; csrf = ""; clearTimeout(timer); window.location.replace("/api/auth/oidc/login?expired=1"); };
  const schedule = (data: any) => {
    csrf = data.activity_csrf; active = true; clearTimeout(timer);
    timer = setTimeout(expire, Math.max(0, (data.expires_at-data.server_now)*1000));
  };
  async function status() {
    try { const response = await originalFetch("/api/auth/session", { credentials: "include" }); if (response.ok) schedule(await response.json()); else if (response.status === 401) expire(); } catch { /* Retry on real interaction, never extend a deadline on error. */ }
  }
  window.fetch = async (...args: Parameters<typeof fetch>) => {
    const response = await originalFetch(...args);
    const target = new URL(args[0] instanceof Request ? args[0].url : String(args[0]), location.href);
    if (response.ok && target.origin === location.origin && target.pathname === "/api/auth/logout") { active=false; csrf=""; clearTimeout(timer); }
    if (response.status === 401 && target.origin === location.origin && target.pathname.startsWith("/api/") && active) expire();
    return response;
  };
  const activity = async (event: Event) => {
    if (!active || busy || !shouldSignalActivity(event, document.visibilityState === "visible", Date.now(), lastSent)) return;
    busy = true; lastSent = Date.now();
    try {
      const response = await originalFetch("/api/auth/session/activity", { method: "POST", credentials: "include", headers: { "X-Session-Activity-CSRF": csrf } });
      if (response.ok) schedule(await response.json()); else if (response.status === 401) expire();
    } catch { /* The server deadline is unchanged. */ } finally { busy = false; }
  };
  for (const type of ["pointerdown","keydown","input","wheel","touchstart"]) document.addEventListener(type, activity, { passive: true, capture: true });
  document.addEventListener("astro:page-load", status);
  status();
}
