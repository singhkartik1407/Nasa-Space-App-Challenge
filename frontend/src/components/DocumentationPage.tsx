const sections = [
  {
    title: "About FireScope",
    text: "FireScope is a frontend workspace for exploring satellite fire detection records across India. It provides tools for geographic exploration, activity analysis, sensor comparison, and candidate relationship inspection.",
  },
  {
    title: "Satellite datasets",
    text: "The project uses MODIS Collection 6.1 observations from Terra and Aqua, and Suomi-NPP VIIRS Collection 2 observations. The common comparison period is January 21, 2012 to July 14, 2026.",
  },
  {
    title: "Detection records",
    text: "A detection record is a satellite observation. Detection counts should not be interpreted as counts of unique physical fires.",
  },
  {
    title: "Candidate relationships",
    text: "Candidate pairs represent possible spatial-temporal relationships between MODIS and VIIRS records. They are not confirmed matches or proof that two observations represent the same physical fire.",
  },
  {
    title: "Sensor confidence",
    text: "MODIS confidence is represented numerically from 0 to 100. VIIRS confidence uses categorical values. These confidence systems should not be combined into a single scale.",
  },
  {
    title: "Fire radiative power",
    text: "FRP summaries should be reported separately for each sensor. MODIS and VIIRS FRP values should not simply be added together as if they were independent measurements.",
  },
  {
    title: "Data availability",
    text: "FireScope operates with live connectivity to the FastAPI backend and DuckDB analytical query engine, reading 9.95M NASA FIRMS active-fire records directly from common-period Parquet files across India. Validated candidate matching pairs are available for the audited March 2012 and March 2024 pilot periods.",
  },
];

export default function DocumentationPage() {
  return (
    <div className="documentation-content">
      <section className="panel documentation-intro">
        <span className="analytics-pending">PROJECT REFERENCE</span>
        <h3>FireScope documentation</h3>
        <p>
          An overview of the datasets, terminology, interpretation principles,
          and current data availability used throughout the application.
        </p>
      </section>

      <div className="documentation-sections">
        {sections.map((section, index) => (
          <article className="panel documentation-card" key={section.title}>
            <span className="documentation-number">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <h3>{section.title}</h3>
              <p>{section.text}</p>
            </div>
          </article>
        ))}
      </div>

      <section className="bottom-note">
        <div className="note-icon">i</div>
        <div>
          <strong>Scientific interpretation matters</strong>
          <p>
            Absence of a candidate relationship does not establish that a
            detection is false or that another sensor missed a fire.
          </p>
        </div>
      </section>
    </div>
  );
}
