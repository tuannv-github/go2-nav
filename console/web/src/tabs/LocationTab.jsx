// tabs/LocationTab.jsx — robot pose and the ran-loc mixture, same map as the robot interface.
// Exposes (global + window): LocationTab

function drawArrow(ctx, x, y, dir, length) {
  const dx = Math.cos(dir) * length;
  const dy = -Math.sin(dir) * length;
  const x1 = x + dx;
  const y1 = y + dy;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  const ang = Math.atan2(dy, dx);
  const head = 9;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - head * Math.cos(ang - 0.45), y1 - head * Math.sin(ang - 0.45));
  ctx.lineTo(x1 - head * Math.cos(ang + 0.45), y1 - head * Math.sin(ang + 0.45));
  ctx.closePath();
  ctx.fill();
}

const ESTIMATE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf"];

function weightLabel(weight) {
  const value = Number(weight);
  if (!Number.isFinite(value)) return "—";
  return (value * 100).toFixed(1) + "%";
}

function weightBrightness(weight, peak) {
  const value = Number(weight);
  const top = Number(peak);
  if (!Number.isFinite(value) || value <= 0 || !Number.isFinite(top) || top <= 0) return 0.18;
  const share = Math.min(1, value / top);
  return 0.18 + 0.82 * Math.pow(share, 0.65);
}

function tickStep(span) {
  const rough = Math.max(span, 1) / 4;
  const pow = Math.pow(10, Math.floor(Math.log10(rough)));
  const err = rough / pow;
  const mult = err >= 5 ? 5 : err >= 2 ? 2 : 1;
  return mult * pow;
}

function axisHalf(points, held) {
  let reach = 0;
  points.forEach((loc) => {
    const padM = loc.estimate ? Number(loc.accuracy_m) || 0 : 0;
    const east = Math.abs(Number(loc.x)) + padM;
    const north = Math.abs(Number(loc.y)) + padM;
    if (Number.isFinite(east)) reach = Math.max(reach, east);
    if (Number.isFinite(north)) reach = Math.max(reach, north);
  });
  if (reach <= held) return held;
  const step = tickStep(reach);
  return Math.max(held, Math.ceil((reach * 1.15) / step) * step);
}

function drawSiteMap(ctx, w, h, points, colors, half) {
  const pad = 46;
  ctx.clearRect(0, 0, w, h);
  const step = tickStep(half);
  const metersToPx = (Math.min(w, h) / 2 - pad) / half;
  const cx = w / 2;
  const cy = h / 2;
  const placed = points.map((loc) => {
    const east = Number(loc.x);
    const north = Number(loc.y);
    return {
      loc: loc,
      east: Number.isFinite(east) ? east : 0,
      north: Number.isFinite(north) ? north : 0,
    };
  });

  ctx.strokeStyle = colors.grid;
  ctx.fillStyle = colors.axis;
  ctx.lineWidth = 1;
  ctx.font = "11px 'IBM Plex Sans', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let metre = -half; metre <= half + step * 0.01; metre += step) {
    const px = cx + metre * metersToPx;
    const py = cy - metre * metersToPx;
    const onOrigin = Math.abs(metre) < step * 0.01;
    if (!onOrigin) {
      ctx.beginPath();
      ctx.moveTo(px, pad);
      ctx.lineTo(px, h - pad);
      ctx.moveTo(pad, py);
      ctx.lineTo(w - pad, py);
      ctx.stroke();
    }
    ctx.strokeStyle = colors.axis;
    ctx.beginPath();
    ctx.moveTo(px, cy - 4);
    ctx.lineTo(px, cy + 4);
    ctx.moveTo(cx - 4, py);
    ctx.lineTo(cx + 4, py);
    ctx.stroke();
    ctx.strokeStyle = colors.grid;
    if (!onOrigin) {
      ctx.fillText(String(Math.round(metre * 1000) / 1000), px, cy + 16);
      ctx.textAlign = "right";
      ctx.fillText(String(Math.round(metre * 1000) / 1000), cx - 8, py);
      ctx.textAlign = "center";
    }
  }

  ctx.strokeStyle = colors.axis;
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.moveTo(pad, cy);
  ctx.lineTo(w - pad, cy);
  ctx.moveTo(cx, h - pad);
  ctx.lineTo(cx, pad);
  ctx.stroke();

  ctx.fillStyle = colors.axis;
  ctx.font = "12px 'IBM Plex Sans', sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("+X", w - pad + 4, cy);
  ctx.fillText("+Y", cx + 8, pad - 2);
  ctx.fillText("0", cx + 8, cy + 16);

  if (!placed.length) {
    ctx.font = "13px 'IBM Plex Sans', sans-serif";
    ctx.fillText("Waiting for a location", pad, h - 16);
    return;
  }

  const ordered = placed.slice().sort((a, b) => {
    const rank = (item) => (item.loc.estimate ? (item.loc.brightness || 0) : 2);
    return rank(a) - rank(b);
  });
  ordered.forEach(({ loc, east, north }) => {
    const x = cx + east * metersToPx;
    const y = cy - north * metersToPx;
    const ink = loc.estimate ? (loc.color || colors.accent) : (loc.connected ? colors.baseline : colors.axis);
    ctx.strokeStyle = ink;
    ctx.fillStyle = ink;
    ctx.globalAlpha = loc.estimate ? (loc.brightness || 1) : 1;
    ctx.lineWidth = 2;
    if (loc.estimate) {
      const radius = Math.max(8, (Number(loc.accuracy_m) || 0) * metersToPx);
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      const dir = Number(loc.w);
      if (Number.isFinite(dir)) drawArrow(ctx, x, y, dir, 26);
    }
    ctx.beginPath();
    ctx.arc(x, y, loc.estimate ? 2 : 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  });
}

function LocationMap({ points, colors }) {
  const box = React.useRef(null);
  const held = React.useRef(50);
  const fit = axisHalf(points, held.current);
  if (fit > held.current) held.current = fit;
  const half = held.current;
  const ref = useCanvas(
    (ctx, w, h) => drawSiteMap(ctx, w, h, points, colors, half),
    [points, colors, half],
    box,
  );
  return (
    <div className="loc-stage" ref={box}>
      <canvas ref={ref} role="img" aria-label="Robot pose and ran-loc estimates" />
    </div>
  );
}

function fmtFixTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Singapore",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function pushTrail(trail, loc) {
  const next = Array.isArray(trail) ? trail.slice() : [];
  const x = Date.parse(loc.estimated_at) / 1000;
  const y = Number(loc.accuracy_m);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return next;
  const last = next[next.length - 1];
  if (last && last.x === x && last.y === y) return next;
  next.push({ x, y });
  return next.slice(-60);
}

function poseFromBridge(state) {
  const pose = state && state.pose;
  if (!pose || pose.x == null || pose.y == null) return null;
  return {
    robot_id: "go2",
    x: pose.x,
    y: pose.y,
    z: pose.z || 0,
    w: pose.yaw,
    source: "go2",
    frame_id: pose.frame_id || "map",
    connected: state.link === "live",
  };
}

function LocationTab({ state, colors, config, actions }) {
  useBridgeLive(actions);
  const kpis = typeof config.kpis === "function" ? config.kpis(state) : [];
  const [pack, setPack] = React.useState(null);
  const [trail, setTrail] = React.useState([]);

  React.useEffect(() => {
    let stop = false;

    async function tick() {
      try {
        const body = await bridgeSend("/location");
        if (stop || !body) return;
        setPack(body);
        const ranked = (body.estimates || []).slice().sort((a, b) => (Number(b.weight) || 0) - (Number(a.weight) || 0));
        if (ranked[0]) setTrail((prev) => pushTrail(prev, ranked[0]));
      } catch (err) {
        if (!stop) setPack(null);
      }
    }

    tick();
    const id = setInterval(tick, 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);

  const pose = (pack && pack.pose) || poseFromBridge(state);
  const ranked = ((pack && pack.estimates) || [])
    .slice()
    .sort((a, b) => (Number(b.weight) || 0) - (Number(a.weight) || 0));
  const peak = ranked.reduce((best, loc) => Math.max(best, Number(loc.weight) || 0), 0);
  const estimates = ranked.map((loc, index) => ({
    ...loc,
    estimate: true,
    color: ESTIMATE_COLORS[index % ESTIMATE_COLORS.length],
    brightness: weightBrightness(loc.weight, peak),
  }));
  const poses = pose ? [{ ...pose, estimate: false, connected: pose.connected !== false }] : [];
  const points = poses.concat(estimates);
  const estimate = estimates[0] || null;
  const loc = estimate;
  const hasFix = Boolean(estimate);

  return (
    <React.Fragment>
      <KpiStrip items={kpis} />

      <div className="tier row-hero">
        <Card>
          <div className="panel-head">
            <SectionLabel kicker="origin 0, 0">Location</SectionLabel>
            <StatusDot state={hasFix ? "ok" : "warn"} label={hasFix ? "estimate ready" : "waiting"} />
          </div>
          <LocationMap points={points} colors={colors} />
          <div className="chart-legend">
            {estimates.map((row) => (
              <span className="cl" key={row.seq}>
                <i className="cl-swatch is-dot" style={{ background: row.color, opacity: row.brightness }} />
                {weightLabel(row.weight)}
              </span>
            ))}
            <span className="cl"><i className="cl-swatch is-robot" />robot</span>
          </div>
        </Card>

        <Card>
          <SectionLabel>Fix</SectionLabel>
          {loc ? (
            <div className="kv-list">
              <div className="kv-row"><span>Robot ID</span><span className="mono">{loc.robot_id}</span></div>
              <div className="kv-row"><span>IMSI</span><span className="mono">{loc.imsi || "—"}</span></div>
              <div className="kv-row"><span>X</span><span className="mono">{fmtNumber(loc.x, 2)} m</span></div>
              <div className="kv-row"><span>Y</span><span className="mono">{fmtNumber(loc.y, 2)} m</span></div>
              <div className="kv-row"><span>Z</span><span className="mono">{fmtNumber(loc.z, 2)} m</span></div>
              <div className="kv-row"><span>W</span><span className="mono">{fmtNumber(loc.w, 3)}</span></div>
              <div className="kv-row"><span>Weight</span><span className="mono">{weightLabel(loc.weight)}</span></div>
              <div className="kv-row"><span>Accuracy</span><span className="mono">{fmtNumber(loc.accuracy_m, 1)} m</span></div>
              <div className="kv-row"><span>Source</span><span className="tag tag-muted">{loc.source || "—"}</span></div>
              <div className="kv-row"><span>Time</span><span className="mono">{fmtFixTime(loc.estimated_at)}</span></div>
              {pose ? (
                <div className="kv-row"><span>Robot</span><span className="mono">{fmtNumber(pose.x, 2)} m, {fmtNumber(pose.y, 2)} m</span></div>
              ) : null}
              {estimates.length > 1 ? estimates.map((row) => (
                <div className="kv-row" key={row.seq}>
                  <span><i className="cl-swatch is-dot" style={{ background: row.color, opacity: row.brightness, marginRight: 6 }} />{weightLabel(row.weight)}</span>
                  <span className="mono">{fmtNumber(row.x, 2)} m, {fmtNumber(row.y, 2)} m</span>
                </div>
              )) : null}
            </div>
          ) : (
            <div className="kv-list">
              <p className="dim">No ran-loc estimate yet. The mixture arrives on the robot socket.</p>
              {pose ? (
                <div className="kv-row"><span>Robot</span><span className="mono">{fmtNumber(pose.x, 2)} m, {fmtNumber(pose.y, 2)} m</span></div>
              ) : (
                <p className="dim">Robot pose is not available.</p>
              )}
            </div>
          )}
        </Card>
      </div>

      <div className="tier">
        <Card>
          <div className="panel-head">
            <SectionLabel>Accuracy</SectionLabel>
            <div className="chart-legend">
              <span className="cl"><i className="cl-swatch is-accent" />metres</span>
              <StatusDot state={trail.length >= 2 ? "ok" : "warn"} label={trail.length >= 2 ? "series" : "collecting"} />
            </div>
          </div>
          <LineChart
            series={trail}
            colors={colors}
            height={220}
            yUnit="m"
            yMin={0}
            fmtX={(x) => fmtFixTime(new Date(x * 1000).toISOString())}
          />
        </Card>
      </div>
    </React.Fragment>
  );
}

Object.assign(window, { LocationTab });
