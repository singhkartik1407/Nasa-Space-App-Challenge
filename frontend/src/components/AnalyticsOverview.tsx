import { useEffect, useState } from "react";
import {
  getFrpAnalytics,
  getRelationshipAnalytics,
  getSensorAnalytics,
} from "../lib/api/analytics";
import type {
  FrpAnalyticsResponse,
  RelationshipAnalyticsResponse,
  SensorAnalyticsResponse,
} from "../lib/api/types";

export default function AnalyticsOverview() {
  const [frp, setFrp] = useState<FrpAnalyticsResponse | null>(null);
  const [sensors, setSensors] = useState<SensorAnalyticsResponse | null>(null);
  const [relationships, setRelationships] = useState<RelationshipAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<"2024-03" | "2012-03">("2024-03");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const startDate = period === "2024-03" ? "2024-03-01" : "2012-03-01";
    const endDate = period === "2024-03" ? "2024-03-31" : "2012-03-31";

    Promise.all([
      getFrpAnalytics(startDate, endDate),
      getSensorAnalytics(),
      getRelationshipAnalytics(period),
    ])
      .then(([frpData, sensorData, relData]) => {
        if (active) {
          setFrp(frpData);
          setSensors(sensorData);
          setRelationships(relData);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load analytics.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [period]);

  return (
    <div className="analytics-content">
      {/* Period Selector */}
      <section style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div style={{ fontSize: "14px", color: "#94a3b8" }}>
          Analyzing validated pilot matching period: <strong>{period === "2024-03" ? "March 2024 (MODIS 61.03 era)" : "March 2012 (MODIS 6.03 era)"}</strong>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            className={`btn-period ${period === "2024-03" ? "active" : ""}`}
            style={{
              padding: "6px 12px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              background: period === "2024-03" ? "#0284c7" : "#1e293b",
              color: "#fff",
              border: "1px solid #334155",
            }}
            onClick={() => setPeriod("2024-03")}
          >
            March 2024 Pilot
          </button>
          <button
            type="button"
            className={`btn-period ${period === "2012-03" ? "active" : ""}`}
            style={{
              padding: "6px 12px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              background: period === "2012-03" ? "#0284c7" : "#1e293b",
              color: "#fff",
              border: "1px solid #334155",
            }}
            onClick={() => setPeriod("2012-03")}
          >
            March 2012 Pilot
          </button>
        </div>
      </section>

      {error && <div className="summary-error" role="alert">{error}</div>}

      <section className="analytics-sensor-grid">
        {/* MODIS Analytics Card */}
        <article className="panel analytics-sensor-card">
          <div className="analytics-card-heading">
            <span className="legend-dot modis" />
            <h3>MODIS (Terra + Aqua)</h3>
            <span className="analytics-platform">1.0 km nominal resolution</span>
          </div>
          <p className="analytics-description">
            Moderate-resolution satellite active-fire detections with calibrated 0–100 numeric confidence.
          </p>
          <div className="analytics-metric">
            <span>FRP Mean / Median</span>
            <strong>
              {loading || !frp ? "Loading..." : `${frp.modis.mean_frp_mw} / ${frp.modis.median_frp_mw} MW`}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>FRP Upper Tail (p95 / Max)</span>
            <strong>
              {loading || !frp ? "Loading..." : `${frp.modis.p95_frp_mw} / ${frp.modis.max_frp_mw.toLocaleString()} MW`}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>Common-Period Observations</span>
            <strong>
              {sensors ? `${sensors.modis.common_period_detections.toLocaleString()} detections` : "1,232,096 detections"}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>Product Versions</span>
            <strong>v6.03 (2012–2022) · v61.03 (2023–2026)</strong>
          </div>
        </article>

        {/* VIIRS Analytics Card */}
        <article className="panel analytics-sensor-card">
          <div className="analytics-card-heading">
            <span className="legend-dot viirs" />
            <h3>VIIRS (Suomi-NPP)</h3>
            <span className="analytics-platform">375 m nominal resolution</span>
          </div>
          <p className="analytics-description">
            High-resolution active-fire imaging with categorical confidence (low, nominal, high).
          </p>
          <div className="analytics-metric">
            <span>FRP Mean / Median</span>
            <strong>
              {loading || !frp ? "Loading..." : `${frp.viirs.mean_frp_mw} / ${frp.viirs.median_frp_mw} MW`}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>FRP Upper Tail (p95 / Max)</span>
            <strong>
              {loading || !frp ? "Loading..." : `${frp.viirs.p95_frp_mw} / ${frp.viirs.max_frp_mw.toLocaleString()} MW`}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>Common-Period Observations</span>
            <strong>
              {sensors ? `${sensors.viirs.common_period_detections.toLocaleString()} detections` : "8,725,086 detections"}
            </strong>
          </div>
          <div className="analytics-metric">
            <span>Product Versions</span>
            <strong>Collection 2 (v2 throughout)</strong>
          </div>
        </article>
      </section>

      {/* Sensor Relationship Analysis Table */}
      <section className="panel analytics-comparison">
        <div className="panel-header">
          <div>
            <h3>Sensor relationship sensitivity analysis ({period})</h3>
            <p>Candidate spatiotemporal association metrics under evaluated threshold profiles</p>
          </div>
          <span className="section-tag" style={{ background: "#0369a1", color: "#f0f9ff" }}>AUDITED PILOT RESULTS</span>
        </div>

        {loading || !relationships ? (
          <div className="analytics-empty">
            <span className="loading-spinner" />
            <strong>Loading relationship audit metrics...</strong>
          </div>
        ) : (
          <div className="match-table-scroll" style={{ padding: "0 16px 16px 16px" }}>
            <table className="match-table" style={{ width: "100%", fontSize: "13px" }}>
              <thead>
                <tr>
                  <th>Profile</th>
                  <th>Candidate Edges</th>
                  <th>MODIS Connected</th>
                  <th>VIIRS Connected</th>
                  <th>Graph Components</th>
                  <th>1-to-1 Share</th>
                  <th>Extent &gt; 5 km</th>
                  <th>Span &gt; 3 h</th>
                </tr>
              </thead>
              <tbody>
                {relationships.profile_sensitivity.map((p) => {
                  const isA = p.profile.startsWith("A");
                  const isB = p.profile.startsWith("B");
                  return (
                    <tr key={p.profile} style={{ background: isA ? "rgba(2, 132, 199, 0.12)" : isB ? "rgba(16, 185, 129, 0.08)" : "transparent" }}>
                      <td>
                        <strong>{p.profile}</strong>
                        {isA && <span style={{ marginLeft: "6px", fontSize: "10px", background: "#0284c7", color: "#fff", padding: "1px 5px", borderRadius: "3px" }}>MVP Default</span>}
                        {isB && <span style={{ marginLeft: "6px", fontSize: "10px", background: "#059669", color: "#fff", padding: "1px 5px", borderRadius: "3px" }}>Alternative</span>}
                      </td>
                      <td><strong>{p.candidate_edges.toLocaleString()}</strong></td>
                      <td>{p.modis_with_candidates.toLocaleString()}</td>
                      <td>{p.viirs_with_candidates.toLocaleString()}</td>
                      <td>{p.components.toLocaleString()}</td>
                      <td><strong>{p.one_to_one_share_pct.toFixed(2)}%</strong></td>
                      <td>{p.components_over_5km}</td>
                      <td>{p.components_over_3h}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bottom-note">
        <div className="note-icon">i</div>
        <div>
          <strong>Interpretation and data integrity</strong>
          <p>
            MODIS and VIIRS confidence values use fundamentally different systems (0–100 vs categorical) and must never be combined into one scale.
            FRP summaries remain separate by sensor due to instrument resolution differences (1.0 km vs 375 m).
            Candidate pairs indicate possible spatiotemporal associations under footprint geometry, not confirmed physical fire matches.
          </p>
        </div>
      </section>
    </div>
  );
}
