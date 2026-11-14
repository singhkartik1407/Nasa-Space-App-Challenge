import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import type { DashboardFilters, MonthlyActivity } from "../lib/api/types";
import { getMonthlyActivity } from "../lib/api/activity";

interface Props {
  filters: DashboardFilters;
}

export default function ActivityChart({ filters }: Props) {
  const [items, setItems] = useState<MonthlyActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getMonthlyActivity(filters)
      .then((response) => {
        if (active) setItems(response.items);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load activity data.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    filters.start_date,
    filters.end_date,
    filters.sensor,
    filters.platform,
    filters.daynight,
    filters.metric,
  ]);

  const chartData = items.map((item) => ({
    name: `${item.year}-${String(item.month).padStart(2, "0")}`,
    MODIS: item.modis_detections ?? 0,
    VIIRS: item.viirs_detections ?? 0,
  }));

  return (
    <article className="panel activity-panel">
      <div className="panel-header">
        <div>
          <h3>Detection activity</h3>
          <p>Monthly satellite detection records (UTC)</p>
        </div>
        <span className="small-select">Monthly</span>
      </div>

      {loading ? (
        <div className="activity-empty">
          <span className="loading-spinner" />
          Loading activity data...
        </div>
      ) : error ? (
        <div className="activity-empty activity-error" role="alert">
          {error}
        </div>
      ) : items.length === 0 ? (
        <div className="activity-empty">
          <BarChart3 size={29} />
          <strong>Monthly data not available</strong>
          <span>Activity records will appear here when the monthly API data is connected.</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", height: "100%" }}>
          <div style={{ width: "100%", height: 220, minHeight: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} tickLine={false} />
                <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "6px", fontSize: "12px" }}
                  itemStyle={{ color: "#f8fafc" }}
                />
                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "6px" }} />
                <Bar dataKey="MODIS" fill="#f97316" radius={[4, 4, 0, 0]} />
                <Bar dataKey="VIIRS" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="activity-data-list">
            {items.map((item) => (
              <div key={`${item.year}-${item.month}`} className="activity-data-row">
                <strong>{item.year} / {String(item.month).padStart(2, "0")}</strong>
                <span>MODIS: {item.modis_detections?.toLocaleString() ?? "—"}</span>
                <span>VIIRS: {item.viirs_detections?.toLocaleString() ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
