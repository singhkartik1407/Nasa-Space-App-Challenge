import { useEffect, useState, useMemo } from "react";
import MapGL, { NavigationControl, ScaleControl, Source, Layer, Popup } from "react-map-gl/maplibre";
import * as maplibregl from "maplibre-gl";
import maplibreglWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  getMapAggregation,
  getMapDetections,
  type MapDetectionProperties,
  type MapAggregateCellProperties,
} from "../lib/api/map";
import GoogleFireMap from "./GoogleFireMap";

// Explicitly configure the web worker URL via Vite's asset URL resolution.
maplibregl.setWorkerUrl(maplibreglWorkerUrl);

const mapStyle = {
  version: 8 as const,
  sources: {
    openstreetmap: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "openstreetmap-layer",
      type: "raster" as const,
      source: "openstreetmap",
    },
  ],
};

interface FireMapProps {
  compact?: boolean;
  filters?: {
    start?: string;
    end?: string;
    sensor?: string;
    daynight?: string;
  };
}

export default function FireMap({ compact = false, filters }: FireMapProps) {
  const [basemap, setBasemap] = useState<"maplibre" | "google">("maplibre");
  const [showModis, setShowModis] = useState(true);
  const [showViirs, setShowViirs] = useState(true);
  const [layersOpen, setLayersOpen] = useState(!compact);
  const [currentZoom, setCurrentZoom] = useState(3);
  const [geojsonData, setGeojsonData] = useState<any>({
    type: "FeatureCollection",
    features: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedFeature, setSelectedFeature] = useState<{
    longitude: number;
    latitude: number;
    isAggregate: boolean;
    detectionProps?: MapDetectionProperties;
    aggregateProps?: MapAggregateCellProperties;
  } | null>(null);

  const isAggregateMode = currentZoom < 10;

  // Fetch data: multi-resolution aggregation when zoom < 10, individual detections when zoom >= 10
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const startDate = filters?.start || "2012-01-21";
    const endDate = filters?.end || "2026-07-14";
    const sensor = filters?.sensor || "ALL";
    const daynight = filters?.daynight || "ALL";

    if (isAggregateMode) {
      const resDeg = currentZoom < 6 ? 0.5 : 0.15;
      getMapAggregation({
        startDate,
        endDate,
        sensor,
        daynight,
        resolutionDeg: resDeg,
        zoom: currentZoom,
      })
        .then((data) => {
          if (active) {
            setGeojsonData(data);
          }
        })
        .catch((err) => {
          if (active) {
            setError(err instanceof Error ? err.message : "Failed to load spatial aggregation");
          }
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    } else {
      getMapDetections({
        startDate,
        endDate,
        sensor,
        daynight,
        limit: compact ? 200 : 500,
      })
        .then((data) => {
          if (active) {
            setGeojsonData(data);
          }
        })
        .catch((err) => {
          if (active) {
            setError(err instanceof Error ? err.message : "Failed to load individual detections");
          }
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }

    return () => {
      active = false;
    };
  }, [
    filters?.start,
    filters?.end,
    filters?.sensor,
    filters?.daynight,
    currentZoom,
    isAggregateMode,
    compact,
  ]);

  // Aggregate layer styles (Zoom < 10)
  const aggregateLayerStyle = useMemo(
    () => ({
      id: "aggregate-hotspot-layer",
      type: "circle" as const,
      paint: {
        "circle-color": [
          "case",
          [">", ["get", "modis_count"], 0],
          [
            "case",
            [">", ["get", "viirs_count"], 0],
            "#8b5cf6", // Co-observed purple
            "#f97316", // MODIS orange
          ],
          "#3b82f6", // VIIRS blue
        ] as any,
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["get", "total_count"],
          1,
          compact ? 3 : 4,
          50,
          compact ? 5 : 7,
          500,
          compact ? 8 : 11,
          5000,
          compact ? 12 : 16,
          50000,
          compact ? 16 : 22,
        ] as any,
        "circle-opacity": 0.82,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
      },
      layout: {
        visibility: showModis || showViirs ? ("visible" as const) : ("none" as const),
      },
    }),
    [showModis, showViirs, compact]
  );

  // Individual detection styles (Zoom >= 10)
  const modisLayerStyle = useMemo(
    () => ({
      id: "modis-layer",
      type: "circle" as const,
      filter: ["==", ["get", "sensor"], "MODIS"] as any,
      paint: {
        "circle-color": "#f97316",
        "circle-radius": compact ? 3.5 : 5,
        "circle-opacity": 0.85,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
      },
      layout: {
        visibility: showModis ? ("visible" as const) : ("none" as const),
      },
    }),
    [showModis, compact]
  );

  const viirsLayerStyle = useMemo(
    () => ({
      id: "viirs-layer",
      type: "circle" as const,
      filter: ["==", ["get", "sensor"], "VIIRS"] as any,
      paint: {
        "circle-color": "#3b82f6",
        "circle-radius": compact ? 2.5 : 4,
        "circle-opacity": 0.85,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
      },
      layout: {
        visibility: showViirs ? ("visible" as const) : ("none" as const),
      },
    }),
    [showViirs, compact]
  );

  // Count detections in current dataset
  const { totalObservations, modisCount, viirsCount } = useMemo(() => {
    let tot = 0;
    let m = 0;
    let v = 0;
    if (isAggregateMode) {
      (geojsonData.features || []).forEach((f: any) => {
        tot += f.properties?.total_count || 0;
        m += f.properties?.modis_count || 0;
        v += f.properties?.viirs_count || 0;
      });
    } else {
      (geojsonData.features || []).forEach((f: any) => {
        tot++;
        if (f.properties?.sensor === "MODIS") m++;
        else if (f.properties?.sensor === "VIIRS") v++;
      });
    }
    return { totalObservations: tot, modisCount: m, viirsCount: v };
  }, [geojsonData, isAggregateMode]);

  // If user switched to Google Maps
  if (basemap === "google") {
    return (
      <div className={`fire-map ${compact ? "compact-map" : ""}`}>
        <div
          style={{
            position: "absolute",
            top: "12px",
            right: "12px",
            zIndex: 20,
            display: "flex",
            gap: "4px",
            background: "rgba(15, 23, 42, 0.9)",
            padding: "4px",
            borderRadius: "6px",
            border: "1px solid #334155",
          }}
        >
          <button
            type="button"
            onClick={() => setBasemap("maplibre")}
            style={{
              background: "transparent",
              color: "#94a3b8",
              border: "none",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
              borderRadius: "4px",
            }}
          >
            MapLibre (OSM)
          </button>
          <button
            type="button"
            onClick={() => setBasemap("google")}
            style={{
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
              fontWeight: 600,
              borderRadius: "4px",
            }}
          >
            Google Maps (deck.gl)
          </button>
        </div>
        <GoogleFireMap
          compact={compact}
          filters={filters}
          onSwitchToMapLibre={() => setBasemap("maplibre")}
        />
      </div>
    );
  }

  return (
    <div className={`fire-map ${compact ? "compact-map" : ""}`}>
      {/* Basemap Switcher Pill */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: compact ? "44px" : "50px",
          zIndex: 10,
          display: "flex",
          gap: "4px",
          background: "rgba(15, 23, 42, 0.9)",
          padding: "3px 6px",
          borderRadius: "6px",
          border: "1px solid #334155",
        }}
      >
        <button
          type="button"
          onClick={() => setBasemap("maplibre")}
          style={{
            background: "#3b82f6",
            color: "#fff",
            border: "none",
            padding: "3px 7px",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
            borderRadius: "4px",
          }}
        >
          MapLibre (OSM)
        </button>
        <button
          type="button"
          onClick={() => setBasemap("google")}
          style={{
            background: "transparent",
            color: "#94a3b8",
            border: "none",
            padding: "3px 7px",
            fontSize: "11px",
            fontWeight: 400,
            cursor: "pointer",
            borderRadius: "4px",
          }}
        >
          Google Maps (deck.gl)
        </button>
      </div>

      {/* Resolution & Granularity Badge */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          left: "12px",
          zIndex: 10,
          background: "rgba(15, 23, 42, 0.9)",
          color: "#f8fafc",
          padding: "5px 10px",
          borderRadius: "6px",
          border: "1px solid #334155",
          fontSize: "11px",
          pointerEvents: "none",
        }}
      >
        <span style={{ color: "#38bdf8", fontWeight: 600 }}>
          {isAggregateMode
            ? currentZoom < 6
              ? "National Hotspot Grid (0.5°)"
              : "Regional Hotspot Grid (0.15°)"
            : "Individual Detections"}
        </span>
        {" · "}
        <span>
          {isAggregateMode
            ? `${(geojsonData.features || []).length} cells · ${totalObservations.toLocaleString()} obs represented`
            : `${modisCount + viirsCount} spots shown`}
        </span>
      </div>

      <MapGL
        mapLib={maplibregl}
        initialViewState={{
          longitude: 82,
          latitude: 22,
          zoom: 3,
        }}
        mapStyle={mapStyle}
        onMove={(event) => {
          const z = event.viewState.zoom;
          if (Math.abs(z - currentZoom) >= 0.5) {
            setCurrentZoom(z);
          }
        }}
        onLoad={(event) => {
          event.target.fitBounds(
            [
              [67.5, 6.5],
              [98, 37.5],
            ],
            { padding: 10, duration: 0, maxZoom: 3 }
          );
        }}
        onClick={(event) => {
          const feature = event.features?.[0];
          if (feature && feature.geometry.type === "Point") {
            const coords = (feature.geometry as any).coordinates;
            const props = feature.properties as any;
            if (props.cell_id != null) {
              setSelectedFeature({
                longitude: coords[0],
                latitude: coords[1],
                isAggregate: true,
                aggregateProps: props,
              });
            } else {
              setSelectedFeature({
                longitude: coords[0],
                latitude: coords[1],
                isAggregate: false,
                detectionProps: props,
              });
            }
          } else {
            setSelectedFeature(null);
          }
        }}
        interactiveLayerIds={
          isAggregateMode ? ["aggregate-hotspot-layer"] : ["modis-layer", "viirs-layer"]
        }
        attributionControl={{ compact: true }}
        dragRotate={false}
        touchPitch={false}
        minZoom={2}
        maxZoom={18}
      >
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-right" />

        <Source id="fire-hotspots" type="geojson" data={geojsonData}>
          {isAggregateMode ? (
            <Layer {...aggregateLayerStyle} />
          ) : (
            <>
              <Layer {...modisLayerStyle} />
              <Layer {...viirsLayerStyle} />
            </>
          )}
        </Source>

        {selectedFeature && (
          <Popup
            longitude={selectedFeature.longitude}
            latitude={selectedFeature.latitude}
            onClose={() => setSelectedFeature(null)}
            closeOnClick={false}
            anchor="bottom"
            className="detection-map-popup"
          >
            {selectedFeature.isAggregate && selectedFeature.aggregateProps ? (
              <div style={{ fontSize: "12px", lineHeight: "1.4", padding: "4px" }}>
                <div style={{ fontWeight: 700, color: "#8b5cf6", marginBottom: "3px" }}>
                  Spatial Hotspot Cell ({selectedFeature.aggregateProps.resolution_deg}°)
                </div>
                <div>
                  <strong>Centroid:</strong> {selectedFeature.latitude.toFixed(2)}°N,{" "}
                  {selectedFeature.longitude.toFixed(2)}°E
                </div>
                <div>
                  <strong>Total Observations:</strong>{" "}
                  {selectedFeature.aggregateProps.total_count.toLocaleString()}
                </div>
                <div style={{ color: "#ea580c" }}>
                  <strong>MODIS:</strong> {selectedFeature.aggregateProps.modis_count.toLocaleString()}{" "}
                  (avg {selectedFeature.aggregateProps.modis_avg_frp} MW)
                </div>
                <div style={{ color: "#2563eb" }}>
                  <strong>VIIRS:</strong> {selectedFeature.aggregateProps.viirs_count.toLocaleString()}{" "}
                  (avg {selectedFeature.aggregateProps.viirs_avg_frp} MW)
                </div>
                <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px" }}>
                  FRP values remain instrument-separated.
                </div>
              </div>
            ) : selectedFeature.detectionProps ? (
              <div style={{ fontSize: "12px", lineHeight: "1.4", padding: "4px" }}>
                <div
                  style={{
                    fontWeight: 700,
                    color:
                      selectedFeature.detectionProps.sensor === "MODIS" ? "#ea580c" : "#2563eb",
                    marginBottom: "3px",
                  }}
                >
                  {selectedFeature.detectionProps.sensor} Detection (
                  {selectedFeature.detectionProps.satellite})
                </div>
                <div>
                  <strong>Time (UTC):</strong>{" "}
                  {selectedFeature.detectionProps.acquisition_datetime}
                </div>
                <div>
                  <strong>Coords:</strong> {selectedFeature.latitude.toFixed(4)},{" "}
                  {selectedFeature.longitude.toFixed(4)}
                </div>
                <div>
                  <strong>FRP:</strong>{" "}
                  {selectedFeature.detectionProps.frp != null
                    ? `${selectedFeature.detectionProps.frp} MW`
                    : "N/A"}
                </div>
                <div>
                  <strong>Confidence:</strong> {selectedFeature.detectionProps.confidence ?? "N/A"}
                </div>
                <div>
                  <strong>Day/Night:</strong>{" "}
                  {selectedFeature.detectionProps.daynight === "D" ? "Day" : "Night"}
                </div>
                <div
                  style={{
                    fontSize: "10px",
                    color: "#64748b",
                    marginTop: "3px",
                    wordBreak: "break-all",
                  }}
                >
                  ID: {selectedFeature.detectionProps.row_id}
                </div>
              </div>
            ) : null}
          </Popup>
        )}
      </MapGL>

      {compact && (
        <button
          type="button"
          className="compact-layers-button"
          onClick={() => setLayersOpen((open) => !open)}
          aria-expanded={layersOpen}
        >
          <span>☷</span>
          Layers
          <span className="compact-layers-chevron">{layersOpen ? "−" : "+"}</span>
        </button>
      )}

      {layersOpen && (
        <div className="map-layer-panel">
          <div className="map-layer-title">SATELLITE LAYERS</div>

          <label className="map-layer-toggle">
            <input
              type="checkbox"
              checked={showModis}
              onChange={(e) => setShowModis(e.target.checked)}
            />
            <span className="sensor-symbol modis-symbol" />
            <span>MODIS ({modisCount.toLocaleString()})</span>
          </label>

          <label className="map-layer-toggle">
            <input
              type="checkbox"
              checked={showViirs}
              onChange={(e) => setShowViirs(e.target.checked)}
            />
            <span className="sensor-symbol viirs-symbol" />
            <span>VIIRS SNPP ({viirsCount.toLocaleString()})</span>
          </label>

          <div className="map-layer-message">
            {loading
              ? "Loading hotspot observations..."
              : error
                ? `Error: ${error}`
                : isAggregateMode
                  ? `Visualizing ${(geojsonData.features || []).length} aggregated grid cells (${totalObservations.toLocaleString()} observations)`
                  : `Showing ${modisCount + viirsCount} individual detections in viewport`}
          </div>

          {isAggregateMode && (
            <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "4px", lineHeight: "1.3" }}>
              Zoom in beyond level 10 to inspect individual sensor detection dots.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
