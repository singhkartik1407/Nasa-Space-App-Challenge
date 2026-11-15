import { useEffect, useState } from "react";
import { getYearlyMonthlyActivity } from "../lib/api/activity";
import type { MonthlyActivity } from "../lib/api/types";

interface ActivityCalendarProps {
  year?: number;
}

export default function ActivityCalendar({
  year: initialYear = 2024,
}: ActivityCalendarProps) {
  const [year, setYear] = useState(initialYear);
  const [monthlyData, setMonthlyData] = useState<Record<number, MonthlyActivity>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const months = [
    { num: 1, name: "January" },
    { num: 2, name: "February" },
    { num: 3, name: "March" },
    { num: 4, name: "April" },
    { num: 5, name: "May" },
    { num: 6, name: "June" },
    { num: 7, name: "July" },
    { num: 8, name: "August" },
    { num: 9, name: "September" },
    { num: 10, name: "October" },
    { num: 11, name: "November" },
    { num: 12, name: "December" },
  ];

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getYearlyMonthlyActivity(year)
      .then((items) => {
        if (active) {
          const map: Record<number, MonthlyActivity> = {};
          items.forEach((item) => {
            map[item.month] = item;
          });
          setMonthlyData(map);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load calendar activity.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [year]);

  return (
    <section className="panel calendar-panel">
      <div className="panel-header">
        <div>
          <h3>Activity calendar</h3>
          <p>Monthly detection activity across {year} (UTC canonical grouping)</p>
        </div>

        <div className="calendar-year-control">
          <button
            type="button"
            onClick={() => setYear((value) => Math.max(2012, value - 1))}
            aria-label="Previous year"
            disabled={year <= 2012}
          >
            −
          </button>
          <span>{year}</span>
          <button
            type="button"
            onClick={() => setYear((value) => Math.min(2026, value + 1))}
            aria-label="Next year"
            disabled={year >= 2026}
          >
            +
          </button>
        </div>
      </div>

      {error ? (
        <div className="activity-empty activity-error" role="alert">
          {error}
        </div>
      ) : (
        <div className="calendar-month-labels">
          {months.map(({ num, name }) => {
            const data = monthlyData[num];
            const hasData = data && (data.modis_detections != null || data.viirs_detections != null);
            const totalObs = (data?.modis_detections || 0) + (data?.viirs_detections || 0);

            return (
              <div className={`calendar-month ${hasData ? "has-data" : ""}`} key={name}>
                <div className="calendar-month-header">
                  <span className="month-name">{name}</span>
                  {hasData && (
                    <span className="month-obs-tag">
                      {totalObs.toLocaleString()} obs
                    </span>
                  )}
                </div>

                {loading ? (
                  <div className="calendar-no-data">Loading...</div>
                ) : hasData ? (
                  <div className="calendar-sensor-breakdown">
                    <div className="sensor-row modis-row">
                      <span>MODIS</span>
                      <strong>{(data.modis_detections || 0).toLocaleString()}</strong>
                    </div>
                    <div className="sensor-row viirs-row">
                      <span>VIIRS</span>
                      <strong>{(data.viirs_detections || 0).toLocaleString()}</strong>
                    </div>
                  </div>
                ) : year === 2026 && num > 7 ? (
                  <div className="calendar-no-data muted">
                    Outside observation window
                  </div>
                ) : (
                  <div className="calendar-no-data">
                    No detections recorded
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <p className="calendar-disclaimer">
        Observation days and detection counts reflect satellite overpasses over India during {year}.
        Absence of recorded detections does not guarantee absence of fire or complete sensor coverage.
      </p>
    </section>
  );
}
