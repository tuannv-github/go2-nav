// lib/bridge.jsx — Go2 controller REST client.
// Exposes (global + window): bridgeOrigin, bridgeSend, bridgeHalt, useBridgeLive

function bridgeOrigin() {
  const params = new URLSearchParams(window.location.search);
  const api = params.get("api");
  if (api) return String(api).replace(/\/$/, "");
  if (window.location.pathname.indexOf("/console") === 0) return window.location.origin;
  const host = window.location.hostname || "127.0.0.1";
  return "http://" + host + ":8081";
}

async function bridgeSend(path, options) {
  const opts = options || {};
  let res;
  try {
    res = await fetch(bridgeOrigin() + path, {
      method: opts.method || "GET",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: opts.body,
    });
  } catch (err) {
    throw new Error("Bridge unreachable");
  }
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) {
    const detail = body && body.detail ? body.detail : (res.status + " " + res.statusText);
    const err = new Error(typeof detail === "string" ? detail : "Request failed");
    err.status = res.status;
    throw err;
  }
  return body;
}

function bridgeHalt() {
  const zero = JSON.stringify({ lx: 0, ly: 0, rx: 0, ry: 0, keys: 0 });
  return Promise.all([
    bridgeSend("/wireless", { method: "POST", body: zero }).catch(() => null),
    bridgeSend("/cmd_vel/stop", { method: "POST" }).catch(() => null),
  ]);
}

function useBridgeLive(actions) {
  React.useEffect(() => {
    let stop = false;

    async function tick() {
      const next = {};
      try {
        const health = await bridgeSend("/health");
        next.link = "live";
        next.linkDetail = "Live";
        next.health = health;
        if (health && health.vx != null) {
          next.calib = { vx: health.vx, vy: health.vy, w: health.w };
        }
      } catch (err) {
        next.link = "offline";
        next.linkDetail = "Offline";
      }
      try {
        next.pose = await bridgeSend("/nav2/pose");
        next.poseDetail = "";
      } catch (err) {
        next.pose = null;
        next.poseDetail = next.link === "live"
          ? (err && err.message ? err.message : "Pose unavailable")
          : "";
      }
      try {
        next.nav = await bridgeSend("/nav2/status");
      } catch (err) {
        next.nav = next.link === "live"
          ? {
            ok: false,
            status: "unavailable",
            goal: null,
            feedback: {},
            result: null,
            detail: err && err.message ? err.message : "Nav unavailable",
          }
          : { ok: false, status: "idle", goal: null, feedback: {}, result: null };
      }
      if (stop) return;
      actions.setState((prev) => {
        const merged = Object.assign({}, prev, next);
        if (next.calib && !prev.calibDirty) {
          merged.calibDraft = {
            vx: String(next.calib.vx),
            vy: String(next.calib.vy),
            w: String(next.calib.w),
          };
        }
        return merged;
      });
    }

    tick();
    const id = setInterval(tick, 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [actions]);
}

Object.assign(window, { bridgeOrigin, bridgeSend, bridgeHalt, useBridgeLive });
