import { useEffect, useState } from "react";
import { getMetadata, getSystemReadiness } from "../lib/api/metadata";
import type { MetadataResponse, SystemReadiness } from "../lib/api/types";

export default function DataSources() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.all([getMetadata(), getSystemReadiness()])
      .then(([metaData, readyData]) => {
        if (active) {
          setMetadata(metaData);
          setReadiness(readyData);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load data sources metadata.");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const sources = [
    {
      name: "MODIS Terra",
      sensor: "MODIS",
      platform: "Terra",
      collection: "Collection 6.1",
      period: metadata ? `${metadata.dataset_window.start_date} – ${metadata.dataset_window.end_date}` : "Jan 21, 2012 – Jul 14, 2026",
      records: readiness ? `${readiness.modis_total_rows.toLocaleString()} MODIS records` : "1,232,096 MODIS records",
      status: readiness?.ready ? "Live Parquet Connected" : "Connection pending",
    },
    {
      name: "MODIS Aqua",
      sensor: "MODIS",
      platform: "Aqua",
      collection: "Collection 6.1",
      period: metadata ? `${metadata.dataset_window.start_date} – ${metadata.dataset_window.end_date}` : "Jan 21, 2012 – Jul 14, 2026",
      records: readiness ? `${readiness.modis_total_rows.toLocaleString()} MODIS records` : "1,232,096 MODIS records",
      status: readiness?.ready ? "Live Parquet Connected" : "Connection pending",
    },
    {
      name: "Suomi-NPP VIIRS",
      sensor: "VIIRS",
      platform: "Suomi-NPP",
      collection: "Collection 2 (375 m)",
      period: "Jan 21, 2012 – Jul 10, 2026",
      records: readiness ? `${readiness.viirs_total_rows.toLocaleString()} VIIRS records` : "8,725,086 VIIRS records",
      status: readiness?.ready ? "Live Parquet Connected" : "Connection pending",
    },
  ];

  return (
    <div className="data-sources-content">
      <section className={`panel data-source-status ${readiness?.ready ? "ready" : "pending"}`}>
        <div className="data-source-status-icon">
          {readiness?.ready ? "✓" : "!"}
        </div>
        <div>
          <strong>{readiness?.ready ? "Backend Parquet Data Engine Connected" : "Connecting to Backend API..."}</strong>
          <p>
            {readiness?.ready
              ? `DuckDB query engine verified. Total 9,957,182 active fire observations across India common observation period (${readiness.modis_total_rows.toLocaleString()} MODIS + ${readiness.viirs_total_rows.toLocaleString()} VIIRS).`
              : error || "Waiting for backend response on http://127.0.0.1:8000."}
          </p>
        </div>
        <span className={`section-tag ${readiness?.ready ? "ready" : "pending"}`}>
          <span /> {readiness?.ready ? "LIVE DATA READY" : "PENDING"}
        </span>
      </section>

      <section className="data-source-grid">
        {sources.map((source) => (
          <article className="panel data-source-card" key={source.name}>
            <div className="data-source-card-top">
              <span className={`data-source-tag ${source.sensor.toLowerCase()}`}>
                {source.sensor}
              </span>
              <span className="data-source-platform">{source.platform}</span>
            </div>
            <h3>{source.name}</h3>
            <div className="data-source-detail">
              <span>Collection</span>
              <strong>{source.collection}</strong>
            </div>
            <div className="data-source-detail">
              <span>Common comparison period</span>
              <strong>{source.period}</strong>
            </div>
            <div className="data-source-detail">
              <span>Dataset records</span>
              <strong>{source.records}</strong>
            </div>
            <div className="data-source-connection">
              <span className="status-dot" style={{ background: readiness?.ready ? "#10b981" : "#f59e0b" }} />
              {source.status}
            </div>
          </article>
        ))}
      </section>

      <section className="bottom-note">
        <div className="note-icon">i</div>
        <div>
          <strong>Sensor data interpretation</strong>
          <p>
            MODIS and VIIRS use different confidence representations: MODIS confidence is numeric (0–100), while VIIRS uses categorical values (low, nominal, high).
            Their confidence values must not be merged into one scale.
          </p>
        </div>
      </section>
    </div>
  );
}
