// tabs/CalibrateTab.jsx — /cmd_vel axis scales.
// Exposes (global + window): CalibrateTab

function CalibrateTab({ state, actions }) {
  useBridgeLive(actions);
  const draft = state.calibDraft || { vx: "0.85", vy: "1.25", w: "1.25" };
  const live = state.calib || {};

  function edit(key, value) {
    actions.setState((prev) => ({
      ...prev,
      calibDirty: true,
      calibDraft: Object.assign({}, prev.calibDraft, { [key]: value }),
    }));
  }

  async function apply() {
    const body = {
      vx: Number(draft.vx),
      vy: Number(draft.vy),
      w: Number(draft.w),
    };
    if (!Number.isFinite(body.vx) || !Number.isFinite(body.vy) || !Number.isFinite(body.w)) {
      actions.setState((prev) => ({ ...prev, notice: "Scales must be finite numbers" }));
      return;
    }
    try {
      const saved = await bridgeSend("/calib", { method: "POST", body: JSON.stringify(body) });
      actions.setState((prev) => ({
        ...prev,
        calibDirty: false,
        notice: "",
        calib: { vx: saved.vx, vy: saved.vy, w: saved.w },
        calibDraft: {
          vx: String(saved.vx),
          vy: String(saved.vy),
          w: String(saved.w),
        },
      }));
    } catch (err) {
      actions.setState((prev) => ({ ...prev, notice: err.message || "Calib update failed" }));
    }
  }

  function reset() {
    actions.setState((prev) => ({
      ...prev,
      calibDirty: false,
      notice: "",
      calibDraft: {
        vx: String(prev.calib ? prev.calib.vx : draft.vx),
        vy: String(prev.calib ? prev.calib.vy : draft.vy),
        w: String(prev.calib ? prev.calib.w : draft.w),
      },
    }));
  }

  return (
    <>
      <div className="tier">
        <KpiStrip items={RAPP_CONFIG.kpis(state)} />
      </div>
      <div className="tier">
        <Card className="config-panel">
          <SectionLabel kicker="sport Move">Velocity scales</SectionLabel>
          <div className="config-live">
            <span className="status-dot dot-ok" aria-hidden="true" />
            <div className="config-live-text">
              <span className="config-live-label">Live scales</span>
              <strong className="mono">
                {"vx " + fmtNumber(live.vx, 2) + "   vy " + fmtNumber(live.vy, 2) + "   w " + fmtNumber(live.w, 2)}
              </strong>
            </div>
            <StatusDot state={state.calibDirty ? "warn" : "ok"} label={state.calibDirty ? "Unsaved" : "Applied"} />
          </div>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">vx scale</span>
              <input className="field-input" value={draft.vx} onChange={(e) => edit("vx", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">vy scale</span>
              <input className="field-input" value={draft.vy} onChange={(e) => edit("vy", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">w scale</span>
              <input className="field-input" value={draft.w} onChange={(e) => edit("w", e.target.value)} />
            </label>
          </div>
          <p className="pad-hint">Sent speed is the command times the scale. Defaults are vx 0.85, vy 1.25, w 1.25.</p>
          <div className="act-row">
            <button type="button" className="act-btn act-btn-primary" onClick={apply}>Apply</button>
            <button type="button" className="act-btn" onClick={reset}>Reset</button>
          </div>
          {state.notice ? (
            <p className="drive-notice"><span className="feed-badge feed-badge-warn">Fail</span>{state.notice}</p>
          ) : null}
        </Card>
      </div>
    </>
  );
}

Object.assign(window, { CalibrateTab });
