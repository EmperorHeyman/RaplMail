// Sandbox syscall interceptor.
//
// Installed FIRST inside the isolated sandbox window. It traps the browser APIs
// a payload could use to reach the outside world (network, navigation) so any
// attempt to phone home is logged and blocked.
//
// IMPORTANT nuance: the sandbox page is the RaplMail bundle itself, so on load
// it (and the webview/Tauri runtime) legitimately makes same-origin, `ipc:`,
// `tauri:`, `blob:` and relative requests for its own assets. Those are NOT the
// analyzed file - the file only ever runs inside WebAssembly, which has zero
// network access. So we only *flag and block* requests to a DIFFERENT external
// origin (the only thing that would mean "this is trying to phone home"); we let
// the framework's own internal requests through, or the window couldn't even
// close itself. That keeps the "network guard" count meaningful instead of
// counting framework noise.

// True only for an absolute http(s)/ws(s) URL pointing at a real external host.
// Same-origin, relative, blob:, data:, ipc:, tauri: and loopback/localhost
// (the local backend) are all treated as internal framework traffic - the
// analyzed file can never trigger any of these (it runs only inside wasm), so
// the only thing worth flagging as a "phone-home" is a genuine public host.
function isLoopback(host) {
  const h = (host || "").toLowerCase().replace(/:\d+$/, "");
  return h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]"
    || h.endsWith(".localhost") || h === "tauri.localhost";
}
function isExternal(raw) {
  try {
    const s = String(raw || "");
    if (!/^(https?:|wss?:)\/\//i.test(s)) return false; // relative / blob: / data: / ipc: / tauri: → internal
    const u = new URL(s, location.href);
    return !!u.host && u.host !== location.host && !isLoopback(u.host);
  } catch {
    return false;
  }
}

/**
 * @param {(a: {api: string, target: string}) => void} onAttempt  called only for blocked EXTERNAL requests
 * @returns {() => void} uninstall
 */
export function installInterceptor(onAttempt) {
  const log = (api, target) => {
    try { onAttempt({ api, target: String(target || "").slice(0, 300) }); } catch {}
  };
  const restore = [];

  // fetch
  if (typeof window.fetch === "function") {
    const orig = window.fetch;
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : (input && input.url) || input;
      if (isExternal(url)) { log("fetch", url); return Promise.reject(new Error("blocked by RaplMail sandbox")); }
      return orig.apply(this, arguments);
    };
    restore.push(() => { window.fetch = orig; });
  }

  // XMLHttpRequest
  if (window.XMLHttpRequest) {
    const P = window.XMLHttpRequest.prototype;
    const origOpen = P.open, origSend = P.send;
    P.open = function (method, url) {
      this.__sbExternal = isExternal(url);
      if (this.__sbExternal) log("XMLHttpRequest", `${method} ${url}`);
      return origOpen.apply(this, arguments);
    };
    P.send = function () {
      if (this.__sbExternal) throw new Error("blocked by RaplMail sandbox");
      return origSend.apply(this, arguments);
    };
    restore.push(() => { P.open = origOpen; P.send = origSend; });
  }

  // WebSocket
  if (window.WebSocket) {
    const OrigWS = window.WebSocket;
    function GuardedWS(url, protocols) {
      if (isExternal(url)) { log("WebSocket", url); throw new Error("blocked by RaplMail sandbox"); }
      return protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
    }
    GuardedWS.prototype = OrigWS.prototype;
    try { window.WebSocket = GuardedWS; restore.push(() => { window.WebSocket = OrigWS; }); } catch {}
  }

  // EventSource
  if (window.EventSource) {
    const Orig = window.EventSource;
    function GuardedES(url, init) {
      if (isExternal(url)) { log("EventSource", url); throw new Error("blocked by RaplMail sandbox"); }
      return init === undefined ? new Orig(url) : new Orig(url, init);
    }
    GuardedES.prototype = Orig.prototype;
    try { window.EventSource = GuardedES; restore.push(() => { window.EventSource = Orig; }); } catch {}
  }

  // navigator.sendBeacon
  if (navigator && typeof navigator.sendBeacon === "function") {
    const orig = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (url, data) {
      if (isExternal(url)) { log("sendBeacon", url); return false; }
      return orig(url, data);
    };
    restore.push(() => { navigator.sendBeacon = orig; });
  }

  // window.open to an external URL
  if (typeof window.open === "function") {
    const orig = window.open;
    window.open = function (url, ...rest) {
      if (isExternal(url)) { log("window.open", url); return null; }
      return orig.call(this, url, ...rest);
    };
    restore.push(() => { window.open = orig; });
  }

  return function uninstall() { for (const fn of restore) { try { fn(); } catch {} } };
}
