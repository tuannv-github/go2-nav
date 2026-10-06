// tabs/DongleTab.jsx — per-UE system info, connection status, and 5G network.
// Exposes (global + window): DongleTab

function dongleTone(row) {
  if (!row || !row.reachable) return "bad";
  if (row.airplane) return "warn";
  const link = row.connection && row.connection.status;
  if (link === "connected") return "ok";
  if (link === "connecting") return "warn";
  return "bad";
}

function dongleLabel(row) {
  if (!row) return "-";
  return row.ue || row.serial || row.usb_path || row.iface || "-";
}

function show(value) {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function dbm(value) {
  if (value == null || value === "") return "-";
  return fmtNumber(value, 0) + " dBm";
}

function db(value) {
  if (value == null || value === "") return "-";
  return fmtNumber(value, 0) + " dB";
}

function bytes(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (Math.abs(n) >= 1e6) return fmtNumber(n / 1e6, 2) + " MB";
  if (Math.abs(n) >= 1e3) return fmtNumber(n / 1e3, 1) + " kB";
  return fmtNumber(n, 0) + " B";
}

function InfoGrid({ rows }) {
  return (
    <div className="stat-grid">
      {rows.map(([label, value]) => (
        <div className="stat-cell" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function DongleTab({ state, actions }) {
  useBridgeLive(actions);
  const pack = state.dongles;
  const rows = pack && Array.isArray(pack.dongles) ? pack.dongles : [];
  const statusError = state.dongleDetail || (pack && pack.detail) || "";

  React.useEffect(() => {
    let stop = false;

    async function tick() {
      try {
        const body = await bridgeSend("/dongle/status");
        if (stop) return;
        actions.setState((prev) => ({ ...prev, dongles: body, dongleDetail: "" }));
      } catch (err) {
        if (stop) return;
        actions.setState((prev) => ({
          ...prev,
          dongleDetail: (err && err.message) || "Dongle status unavailable",
        }));
      }
    }

    tick();
    const id = setInterval(tick, 2000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [actions]);

  return (
    <>
      <div className="tier">
        <KpiStrip items={RAPP_CONFIG.kpis(state)} />
      </div>
      <div className="tier">
        <div className="panel-head">
          <SectionLabel kicker={pack ? rows.length + " attached" : "status"}>UE dongles</SectionLabel>
          <span className={"feed-live" + (statusError ? " is-cached" : "")}>
            <span className={"status-dot " + (statusError ? "dot-bad" : "dot-ok")} />
            {statusError ? "Stale" : "Live"}
          </span>
        </div>
        {statusError ? (
          <p className="drive-notice"><span className="feed-badge feed-badge-warn">Fail</span>{statusError}</p>
        ) : null}
        {!pack && !statusError ? (
          <Card><p className="pad-hint">Loading dongle status…</p></Card>
        ) : null}
        {pack && !rows.length && !statusError ? (
          <Card><p className="pad-hint">No Pegatron dongles found (USB 2cb7:0105 / 2cb7:010b).</p></Card>
        ) : null}
        {rows.map((row) => {
          const system = row.system || {};
          const connection = row.connection || {};
          const network = row.network || {};
          const sim = row.sim || {};
          const tone = dongleTone(row);
          const key = row.serial || row.usb_path || row.iface;
          return (
            <div className="dongle-ue" key={key}>
              <div className="dongle-ue-head">
                <strong>{dongleLabel(row)}</strong>
                <StatusDot state={tone} label={row.reachable ? (connection.status || "up") : "down"} />
                <span className="mono dim">{show(row.iface)} · {show(row.gateway)} · {show(row.usb_path)}</span>
              </div>
              {row.error ? (
                <p className="drive-notice"><span className="feed-badge feed-badge-warn">API</span>{row.error}</p>
              ) : null}
              <div className="dongle-panels">
                <Card>
                  <SectionLabel kicker={system.name || "modem"}>System info</SectionLabel>
                  <InfoGrid rows={[
                    ["Device name", show(system.name)],
                    ["Uptime", show(system.uptime)],
                    ["Serial number", show(system.serial)],
                    ["IMEI", show(system.imei)],
                    ["IMSI", show(system.imsi)],
                    ["ICCID", show(system.iccid)],
                    ["My number", show(system.msisdn)],
                    ["Hardware version", show(system.hw)],
                    ["Software version", show(system.sw)],
                    ["Web UI version", show(system.webui)],
                    ["Config version", show(system.config)],
                    ["WAN IP address", show(system.wan_ipv4)],
                    ["WAN IPv6 address", show(system.wan_ipv6)],
                  ]} />
                </Card>
                <Card>
                  <SectionLabel kicker={connection.uptime || "link"}>Connection status</SectionLabel>
                  <InfoGrid rows={[
                    ["Status", show(connection.status)],
                    ["WAN IPv4", show(connection.ipv4)],
                    ["WAN IPv6", show(connection.ipv6)],
                    ["Uptime", show(connection.uptime)],
                    ["Downlink rate", show(connection.dl_rate)],
                    ["Uplink rate", show(connection.ul_rate)],
                    ["Downlink", bytes(connection.dl_bytes)],
                    ["Uplink", bytes(connection.ul_bytes)],
                    ["SIM", show(sim.state || (sim.spn ? sim.spn : null))],
                    ["SIM name", show(sim.spn)],
                    ["Airplane", row.airplane == null ? "-" : (row.airplane ? "on" : "off")],
                    ["USB serial", show(row.serial)],
                  ]} />
                </Card>
                <Card>
                  <SectionLabel kicker={network.cell || "NR"}>5G network</SectionLabel>
                  <InfoGrid rows={[
                    ["Network", show(network.name)],
                    ["PLMN", show(network.plmn)],
                    ["RAT", show(network.rat)],
                    ["Cell", show(network.cell)],
                    ["Band", show(network.band)],
                    ["Bandwidth", network.bandwidth != null ? show(network.bandwidth) + " MHz" : "-"],
                    ["PCI", show(network.pci)],
                    ["ARFCN", show(network.arfcn)],
                    ["TAC", show(network.tac)],
                    ["Roaming", network.roaming == null ? "-" : (network.roaming ? "yes" : "no")],
                    ["RSRP", dbm(network.rsrp)],
                    ["RSRQ", db(network.rsrq)],
                    ["SINR", db(network.sinr)],
                    ["Signal level", show(network.level)],
                  ]} />
                </Card>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

Object.assign(window, { DongleTab });
