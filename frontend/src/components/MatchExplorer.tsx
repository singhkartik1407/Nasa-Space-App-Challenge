import { useEffect, useState } from "react";
import { getCandidates } from "../lib/api/candidates";
import { getDashboardSummary } from "../lib/api/dashboard";
import type { CandidateMatch, DashboardSummary } from "../lib/api/types";

export default function MatchExplorer() {
  const [profile, setProfile] = useState<"A" | "B">("A");
  const [period, setPeriod] = useState<"2024-03" | "2012-03">("2024-03");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [candidates, setCandidates] = useState<CandidateMatch[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const startDate = period === "2024-03" ? "2024-03-01" : "2012-03-01";
  const endDate = period === "2024-03" ? "2024-03-31" : "2012-03-31";

  // Reset page when profile or period changes
  const handleProfileChange = (newProfile: "A" | "B") => {
    setProfile(newProfile);
    setPage(1);
  };

  const handlePeriodChange = (newPeriod: "2024-03" | "2012-03") => {
    setPeriod(newPeriod);
    setPage(1);
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    Promise.all([
      getDashboardSummary({ start_date: startDate, end_date: endDate }, profile),
      getCandidates({
        profile,
        startDate,
        endDate,
        page,
        pageSize,
      }),
    ])
      .then(([summaryData, candData]) => {
        if (active) {
          setSummary(summaryData);
          setCandidates(candData.items || []);
          setTotalItems(candData.pagination?.total_items || 0);
          setTotalPages(candData.pagination?.total_pages || 1);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load candidate pairs.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [profile, period, page, pageSize, startDate, endDate]);

  return (
    <div className="match-explorer-content">
      {/* Profile & Period Selection Controls */}
      <section style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#94a3b8" }}>MATCH PROFILE:</span>
          <button
            type="button"
            onClick={() => handleProfileChange("A")}
            style={{
              padding: "6px 14px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              background: profile === "A" ? "#0284c7" : "#1e293b",
              color: "#fff",
              border: "1px solid #334155",
            }}
          >
            Profile A (1h, 0km) — Default
          </button>
          <button
            type="button"
            onClick={() => handleProfileChange("B")}
            style={{
              padding: "6px 14px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              background: profile === "B" ? "#059669" : "#1e293b",
              color: "#fff",
              border: "1px solid #334155",
            }}
          >
            Profile B (3h, 0km) — Alternative
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#94a3b8" }}>PILOT PERIOD:</span>
          <select
            value={period}
            onChange={(e) => handlePeriodChange(e.target.value as "2024-03" | "2012-03")}
            style={{
              padding: "6px 12px",
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #334155",
              borderRadius: "4px",
              fontSize: "12px",
            }}
          >
            <option value="2024-03">March 2024 (MODIS 61.03 era)</option>
            <option value="2012-03">March 2012 (MODIS 6.03 era)</option>
          </select>
        </div>
      </section>

      {error && <div className="summary-error" role="alert">{error}</div>}

      {/* Candidate Relationship Overview Cards */}
      <section className="panel match-summary-panel">
        <div className="panel-header">
          <div>
            <h3>Candidate relationship overview</h3>
            <p>
              Potential spatiotemporal candidate relationships under Profile {profile} ({startDate} to {endDate})
            </p>
          </div>
          <span className="section-tag" style={{ background: "#0369a1", color: "#f0f9ff" }}>
            {profile === "A" ? "CONSERVATIVE 1H" : "HIGHER RECALL 3H"}
          </span>
        </div>

        <div className="match-summary-grid">
          <div className="match-summary-item">
            <span>Candidate pairs</span>
            <strong>{loading ? "..." : (summary?.candidate_match_pairs?.toLocaleString() ?? "—")}</strong>
            <small>Spatial-temporal edge count</small>
          </div>
          <div className="match-summary-item">
            <span>Ambiguous relationships</span>
            <strong>{loading ? "..." : (summary?.ambiguous_candidate_relationships?.toLocaleString() ?? "—")}</strong>
            <small>Many-to-one / many-to-many</small>
          </div>
          <div className="match-summary-item">
            <span>MODIS without candidates</span>
            <strong>{loading ? "..." : (summary?.modis_only_records?.toLocaleString() ?? "—")}</strong>
            <small>Coverage unverified</small>
          </div>
          <div className="match-summary-item">
            <span>VIIRS without candidates</span>
            <strong>{loading ? "..." : (summary?.viirs_only_records?.toLocaleString() ?? "—")}</strong>
            <small>Coverage unverified</small>
          </div>
        </div>
      </section>

      {/* Candidate Pair Records Table */}
      <section className="panel match-table-panel">
        <div className="panel-header">
          <div>
            <h3>Candidate pair records</h3>
            <p>
              Showing {candidates.length} of {totalItems.toLocaleString()} candidate pairs (Page {page} of {totalPages})
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <label style={{ fontSize: "11px", color: "#94a3b8", display: "flex", alignItems: "center", gap: "4px" }}>
              Per page:
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                style={{
                  padding: "4px 8px",
                  background: "#0f172a",
                  color: "#f8fafc",
                  border: "1px solid #334155",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </label>
            <button
              type="button"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              style={{
                padding: "4px 10px",
                borderRadius: "4px",
                fontSize: "12px",
                cursor: page <= 1 ? "not-allowed" : "pointer",
                background: "#1e293b",
                color: page <= 1 ? "#64748b" : "#f8fafc",
                border: "1px solid #334155",
              }}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              style={{
                padding: "4px 10px",
                borderRadius: "4px",
                fontSize: "12px",
                cursor: page >= totalPages ? "not-allowed" : "pointer",
                background: "#1e293b",
                color: page >= totalPages ? "#64748b" : "#f8fafc",
                border: "1px solid #334155",
              }}
            >
              Next
            </button>
          </div>
        </div>

        <div className="match-table-scroll">
          <table className="match-table">
            <thead>
              <tr>
                <th>MODIS Record ID</th>
                <th>VIIRS Record ID</th>
                <th>Distance (km)</th>
                <th>Time Diff (min)</th>
                <th>Combined Radii (km)</th>
                <th>Satellites</th>
                <th>FRP (MW)</th>
                <th>Relationship</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="match-empty">
                    <span className="loading-spinner" />
                    <strong>Loading candidate pair records...</strong>
                  </td>
                </tr>
              ) : candidates.length === 0 ? (
                <tr>
                  <td colSpan={8} className="match-empty">
                    <strong>No candidate pair records available</strong>
                    <span>No records meet the selected profile criteria in this interval.</span>
                  </td>
                </tr>
              ) : (
                candidates.map((c) => (
                  <tr key={c.candidate_id}>
                    <td>
                      <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#fb923c" }}>
                        {c.modis_row_id.length > 25 ? `${c.modis_row_id.slice(0, 15)}...${c.modis_row_id.slice(-8)}` : c.modis_row_id}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#60a5fa" }}>
                        {c.viirs_row_id.length > 25 ? `${c.viirs_row_id.slice(0, 15)}...${c.viirs_row_id.slice(-8)}` : c.viirs_row_id}
                      </span>
                    </td>
                    <td><strong>{c.distance_km.toFixed(3)} km</strong></td>
                    <td>{c.time_diff_minutes.toFixed(1)} min</td>
                    <td>{c.footprint_radius_sum_km.toFixed(3)} km</td>
                    <td>
                      <span style={{ fontSize: "11px" }}>{c.modis_satellite} / {c.viirs_satellite}</span>
                    </td>
                    <td>
                      <span style={{ fontSize: "11px" }}>
                        M: {c.modis_frp_mw != null ? `${c.modis_frp_mw}MW` : "—"} · V: {c.viirs_frp_mw != null ? `${c.viirs_frp_mw}MW` : "—"}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          background: "#0369a1",
                          color: "#f0f9ff",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 600,
                        }}
                      >
                        Profile {profile} Satisfied
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bottom-note">
        <div className="note-icon">i</div>
        <div>
          <strong>How to interpret candidate pairs</strong>
          <p>
            A candidate pair represents a possible spatial-temporal association between two satellite detection records under footprint geometry (distance &le; r<sub>MODIS</sub> + r<sub>VIIRS</sub> + spatial buffer).
            It does not establish that both sensors observed the same isolated physical fire. Records without candidates remain coverage-unverified.
          </p>
        </div>
      </section>
    </div>
  );
}
