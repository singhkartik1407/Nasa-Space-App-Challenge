import { useEffect, useState, useMemo } from "react";
import MapGL, { NavigationControl, ScaleControl, Source, Layer, Popup } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { getMapDetections, type MapDetectionProperties } from "../lib/api/map";

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
  const [showModis, setShowModis] = useState(true);
  const [showViirs, setShowViirs] = useState(true);
  const [layersOpen, setLayersOpen] = useState(!compact);
  const [geojsonData, setGeojsonData] = useState<any>({
    type: "FeatureCollection",
    features: [],
  });
  const [loading, setLoading] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState<{
    longitude: number;
    latitude: number;
    properties: MapDetectionProperties;
  } | null>(null);

  // Fetch real detections whenever date/sensor filters change
  useEffect(() => {
    let active = true;
    setLoading(true);

    const startDate = filters?.start || "2024-03-01";
    const endDate = filters?.end || "2024-03-05";

    getMapDetections({
      startDate,
      endDate,
      sensor: filters?.sensor || "ALL",
      daynight: filters?.daynight || "ALL",
      limit: compact ? 200 : 500,
    })
      .then((data) => {
        if (active) {
          setGeojsonData(data);
        }
      })
      .catch((err) => {
        console.warn("Failed to fetch map detections:", err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filters?.start, filters?.end, filters?.sensor, filters?.daynight, compact]);

  // Count detections by sensor in current dataset
  const { modisCount, viirsCount } = useMemo(() => {
    let m = 0;
    let v = 0;
    (geojsonData.features || []).forEach((f: any) => {
      if (f.properties?.sensor === "MODIS") m++;
      else if (f.properties?.sensor === "VIIRS") v++;
    });
    return { modisCount: m, viirsCount: v };
  }, [geojsonData]);

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

  return (
    <div className={`fire-map ${compact ? "compact-map" : ""}`}>
      <MapGL
        initialViewState={{
          longitude: 82,
          latitude: 22,
          zoom: 3,
        }}
        mapStyle={mapStyle}
        onLoad={(event) => {
          event.target.fitBounds(
            [[67.5, 6.5], [98, 37.5]],
            { padding: 10, duration: 0, maxZoom: 3 }
          );
        }}
        onClick={(event) => {
          const feature = event.features?.[0];
          if (feature && feature.geometry.type === "Point") {
            const coords = (feature.geometry as any).coordinates;
            setSelectedFeature({
              longitude: coords[0],
              latitude: coords[1],
              properties: feature.properties as any,
            });
          } else {
            setSelectedFeature(null);
          }
        }}
        interactiveLayerIds={["modis-layer", "viirs-layer"]}
        attributionControl={{ compact: true }}
        dragRotate={false}
        touchPitch={false}
        minZoom={2}
        maxZoom={18}
      >
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-right" />

        <Source id="fire-hotspots" type="geojson" data={geojsonData}>
          <Layer {...modisLayerStyle} />
          <Layer {...viirsLayerStyle} />
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
            <div style={{ fontSize: "12px", lineHeight: "1.4", padding: "4px" }}>
              <div style={{ fontWeight: 700, color: selectedFeature.properties.sensor === "MODIS" ? "#ea580c" : "#2563eb", marginBottom: "3px" }}>
                {selectedFeature.properties.sensor} Detection ({selectedFeature.properties.satellite})
              </div>
              <div><strong>Time (UTC):</strong> {selectedFeature.properties.acquisition_datetime}</div>
              <div><strong>Coords:</strong> {selectedFeature.latitude.toFixed(4)}, {selectedFeature.longitude.toFixed(4)}</div>
              <div><strong>FRP:</strong> {selectedFeature.properties.frp != null ? `${selectedFeature.properties.frp} MW` : "N/A"}</div>
              <div><strong>Confidence:</strong> {selectedFeature.properties.confidence ?? "N/A"}</div>
              <div><strong>Day/Night:</strong> {selectedFeature.properties.daynight === "D" ? "Day" : "Night"}</div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "3px", wordBreak: "break-all" }}>
                ID: {selectedFeature.properties.row_id}
              </div>
            </div>
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
            <span>MODIS ({modisCount})</span>
          </label>

          <label className="map-layer-toggle">
            <input
              type="checkbox"
              checked={showViirs}
              onChange={(e) => setShowViirs(e.target.checked)}
            />
            <span className="sensor-symbol viirs-symbol" />
            <span>VIIRS SNPP ({viirsCount})</span>
          </label>

          <div className="map-layer-message">
            {loading
              ? "Loading hotspot detections..."
              : showModis || showViirs
                ? `Showing ${modisCount + viirsCount} observations in viewport`
                : "All detection layers hidden"}
          </div>
        </div>
      )}
    </div>
  );
}
