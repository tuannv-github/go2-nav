// tabs/DriveTab.jsx — stick teleop and sport velocity.
// Exposes (global + window): DriveTab

function DriveTab({ state, actions }) {
  useBridgeLive(actions);
  const stateRef = React.useRef(state);
  stateRef.current = state;
  const keys = React.useRef(new Set());
  const pad = React.useRef({ lx: 0, ly: 0, active: false });
  const axes = React.useRef({ lx: 0, ly: 0, rx: 0 });
  const lastSport = React.useRef("");
  const stickLive = React.useRef(false);
  const [knob, setKnob] = React.useState({ lx: 0, ly: 0 });

  const applyAxes = React.useCallback(() => {
    const s = stateRef.current || {};
    let lx = 0;
    let ly = 0;
    let rx = 0;
    keys.current.forEach((name) => {
      if (name === "w" || name === "arrowup") ly += 1;
      if (name === "s" || name === "arrowdown") ly -= 1;
      if (name === "a") lx -= 1;
      if (name === "d") lx += 1;
      if (name === "q" || name === "arrowleft") rx -= 1;
      if (name === "e" || name === "arrowright") rx += 1;
    });
    if (pad.current.active) {
      lx += pad.current.lx;
      ly += pad.current.ly;
    }
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (let i = 0; i < pads.length; i += 1) {
      const gp = pads[i];
      if (!gp || !gp.axes || gp.axes.length < 2) continue;
      const dz = 0.12;
      const ax = Math.abs(gp.axes[0]) > dz ? gp.axes[0] : 0;
      const ay = Math.abs(gp.axes[1]) > dz ? -gp.axes[1] : 0;
      const yawAxis = gp.axes.length > 2 && Math.abs(gp.axes[2]) > dz ? gp.axes[2] : 0;
      lx += ax;
      ly += ay;
      rx += yawAxis;
      break;
    }
    const clamp = (v) => Math.max(-1, Math.min(1, v));
    axes.current = { lx: clamp(lx), ly: clamp(ly), rx: clamp(rx) };
  }, []);

  React.useEffect(() => {
    let dead = false;

    async function tick() {
      if (dead) return;
      applyAxes();
      const a = axes.current;
      const s = stateRef.current || {};
      const mode = s.driveMode === "sport" ? "sport" : "stick";
      setKnob({ lx: a.lx, ly: a.ly });

      if (mode === "sport") {
        const speed = Number(s.speed);
        const scale = Number.isFinite(speed) ? speed : 0.2;
        const vx = a.ly * scale;
        const vy = a.lx * scale;
        const w = a.rx * scale;
        const sig = [vx, vy, w].map((n) => n.toFixed(3)).join(",");
        if (sig === lastSport.current) return;
        lastSport.current = sig;
        try {
          if (vx === 0 && vy === 0 && w === 0) {
            await bridgeSend("/cmd_vel/stop", { method: "POST" });
          } else {
            await bridgeSend("/cmd_vel", {
              method: "POST",
              body: JSON.stringify({ vx, vy, w }),
            });
          }
          if (!dead) actions.setState((prev) => ({ ...prev, sport: { vx, vy, w }, notice: "" }));
        } catch (err) {
          if (!dead) actions.setState((prev) => ({ ...prev, notice: err.message || "Sport command failed" }));
        }
        return;
      }

      const mag = Number(s.stickMag);
      const gain = Number.isFinite(mag) ? mag : 0.35;
      const lx = a.lx * gain;
      const ly = a.ly * gain;
      const rx = a.rx * gain;
      const active = Math.abs(lx) + Math.abs(ly) + Math.abs(rx) > 0.0001;
      if (!active && !stickLive.current) return;
      stickLive.current = active;
      try {
        await bridgeSend("/wireless", {
          method: "POST",
          body: JSON.stringify({ lx, ly, rx, ry: 0, keys: 0 }),
        });
        if (!dead) actions.setState((prev) => ({ ...prev, stick: { lx, ly, rx, ry: 0 }, notice: "" }));
      } catch (err) {
        if (!dead) actions.setState((prev) => ({ ...prev, notice: err.message || "Stick command failed" }));
      }
    }

    function typing(event) {
      const tag = event.target && event.target.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    }

    function onKeyDown(event) {
      if (typing(event)) return;
      if (event.code === "Space") {
        event.preventDefault();
        keys.current.clear();
        pad.current = { lx: 0, ly: 0, active: false };
        lastSport.current = "";
        stickLive.current = false;
        bridgeHalt();
        return;
      }
      const name = event.key.toLowerCase();
      const known = ["w", "a", "s", "d", "q", "e", "arrowup", "arrowdown", "arrowleft", "arrowright"];
      if (known.indexOf(name) < 0) return;
      event.preventDefault();
      keys.current.add(name);
    }

    function onKeyUp(event) {
      keys.current.delete(event.key.toLowerCase());
    }

    const id = setInterval(tick, 100);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      dead = true;
      clearInterval(id);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      bridgeHalt();
    };
  }, [actions, applyAxes]);

  function setMode(mode) {
    lastSport.current = "";
    stickLive.current = false;
    bridgeHalt();
    actions.setState((prev) => ({ ...prev, driveMode: mode, notice: "" }));
  }

  function onPad(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
    pad.current = {
      lx: Math.max(-1, Math.min(1, x)),
      ly: Math.max(-1, Math.min(1, y)),
      active: true,
    };
    if (event.currentTarget.setPointerCapture) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  }

  function endPad() {
    pad.current = { lx: 0, ly: 0, active: false };
  }

  const mode = state.driveMode === "sport" ? "sport" : "stick";
  const linkState = state.link === "live" ? "ok" : "bad";
  const knobStyle = {
    left: ((knob.lx + 1) / 2) * 100 + "%",
    top: ((1 - knob.ly) / 2) * 100 + "%",
  };
  const shown = mode === "sport" ? state.sport || {} : state.stick || {};

  return (
    <>
      <div className="tier">
        <KpiStrip items={RAPP_CONFIG.kpis(state)} />
      </div>

      <div className="tier">
        <Card>
          <div className="panel-head">
            <SectionLabel kicker="one path at a time">Drive mode</SectionLabel>
            <StatusDot state={linkState} label={state.linkDetail || "Offline"} />
          </div>
          <div className="config-profiles drive-modes">
            <button
              type="button"
              className={"config-profile" + (mode === "stick" ? " is-selected" : "")}
              aria-pressed={mode === "stick"}
              onClick={() => setMode("stick")}
            >
              <span className="config-profile-mark" />
              <span className="config-profile-body">
                <span className="config-profile-head"><strong>Stick</strong></span>
                <span className="config-profile-desc">Joystick on /wireless. Held until you release.</span>
              </span>
            </button>
            <button
              type="button"
              className={"config-profile" + (mode === "sport" ? " is-selected" : "")}
              aria-pressed={mode === "sport"}
              onClick={() => setMode("sport")}
            >
              <span className="config-profile-mark" />
              <span className="config-profile-body">
                <span className="config-profile-head"><strong>Sport</strong></span>
                <span className="config-profile-desc">Body speed on /cmd_vel. Release sends StopMove.</span>
              </span>
            </button>
          </div>
          {state.notice ? (
            <p className="drive-notice"><span className="feed-badge feed-badge-warn">Fail</span>{state.notice}</p>
          ) : null}
        </Card>
      </div>

      <div className="tier row-hero">
        <Card>
          <SectionLabel kicker={mode === "sport" ? "m/s and rad/s" : "stick −1 to 1"}>Motion</SectionLabel>
          <div className="pad-wrap">
            <div
              className="pad"
              role="application"
              aria-label="Motion pad. Drag to move. W A S D strafe, Q E yaw, Space stops."
              onPointerDown={onPad}
              onPointerMove={(event) => { if (pad.current.active) onPad(event); }}
              onPointerUp={endPad}
              onPointerCancel={endPad}
            >
              <span className="pad-cross" />
              <span className="pad-knob" style={knobStyle} />
            </div>
            <p className="pad-hint">Drag the pad, or use W A S D, Q E, arrows. Space stops. A gamepad left stick also drives.</p>
          </div>
          <label className="field">
            <span className="field-label">{mode === "sport" ? "Speed" : "Stick gain"}</span>
            <input
              className="stick-range"
              type="range"
              min="0"
              max={mode === "sport" ? "0.6" : "1"}
              step="0.05"
              value={mode === "sport" ? state.speed : state.stickMag}
              onChange={(event) => {
                const value = Number(event.target.value);
                actions.setState((prev) => (
                  mode === "sport" ? { ...prev, speed: value } : { ...prev, stickMag: value }
                ));
              }}
            />
            <span className="mono field-value">
              {mode === "sport" ? fmtNumber(state.speed, 2) + " m/s" : fmtNumber(state.stickMag, 2)}
            </span>
          </label>
        </Card>

        <Card>
          <SectionLabel kicker="last sent">Command</SectionLabel>
          <div className="cmd-readout">
            <div className="cmd-cell">
              <div className="cmd-k">{mode === "sport" ? "vx" : "ly"}</div>
              <div className="cmd-v mono">{fmtNumber(mode === "sport" ? shown.vx : shown.ly, 2)}</div>
            </div>
            <div className="cmd-cell">
              <div className="cmd-k">{mode === "sport" ? "vy" : "lx"}</div>
              <div className="cmd-v mono">{fmtNumber(mode === "sport" ? shown.vy : shown.lx, 2)}</div>
            </div>
            <div className="cmd-cell">
              <div className="cmd-k">{mode === "sport" ? "w" : "rx"}</div>
              <div className="cmd-v mono">{fmtNumber(mode === "sport" ? shown.w : shown.rx, 2)}</div>
            </div>
          </div>
          <div className="act-row">
            <button
              type="button"
              className="act-btn act-btn-stop"
              onClick={() => {
                keys.current.clear();
                pad.current = { lx: 0, ly: 0, active: false };
                lastSport.current = "";
                stickLive.current = false;
                bridgeHalt();
              }}
            >
              Stop
            </button>
          </div>
        </Card>
      </div>
    </>
  );
}

Object.assign(window, { DriveTab });
