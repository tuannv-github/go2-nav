// tabs/NavigateTab.jsx — Nav2 goal, pose, and costmap.
// Exposes (global + window): NavigateTab

function navTone(status) {
  if (status === "succeeded" || status === "idle" || status === "canceled" || status === "finished") return "ok";
  if (status === "executing" || status === "waiting" || status === "canceling") return "warn";
  return "bad";
}

function NavigateTab({ state, actions }) {
  useBridgeLive(actions);
  const goal = state.goalDraft || { x: "0", y: "0", yaw: "0", frame_id: "map" };
  const poseDraft = state.poseDraft || { x: "0", y: "0", yaw: "0", frame_id: "map" };
  const nav = state.nav || {};
  const status = nav.status || "idle";

  function setGoal(key, value) {
    actions.setState((prev) => ({
      ...prev,
      goalDraft: Object.assign({}, prev.goalDraft, { [key]: value }),
    }));
  }

  function setPoseDraft(key, value) {
    actions.setState((prev) => ({
      ...prev,
      poseDraft: Object.assign({}, prev.poseDraft, { [key]: value }),
    }));
  }

  function readPose(draft) {
    const x = Number(draft.x);
    const y = Number(draft.y);
    const yaw = Number(draft.yaw);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(yaw)) return null;
    return {
      x,
      y,
      yaw,
      frame_id: draft.frame_id || "map",
    };
  }

  async function sendGoal() {
    const body = readPose(goal);
    if (!body) {
      actions.setState((prev) => ({ ...prev, notice: "Goal needs numeric x, y, and yaw" }));
      return;
    }
    try {
      await bridgeSend("/nav2/goal", { method: "POST", body: JSON.stringify(body) });
      actions.setState((prev) => ({ ...prev, notice: "" }));
    } catch (err) {
      actions.setState((prev) => ({ ...prev, notice: err.message || "Goal failed" }));
    }
  }

  async function cancelGoal() {
    try {
      await bridgeSend("/nav2/cancel", { method: "POST" });
      actions.setState((prev) => ({ ...prev, notice: "" }));
    } catch (err) {
      actions.setState((prev) => ({ ...prev, notice: err.message || "Cancel failed" }));
    }
  }

  async function setPose() {
    const body = readPose(poseDraft);
    if (!body) {
      actions.setState((prev) => ({ ...prev, notice: "Pose needs numeric x, y, and yaw" }));
      return;
    }
    try {
      await bridgeSend("/nav2/pose", { method: "POST", body: JSON.stringify(body) });
      actions.setState((prev) => ({ ...prev, notice: "" }));
    } catch (err) {
      actions.setState((prev) => ({ ...prev, notice: err.message || "Set pose failed" }));
    }
  }

  async function clearMap() {
    try {
      await bridgeSend("/nav2/clear_local_costmap", { method: "POST" });
      actions.setState((prev) => ({ ...prev, notice: "" }));
    } catch (err) {
      actions.setState((prev) => ({ ...prev, notice: err.message || "Clear costmap failed" }));
    }
  }

  function copyLive(which) {
    const pose = state.pose;
    if (!pose) return;
    const draft = {
      x: Number(pose.x).toFixed(3),
      y: Number(pose.y).toFixed(3),
      yaw: Number(pose.yaw).toFixed(3),
      frame_id: pose.frame_id || "map",
    };
    actions.setState((prev) => (
      which === "pose"
        ? { ...prev, poseDraft: draft }
        : { ...prev, goalDraft: draft }
    ));
  }

  const rows = [
    ["Status", status],
    ["Goal", nav.goal ? (fmtNumber(nav.goal.x, 2) + ", " + fmtNumber(nav.goal.y, 2)) : "-"],
    ["Distance", nav.feedback && nav.feedback.distance_remaining != null ? fmtNumber(nav.feedback.distance_remaining, 2) + " m" : "-"],
    ["Result", nav.result && nav.result.message ? nav.result.message : "-"],
  ];

  return (
    <>
      <div className="tier">
        <KpiStrip items={RAPP_CONFIG.kpis(state)} />
      </div>

      <div className="tier row-2">
        <Card>
          <div className="panel-head">
            <SectionLabel kicker={state.pose ? state.pose.frame_id : "map"}>Live pose</SectionLabel>
            <StatusDot
              state={state.pose ? "ok" : "warn"}
              label={state.pose ? "Tracking" : "No TF"}
            />
          </div>
          <div className="cmd-readout">
            <div className="cmd-cell">
              <div className="cmd-k">x</div>
              <div className="cmd-v mono">{state.pose ? fmtNumber(state.pose.x, 2) : "-"}</div>
            </div>
            <div className="cmd-cell">
              <div className="cmd-k">y</div>
              <div className="cmd-v mono">{state.pose ? fmtNumber(state.pose.y, 2) : "-"}</div>
            </div>
            <div className="cmd-cell">
              <div className="cmd-k">yaw</div>
              <div className="cmd-v mono">{state.pose ? fmtNumber(state.pose.yaw, 2) : "-"}</div>
            </div>
          </div>
          {state.poseDetail ? <p className="drive-notice"><span className="feed-badge feed-badge-warn">TF</span>{state.poseDetail}</p> : null}
        </Card>

        <Card className="table-card">
          <div className="panel-head">
            <SectionLabel kicker="NavigateToPose">Nav status</SectionLabel>
            <StatusDot state={navTone(status)} label={status} />
          </div>
          <div className="table-scroll">
            <table className="dtable">
              <tbody>
                {rows.map((row) => (
                  <tr key={row[0]}>
                    <td className="dim">{row[0]}</td>
                    <td className="mono">{row[1]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="act-row">
            <button type="button" className="act-btn" onClick={cancelGoal}>Cancel goal</button>
            <button type="button" className="act-btn" onClick={clearMap}>Clear local costmap</button>
          </div>
        </Card>
      </div>

      <div className="tier row-2">
        <Card>
          <SectionLabel kicker="POST /nav2/goal">Send goal</SectionLabel>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">x</span>
              <input className="field-input" value={goal.x} onChange={(e) => setGoal("x", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">y</span>
              <input className="field-input" value={goal.y} onChange={(e) => setGoal("y", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">yaw</span>
              <input className="field-input" value={goal.yaw} onChange={(e) => setGoal("yaw", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">frame</span>
              <input className="field-input" value={goal.frame_id} onChange={(e) => setGoal("frame_id", e.target.value)} />
            </label>
          </div>
          <div className="act-row">
            <button type="button" className="act-btn act-btn-primary" onClick={sendGoal}>Send goal</button>
            <button type="button" className="act-btn" onClick={() => copyLive("goal")} disabled={!state.pose}>Use live pose</button>
          </div>
        </Card>

        <Card>
          <SectionLabel kicker="POST /nav2/pose">Set localization</SectionLabel>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">x</span>
              <input className="field-input" value={poseDraft.x} onChange={(e) => setPoseDraft("x", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">y</span>
              <input className="field-input" value={poseDraft.y} onChange={(e) => setPoseDraft("y", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">yaw</span>
              <input className="field-input" value={poseDraft.yaw} onChange={(e) => setPoseDraft("yaw", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">frame</span>
              <input className="field-input" value={poseDraft.frame_id} onChange={(e) => setPoseDraft("frame_id", e.target.value)} />
            </label>
          </div>
          <div className="act-row">
            <button type="button" className="act-btn act-btn-primary" onClick={setPose}>Publish initial pose</button>
            <button type="button" className="act-btn" onClick={() => copyLive("pose")} disabled={!state.pose}>Use live pose</button>
          </div>
        </Card>
      </div>

      {state.notice ? (
        <div className="tier">
          <Card>
            <SectionLabel>Notice</SectionLabel>
            <p className="drive-notice"><span className="feed-badge feed-badge-warn">Fail</span>{state.notice}</p>
          </Card>
        </div>
      ) : null}
    </>
  );
}

Object.assign(window, { NavigateTab });
