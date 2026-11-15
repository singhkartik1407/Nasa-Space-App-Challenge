import { useEffect, useState } from "react";
import { getHealth, getSystemReadiness } from "../lib/api/metadata";
import { API_BASE_URL } from "../lib/api/client";
import type { SystemReadiness } from "../lib/api/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<{ status: string; app_name: string; app_version: string } | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const t0 = performance.now();

    Promise.all([getHealth(), getSystemReadiness()])
      .then(([healthData, readyData]) => {
        if (active) {
          setHealth(healthData);
          setReadiness(readyData);
          setLatencyMs(Math.round(performance.now() - t0));
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Backend unreachable");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const isConnected = readiness?.ready === true;

  return (
    <div className="settings-content">
      <section className="panel settings-section">
        <div className="panel-header">
          <div>
            <h3>Application</h3>
            <p>FireScope frontend configuration and environment</p>
          </div>
        </div>
        <div className="settings-row">
          <div><strong>Application name</strong><span>Satellite fire intelligence for India</span></div>
          <span className="settings-value">{health?.app_name || "FireScope API"}</span>
        </div>
        <div className="settings-row">
          <div><strong>Version</strong><span>Application release version</span></div>
          <span className="settings-value">{health?.app_version || "1.0.0"}</span>
        </div>
        <div className="settings-row">
          <div><strong>Environment</strong><span>Current deployment runtime</span></div>
          <span className="settings-value">Local development</span>
        </div>
        <div className="settings-row">
          <div><strong>Data mode</strong><span>Active data retrieval strategy</span></div>
          <span className="settings-status" style={{ color: isConnected ? "#10b981" : "#f59e0b" }}>
            {isConnected ? "Live FastAPI / DuckDB Mode" : "Waiting for connection"}
          </span>
        </div>
      </section>

      <section className="panel settings-section">
        <div className="panel-header">
          <div>
            <h3>Backend connection</h3>
            <p>Analytical engine and metadata persistence status</p>
          </div>
        </div>
        <div className="settings-row">
          <div><strong>API status</strong><span>FastAPI process status</span></div>
          <span className="settings-status" style={{ color: isConnected ? "#10b981" : "#ef4444" }}>
            {isConnected ? `Online (${latencyMs}ms)` : error || "Not connected"}
          </span>
        </div>
        <div className="settings-row">
          <div><strong>API base URL</strong><span>Configured endpoint root</span></div>
          <span className="settings-value" style={{ fontFamily: "monospace", fontSize: "12px" }}>{API_BASE_URL}</span>
        </div>
        <div className="settings-row">
          <div><strong>Analytical query engine</strong><span>Direct-over-Parquet query processor</span></div>
          <span className="settings-value">DuckDB (In-Memory Session)</span>
        </div>
        <div className="settings-row">
          <div><strong>Metadata persistence</strong><span>Job state and review annotations</span></div>
          <span className="settings-value">SQLAlchemy (Local SQLite / PostgreSQL-ready)</span>
        </div>
        <div className="settings-row">
          <div><strong>Verified source observations</strong><span>Read-only common-period Parquet files</span></div>
          <span className="settings-value">
            {readiness ? `${(readiness.modis_total_rows + readiness.viirs_total_rows).toLocaleString()} rows` : "9,957,182 rows"}
          </span>
        </div>
      </section>

      <section className="panel settings-section">
        <div className="panel-header">
          <div>
            <h3>Map display</h3>
            <p>Geographic visualization infrastructure</p>
          </div>
        </div>
        <div className="settings-row">
          <div><strong>Primary map provider</strong><span>Interactive geospatial rendering engine</span></div>
          <span className="settings-value">
            {Boolean(import.meta.env.VITE_GOOGLE_MAPS_API_KEY) ? "Google Maps (deck.gl)" : "MapLibre GL (OpenStreetMap)"}
          </span>
        </div>
        <div className="settings-row">
          <div><strong>Google Maps key status</strong><span>3D vector terrain & deck.gl integration</span></div>
          <span className="settings-status" style={{ color: Boolean(import.meta.env.VITE_GOOGLE_MAPS_API_KEY) ? "var(--status-matched)" : "var(--status-profile-b)" }}>
            {Boolean(import.meta.env.VITE_GOOGLE_MAPS_API_KEY) ? "Active (API key loaded)" : "Pending (set VITE_GOOGLE_MAPS_API_KEY in .env)"}
          </span>
        </div>
        <div className="settings-row">
          <div><strong>Geographic extent</strong><span>Default view bounding box</span></div>
          <span className="settings-value">India Subcontinent (67.5°E to 98.0°E, 6.5°N to 37.5°N)</span>
        </div>
      </section>

      <section className="bottom-note">
        <div className="note-icon">i</div>
        <div>
          <strong>System configuration</strong>
          <p>
            The backend serves analytical queries directly from immutable Parquet datasets via DuckDB.
            Threshold Profiles A (1h, 0km) and B (3h, 0km) are active and available across all modules.
          </p>
        </div>
      </section>
    </div>
  );
}
