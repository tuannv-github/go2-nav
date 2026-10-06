// rapp.config.jsx — Go2 controller console manifest.
// Exposes (global + window): RAPP_CONFIG, ICONS

const ICONS = {
  drive: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="2" />
      <path d="M12 4v2M12 18v2M4 12h2M18 12h2" />
    </svg>
  ),
  map: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3-6-3z" /><path d="M9 3v15M15 6v15" />
    </svg>
  ),
  gear: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82-.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
  dongle: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 18a7 7 0 0 1 14 0" />
      <path d="M8.5 18a3.5 3.5 0 0 1 7 0" />
      <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none" />
    </svg>
  ),
};

const RAPP_CONFIG = {
  brand: {
    product: "NeuroRAN",
    shortName: "GO2",
    title: "NeuroRAN GO2 Console",
    logo: "logo/NeuroRAN.png",
    logoPng: "logo/NeuroRAN.png",
  },

  site: {
    label: "Go2",
    id: "go2",
    clockTz: "Asia/Singapore",
  },

  theme: {
    accent: "Energy green",
    dark: false,
    density: "comfy",
  },

  exampleState: {
    link: "offline",
    linkDetail: "Offline",
    notice: "",
    driveMode: "stick",
    speed: 0.2,
    stickMag: 0.35,
    stick: { lx: 0, ly: 0, rx: 0, ry: 0 },
    sport: { vx: 0, vy: 0, w: 0 },
    health: null,
    calib: { vx: 0.85, vy: 1.25, w: 1.25 },
    calibDraft: { vx: "0.85", vy: "1.25", w: "1.25" },
    calibDirty: false,
    pose: null,
    poseDetail: "",
    nav: { ok: false, status: "idle", goal: null, feedback: {}, result: null },
    goalDraft: { x: "0", y: "0", yaw: "0", frame_id: "map" },
    poseDraft: { x: "0", y: "0", yaw: "0", frame_id: "map" },
    dongles: null,
    dongleDetail: "",
  },

  tabs: [
    { id: "drive", label: "Drive", icon: ICONS.drive, component: "DriveTab" },
    { id: "navigate", label: "Navigate", icon: ICONS.map, component: "NavigateTab" },
    { id: "calibrate", label: "Calibrate", icon: ICONS.gear, component: "CalibrateTab" },
    { id: "dongle", label: "Dongle", icon: ICONS.dongle, component: "DongleTab" },
  ],

  kpis: (state) => {
    const pose = state && state.pose;
    const navStatus = (state && state.nav && state.nav.status) || "idle";
    const badNav = navStatus === "aborted" || navStatus === "error" || navStatus === "rejected";
    return [
      {
        label: "Bridge",
        kicker: "REST",
        value: state && state.link === "live" ? "Live" : "Offline",
        icon: "signal",
        bad: !state || state.link !== "live",
      },
      {
        label: "Drive",
        kicker: "mode",
        value: state && state.driveMode === "sport" ? "Sport" : "Stick",
        icon: "gauge",
      },
      {
        label: "Pose X",
        kicker: (pose && pose.frame_id) || "map",
        value: pose ? fmtNumber(pose.x, 2) : "-",
        unit: pose ? "m" : "",
        icon: "grid",
      },
      {
        label: "Nav",
        kicker: "goal",
        value: state && state.link === "live" ? navStatus : "-",
        icon: "check",
        bad: !!(state && state.link === "live" && badNav),
      },
    ];
  },
};

Object.assign(window, { RAPP_CONFIG, ICONS });
