$path = ".\src\App.tsx"
$code = Get-Content $path -Raw

$changes = @(
  @{
    Old = '<article className={`stat-card ${hidden ? "stat-muted" : ""}`} key={item.label}>'
    New = '<article role="button" tabIndex={hidden ? -1 : 0} onClick={() => { if (item.label.startsWith("MODIS")) changeSensor("MODIS"); else if (item.label.startsWith("VIIRS")) changeSensor("VIIRS"); }} className={`stat-card stat-clickable ${hidden ? "stat-muted" : ""} ${(item.label.startsWith("MODIS") && filters.sensor === "MODIS") || (item.label.startsWith("VIIRS") && filters.sensor === "VIIRS") ? "stat-selected" : ""}`} key={item.label}>'
  },
  @{
    Old = '<div className="chart-legend"><span className="legend-dot modis" /> MODIS <span className="legend-dot viirs" /> VIIRS</div>'
    New = '<div className="chart-legend">{filters.sensor !== "VIIRS" && <><span className="legend-dot modis" /> MODIS</>}{filters.sensor === "BOTH" && <span className="chart-legend-gap" />}{filters.sensor !== "MODIS" && <><span className="legend-dot viirs" /> VIIRS</>}</div>'
  },
  @{
    Old = '<div className="chart-bar modis-bar" style={{ height: `${height * .72}%` }} /><div className="chart-bar viirs-bar" style={{ height: `${height}%` }} />'
    New = '{filters.sensor !== "VIIRS" && <div className="chart-bar modis-bar" style={{ height: `${height * .72}%` }} />}{filters.sensor !== "MODIS" && <div className="chart-bar viirs-bar" style={{ height: `${height}%` }} />}' 
  }
)

foreach ($item in $changes) {
  if (-not $code.Contains($item.Old)) {
    Write-Host "Expected code section not found. Update cancelled." -ForegroundColor Red
    exit
  }
}

foreach ($item in $changes) {
  $code = $code.Replace($item.Old, $item.New)
}

Set-Content $path $code -Encoding UTF8

@(
  "",
  "/* Interactive KPI and sensor-aware chart */",
  ".stat-clickable { cursor: pointer; text-align: left; color: inherit; font: inherit; width: 100%; }",
  ".stat-clickable:hover { border-color: #60718d; transform: translateY(-2px); transition: .18s ease; }",
  ".stat-clickable:focus-visible { outline: 2px solid #f3a16a; outline-offset: 3px; }",
  ".stat-selected { border-color: #d28d5d; box-shadow: inset 0 0 0 1px #d28d5d33; }",
  ".chart-legend-gap { width: 8px; }",
  ".chart-legend { flex-wrap: wrap; }"
) | Add-Content ".\src\App.css" -Encoding UTF8

Write-Host "Dashboard update completed successfully!" -ForegroundColor Green
