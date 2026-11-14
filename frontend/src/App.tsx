import { useEffect, useState } from "react";
import {
  Activity, BarChart3, CalendarDays, CircleHelp,
  Crosshair, Download, Flame, Layers3, LayoutDashboard, Map,
  Radio, Settings2, ShieldCheck, SlidersHorizontal, Target, Zap
} from "lucide-react";
import "./App.css";
import FireMap from "./components/FireMap";
import { getDashboardSummary } from "./lib/api/dashboard";
import type { DashboardSummary, DashboardFilters } from "./lib/api/types";
import ActivityChart from "./components/ActivityChart";
import ActivityCalendar from "./components/ActivityCalendar";
import AnalyticsOverview from "./components/AnalyticsOverview";
import MatchExplorer from "./components/MatchExplorer";
import DataSources from "./components/DataSources";
import SettingsPage from "./components/SettingsPage";
import DocumentationPage from "./components/DocumentationPage";

const initialFilters = {
  start: "2024-03-01",
  end: "2024-03-31",
  sensor: "BOTH",
  platform: "ALL",
  daynight: "ALL",
};

const navigation = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Fire map", icon: Map },
  { label: "Activity calendar", icon: CalendarDays },
  { label: "Analytics", icon: BarChart3 },
  { label: "Match explorer", icon: Crosshair },
];

const stats = [
  { label: "MODIS DETECTIONS", sub: "Terra + Aqua (1.0 km)", icon: Flame, color: "orange" },
  { label: "VIIRS DETECTIONS", sub: "Suomi-NPP (375 m)", icon: Radio, color: "blue" },
  { label: "CANDIDATE PAIRS", sub: "Profile A (1h, 0km buffer)", icon: Crosshair, color: "purple" },
  { label: "AMBIGUOUS PAIRS", sub: "Many-to-many relationships", icon: Target, color: "green" },
];

function App() {
  const [filters, setFilters] = useState(initialFilters);
  const [activePage, setActivePage] = useState("Dashboard");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [showActivityPanel, setShowActivityPanel] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  // Fetch summary whenever date or sensor filter changes
  useEffect(() => {
    let active = true;
    setSummaryLoading(true);
    setSummaryError(null);

    getDashboardSummary({
      start_date: filters.start,
      end_date: filters.end,
      sensor: filters.sensor as DashboardFilters["sensor"],
    })
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((error: unknown) => {
        if (active) {
          setSummaryError(
            error instanceof Error ? error.message : "Unable to load dashboard summary."
          );
        }
      })
      .finally(() => {
        if (active) setSummaryLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filters.start, filters.end, filters.sensor]);

  const updateFilter = (key: string, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const resetFilters = () => setFilters(initialFilters);

  const platforms =
    filters.sensor === "MODIS"
      ? [{ value: "ALL", label: "All platforms" }, { value: "TERRA", label: "Terra" }, { value: "AQUA", label: "Aqua" }]
      : filters.sensor === "VIIRS"
        ? [{ value: "SNPP", label: "Suomi-NPP" }]
        : [{ value: "ALL", label: "All platforms" }, { value: "TERRA", label: "Terra" }, { value: "AQUA", label: "Aqua" }, { value: "SNPP", label: "Suomi-NPP" }];

  const changeSensor = (value: string) => {
    setFilters((current) => ({
      ...current,
      sensor: value,
      platform: value === "VIIRS" ? "SNPP" : "ALL",
    }));
  };

  const pageDescriptions: Record<string, string> = {
    "Fire map": "Explore the geographic distribution of satellite detection records across India.",
    "Activity calendar": "Explore monthly and seasonal patterns in satellite detection activity.",
    "Analytics": "Compare sensor-specific trends and historical activity patterns.",
    "Match explorer": "Examine candidate spatial-temporal relationships between MODIS and VIIRS records.",
  };

  const isLive = summary?.data_status === "available";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Flame size={23} /></div>
          <div>
            <div className="brand-name">Fire<span>Scope</span></div>
            <div className="brand-caption">SATELLITE INTELLIGENCE</div>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <nav className="navigation">
          {navigation.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={`nav-item ${activePage === label ? "active" : ""}`}
              onClick={() => setActivePage(label)}
            >
              <Icon size={18} /> {label}
            </button>
          ))}
        </nav>

        <div className="nav-label tools-label">PREFERENCES</div>
        <nav className="navigation">
          <button className="nav-item" onClick={() => setActivePage("Data sources")}><SlidersHorizontal size={18} /> Data sources</button>
          <button className="nav-item" onClick={() => setActivePage("Settings")}><Settings2 size={18} /> Settings</button>
          <button className="nav-item" onClick={() => setActivePage("Documentation")}><CircleHelp size={18} /> Documentation</button>
        </nav>

        <div className="sidebar-bottom">
          <div className="system-card">
            <div className="system-icon"><ShieldCheck size={17} /></div>
            <div>
              <div className="system-title">Data integrity</div>
              <div className="system-subtitle">{isLive ? "Live data connected" : "Connecting..."}</div>
            </div>
            <span className="status-dot" style={{ background: isLive ? "#10b981" : "#f59e0b" }} />
          </div>
          <div className="sidebar-footer">FIRESCOPE <span>·</span> INDIA</div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-separator">/</span><strong>{activePage}</strong></div>
          <div className="topbar-right">
            <div className="demo-pill"><span style={{ background: isLive ? "#10b981" : "#f59e0b" }} /> {isLive ? "FASTAPI BACKEND CONNECTED" : "CONNECTING TO API"}</div>

            <div className="topbar-dropdown-wrap">
              <button
                className="icon-button"
                aria-label="Activity status"
                aria-expanded={showActivityPanel}
                onClick={() => {
                  setShowActivityPanel((open) => !open);
                  setShowProfileMenu(false);
                }}
              >
                <Activity size={18} />
              </button>

              {showActivityPanel && (
                <div className="topbar-dropdown activity-dropdown">
                  <h3>System status</h3>
                  <div className="dropdown-status-row">
                    <span>Frontend application</span>
                    <strong className="status-online">Running</strong>
                  </div>
                  <div className="dropdown-status-row">
                    <span>Data mode</span>
                    <strong style={{ color: isLive ? "#10b981" : "#f59e0b" }}>{isLive ? "Live FastAPI / DuckDB" : "Connecting"}</strong>
                  </div>
                  <div className="dropdown-status-row">
                    <span>Backend API</span>
                    <strong className={isLive ? "status-online" : "status-pending"}>{isLive ? "Online" : "Pending"}</strong>
                  </div>
                  <div className="dropdown-status-row">
                    <span>DuckDB Parquet Engine</span>
                    <strong className={isLive ? "status-online" : "status-pending"}>{isLive ? "Active" : "Pending"}</strong>
                  </div>
                </div>
              )}
            </div>

            <div className="topbar-dropdown-wrap">
              <button
                className="avatar avatar-button"
                aria-label="Open profile menu"
                aria-expanded={showProfileMenu}
                onClick={() => {
                  setShowProfileMenu((open) => !open);
                  setShowActivityPanel(false);
                }}
              >
                FS
              </button>

              {showProfileMenu && (
                <div className="topbar-dropdown profile-dropdown">
                  <div className="profile-menu-heading">
                    <strong>FireScope</strong>
                    <span>Space Tech Hackathon</span>
                  </div>
                  <button onClick={() => { setActivePage("Dashboard"); setShowProfileMenu(false); }}>
                    Dashboard
                  </button>
                  <button onClick={() => { setActivePage("Settings"); setShowProfileMenu(false); }}>
                    Settings
                  </button>
                  <button onClick={() => { setActivePage("Documentation"); setShowProfileMenu(false); }}>
                    Documentation
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="dashboard-content">
          {activePage === "Dashboard" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> INDIA · SATELLITE MONITORING</div>
                  <h1>Fire activity <span>overview</span></h1>
                  <p className="page-description">Monitor satellite fire detections, explore activity patterns, and compare sensor observations across India.</p>
                </div>
                <button className="export-button" disabled><Download size={16} /> Export data <span className="coming-soon">SOON</span></button>
              </section>

              <section className="filter-panel">
                <div className="filter-heading"><SlidersHorizontal size={16} /><span>GLOBAL FILTERS</span><button className="reset-button" onClick={resetFilters}>Reset filters</button></div>
                <div className="filter-controls">
                  <label className="filter-control"><CalendarDays size={15} /><span>From</span><input aria-label="Start date" type="date" min="2012-01-21" max="2026-07-14" value={filters.start} onChange={(e) => updateFilter("start", e.target.value)} /></label>
                  <label className="filter-control"><CalendarDays size={15} /><span>To</span><input aria-label="End date" type="date" min="2012-01-21" max="2026-07-14" value={filters.end} onChange={(e) => updateFilter("end", e.target.value)} /></label>
                  <label className="filter-control"><Layers3 size={15} /><span>Sensor</span><select aria-label="Sensor" value={filters.sensor} onChange={(e) => changeSensor(e.target.value)}><option value="BOTH">Both sensors</option><option value="MODIS">MODIS</option><option value="VIIRS">VIIRS</option></select></label>
                  <label className="filter-control"><Radio size={15} /><span>Platform</span><select aria-label="Platform" value={filters.platform} onChange={(e) => updateFilter("platform", e.target.value)}>{platforms.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></label>
                  <label className="filter-control"><Zap size={15} /><span>Day / Night</span><select aria-label="Day or night" value={filters.daynight} onChange={(e) => updateFilter("daynight", e.target.value)}><option value="ALL">All</option><option value="D">Day</option><option value="N">Night</option></select></label>
                </div>
                <div className="filter-note">
                  Common comparison window: Jan 21, 2012 – Jul 14, 2026 (UTC). Validated pilot matching periods: March 2012 and March 2024.
                </div>
                {filters.start > filters.end && <div className="filter-error">Start date must be earlier than or equal to end date.</div>}
                <div className="active-filter-summary">
                  <strong>Current selection:</strong> {filters.sensor === "BOTH" ? "Both sensors" : filters.sensor} · {filters.platform === "ALL" ? "All applicable platforms" : filters.platform} · {filters.daynight === "ALL" ? "Day and night" : filters.daynight === "D" ? "Daytime" : "Nighttime"} · {filters.start} to {filters.end}
                </div>
              </section>

              <section className="section-heading">
                <div><h2>Detection summary</h2><p>Satellite observation records across selected period ({filters.start} to {filters.end})</p></div>
                <span className="section-tag"><span /> {summary?.matching_available ? "MATCHED PILOT PERIOD" : "SENSORS OVERVIEW"}</span>
              </section>

              {summaryError && <div className="summary-error" role="alert">Summary unavailable: {summaryError}</div>}
              <section className="stats-grid">
                {stats.map((item) => {
                  const Icon = item.icon;
                  const hidden = (item.label === "MODIS DETECTIONS" && filters.sensor === "VIIRS") || (item.label === "VIIRS DETECTIONS" && filters.sensor === "MODIS");
                  const liveValue = item.label === "MODIS DETECTIONS"
                    ? summary?.modis_detection_records
                    : item.label === "VIIRS DETECTIONS"
                      ? summary?.viirs_detection_records
                      : item.label === "CANDIDATE PAIRS"
                        ? summary?.candidate_match_pairs
                        : summary?.ambiguous_candidate_relationships;
                  return (
                    <article role="button" tabIndex={hidden ? -1 : 0} onClick={() => { if (item.label.startsWith("MODIS")) changeSensor("MODIS"); else if (item.label.startsWith("VIIRS")) changeSensor("VIIRS"); }} className={`stat-card stat-clickable ${hidden ? "stat-muted" : ""} ${(item.label.startsWith("MODIS") && filters.sensor === "MODIS") || (item.label.startsWith("VIIRS") && filters.sensor === "VIIRS") ? "stat-selected" : ""}`} key={item.label}>
                      <div className="stat-top"><span className="stat-label">{item.label}</span><span className={`stat-icon ${item.color}`}><Icon size={18} /></span></div>
                      <div className="stat-value">{hidden ? "—" : summaryLoading ? "Loading..." : summaryError ? "Unavailable" : liveValue == null ? "—" : liveValue.toLocaleString()}</div>
                      <div className="stat-bottom"><span className="stat-description">{hidden ? "Not selected" : item.sub}</span></div>
                    </article>
                  );
                })}
              </section>

              <section className="insight-grid">
                <ActivityChart filters={{
                  start_date: filters.start,
                  end_date: filters.end,
                  sensor: filters.sensor as DashboardFilters["sensor"],
                  platform: filters.platform as DashboardFilters["platform"],
                  daynight: filters.daynight as DashboardFilters["daynight"],
                  metric: "modis_detections",
                }} />

                <article className="panel map-panel">
                  <div className="panel-header"><div><h3>India fire map</h3><p>Geographic distribution of detections in selected window</p></div><span className="map-expand"><Crosshair size={16} /></span></div>
                  <div className="real-map-container"><FireMap compact filters={filters} /></div>
                  <div className="map-footer"><span><span className="status-dot" style={{ background: "#10b981" }} /> India coverage</span><span>Live observations active</span></div>
                </article>
              </section>

              <section className="bottom-note"><div className="note-icon"><ShieldCheck size={19} /></div><div><strong>Scientific data integrity</strong><p>Detection records are satellite pixel anomalies, not unique wildfires. Candidate pairs represent spatiotemporal associations under footprint geometry, not confirmed physical fires.</p></div><span className="note-link">METHODOLOGY <Crosshair size={14} /></span></section>
            </>
          ) : activePage === "Activity calendar" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> INDIA · HISTORICAL ACTIVITY</div>
                  <h1>Activity <span>calendar</span></h1>
                  <p className="page-description">Explore monthly satellite detection activity across the selected year.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> LIVE MONTHLY API CONNECTED</div>
              </section>
              <ActivityCalendar />
              <section className="bottom-note">
                <div className="note-icon"><ShieldCheck size={19} /></div>
                <div>
                  <strong>Monthly data is connected directly to Parquet</strong>
                  <p>All monthly counts are queried in real time via DuckDB using canonical UTC grouping. Select any year between 2012 and 2026.</p>
                </div>
              </section>
            </>
          ) : activePage === "Analytics" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> INDIA · SENSOR ANALYSIS</div>
                  <h1>Satellite <span>analytics</span></h1>
                  <p className="page-description">Review sensor-specific detection patterns and potential relationships.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> SENSOR & FRP ANALYTICS ACTIVE</div>
              </section>
              <AnalyticsOverview />
            </>
          ) : activePage === "Match explorer" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> INDIA · SENSOR COMPARISON</div>
                  <h1>Match <span>explorer</span></h1>
                  <p className="page-description">Examine candidate spatiotemporal relationships between MODIS and VIIRS records under Profiles A and B.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> CANDIDATE MATCHES CONNECTED</div>
              </section>
              <MatchExplorer />
            </>
          ) : activePage === "Documentation" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> FIRESCOPE · PROJECT GUIDE</div>
                  <h1>Project <span>documentation</span></h1>
                  <p className="page-description">Understand the satellite datasets, terminology, and scientific interpretation used in FireScope.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> REFERENCE GUIDE</div>
              </section>
              <DocumentationPage />
            </>
          ) : activePage === "Settings" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> FIRESCOPE · CONFIGURATION</div>
                  <h1>Application <span>settings</span></h1>
                  <p className="page-description">Review the current frontend configuration and connection status.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> FASTAPI CONNECTED</div>
              </section>
              <SettingsPage />
            </>
          ) : activePage === "Data sources" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> FIRESCOPE · DATA CATALOG</div>
                  <h1>Data <span>sources</span></h1>
                  <p className="page-description">Review the satellite datasets and collection versions used by FireScope.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> PARQUET ENGINE ACTIVE</div>
              </section>
              <DataSources />
            </>
          ) : activePage === "Fire map" ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow"><span className="eyebrow-line" /> INDIA · GEOSPATIAL MONITORING</div>
                  <h1>Fire <span>map</span></h1>
                  <p className="page-description">Explore the geographic distribution of satellite detection records across India.</p>
                </div>
                <div className="demo-pill"><span style={{ background: "#10b981" }} /> REAL DETECTIONS ACTIVE</div>
              </section>

              <section className="map-toolbar">
                <div className="map-toolbar-title">
                  <Layers3 size={17} />
                  <strong>MAP LAYERS</strong>
                </div>
                <div className="map-layer-options">
                  <span className="layer-option"><i className="legend-dot modis" /> MODIS (1.0 km)</span>
                  <span className="layer-option"><i className="legend-dot viirs" /> VIIRS (375 m)</span>
                  <span className="layer-status" style={{ color: "#38bdf8" }}>Click any detection hotspot for detailed observation properties</span>
                </div>
              </section>

              <section className="panel full-map-panel">
                <div className="panel-header">
                  <div>
                    <h3>India detection overview</h3>
                    <p>Interactive geographic view · Pan and zoom to explore ({filters.start} to {filters.end})</p>
                  </div>
                  <span className="section-tag" style={{ background: "#059669", color: "#fff" }}><span /> LIVE DETECTIONS ACTIVE</span>
                </div>
                <div className="full-map-container">
                  <FireMap filters={{ start: filters.start, end: filters.end, sensor: filters.sensor, daynight: filters.daynight }} />
                </div>
                <div className="full-map-footer">
                  <span><span className="status-dot" style={{ background: "#10b981" }} /> Basemap connected</span>
                  <span>Observation hotspots rendered directly from NASA FIRMS Parquet data</span>
                </div>
              </section>

              <section className="bottom-note">
                <div className="note-icon"><ShieldCheck size={19} /></div>
                <div>
                  <strong>Observation records vs Wildfire Events</strong>
                  <p>Each marker indicates an active-fire satellite pixel anomaly. Click any hotspot to view satellite platform, acquisition timestamp (UTC), confidence, and Fire Radiative Power (MW).</p>
                </div>
              </section>
            </>
          ) : (
            <section className="module-placeholder">
              <div className="eyebrow"><span className="eyebrow-line" /> FIRESCOPE WORKSPACE</div>
              <h1>{activePage}</h1>
              <p>{pageDescriptions[activePage] || `Manage FireScope ${activePage.toLowerCase()} preferences and information.`}</p>
              <div className="module-status"><ShieldCheck size={20} /><div><strong>Module planned</strong><span>This section will be implemented in the next development milestones.</span></div></div>
              <button className="back-button" onClick={() => setActivePage("Dashboard")}>Return to dashboard</button>
            </section>
          )}

          <footer className="page-footer"><span>FIRESCOPE · SATELLITE FIRE INTELLIGENCE</span><span>PRODUCTION INTEGRATION <span className="footer-separator">/</span> LIVE FASTAPI + DUCKDB</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
