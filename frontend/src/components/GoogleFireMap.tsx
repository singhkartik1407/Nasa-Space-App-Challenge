import { useEffect, useRef, useState, useMemo } from "react";
import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { GoogleMapsOverlay } from "@deck.gl/google-maps";
import { ScatterplotLayer } from "@deck.gl/layers";
import {
  getMapAggregation,
  getMapDetections,
  type MapAggregateFeature,
  type MapDetectionFeature,
} from "../lib/api/map";

interface GoogleFireMapProps {
  compact?: boolean;
  filters?: {
    start?: string;
    end?: string;
    sensor?: string;
    daynight?: string;
  };
  onSwitchToMapLibre?: () => void;
}

export default function GoogleFireMap({
  compact = false,
  filters,
  onSwitchToMapLibre,
}: GoogleFireMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlayRef = useRef<GoogleMapsOverlay | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState(4);
  const [aggregateFeatures, setAggregateFeatures] = useState<MapAggregateFeature[]>([]);
  const [individualFeatures, setIndividualFeatures] = useState<MapDetectionFeature[]>([]);
  const [selectedCell, setSelectedCell] = useState<MapAggregateFeature["properties"] | null>(null);
  const [selectedDetection, setSelectedDetection] = useState<MapDetectionFeature["properties"] | null>(null);
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(null);

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
  const mapId = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || undefined;

  // Initialize Google Map and deck.gl overlay
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (!apiKey) {
      setError("Google Maps API key not found in environment configuration.");
      setLoading(false);
      return;
    }

    let isMounted = true;
    try {
      setOptions({
        key: apiKey,
        v: "weekly",
        ...(mapId ? { mapIds: [mapId] } : {}),
      });
    } catch {
      // Ignore if setOptions was already called
    }

    importLibrary("maps")
      .then((mapsLib: any) => {
        if (!isMounted || !mapContainerRef.current) return;

        const MapConstructor = mapsLib.Map;
        const mapInstance = new MapConstructor(mapContainerRef.current, {
          center: { lat: 22.0, lng: 82.0 },
          zoom: compact ? 3 : 4,
          mapId: mapId || undefined,
          mapTypeId: "roadmap",
          zoomControl: true,
          streetViewControl: false,
          fullscreenControl: !compact,
          mapTypeControl: false,
        });

        mapRef.current = mapInstance;

        mapInstance.addListener("zoom_changed", () => {
          const z = mapInstance.getZoom();
          if (typeof z === "number") setZoomLevel(z);
        });

        const overlay = new GoogleMapsOverlay({
          layers: [],
        });
        overlay.setMap(mapInstance);
        overlayRef.current = overlay;

        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        const msg = err instanceof Error ? err.message : "Failed to load Google Maps JS API";
        setError(msg);
        setLoading(false);
      });

    return () => {
      isMounted = false;
      if (overlayRef.current) {
        overlayRef.current.setMap(null);
        overlayRef.current = null;
      }
      mapRef.current = null;
    };
  }, [apiKey, mapId, compact]);

  // Fetch data based on zoom and filters
  useEffect(() => {
    let active = true;
    const startDate = filters?.start || "2012-01-21";
    const endDate = filters?.end || "2026-07-14";
    const sensor = filters?.sensor || "ALL";
    const daynight = filters?.daynight || "ALL";

    if (zoomLevel < 10) {
      // Zoom 1 & 2: Multi-resolution spatial aggregation
      const resDeg = zoomLevel < 6 ? 0.5 : 0.15;
      getMapAggregation({
        startDate,
        endDate,
        sensor,
        daynight,
        resolutionDeg: resDeg,
        zoom: zoomLevel,
      })
        .then((res) => {
          if (active) {
            setAggregateFeatures(res.features || []);
            setIndividualFeatures([]);
          }
        })
        .catch((err) => {
          if (active) console.error("GoogleFireMap aggregation error:", err);
        });
    } else {
      // Zoom 3: Local individual detections
      getMapDetections({
        startDate,
        endDate,
        sensor,
        daynight,
        limit: 500,
      })
        .then((res) => {
          if (active) {
            setIndividualFeatures(res.features || []);
            setAggregateFeatures([]);
          }
        })
        .catch((err) => {
          if (active) console.error("GoogleFireMap detections error:", err);
        });
    }

    return () => {
      active = false;
    };
  }, [filters?.start, filters?.end, filters?.sensor, filters?.daynight, zoomLevel]);

  // Update deck.gl overlay layers
  useEffect(() => {
    if (!overlayRef.current) return;

    const layers: any[] = [];

    if (aggregateFeatures.length > 0) {
      layers.push(
        new ScatterplotLayer<MapAggregateFeature>({
          id: "google-aggregate-layer",
          data: aggregateFeatures,
          pickable: true,
          opacity: 0.8,
          stroked: true,
          filled: true,
          radiusScale: 1,
          radiusMinPixels: 4,
          radiusMaxPixels: 24,
          lineWidthMinPixels: 1,
          getPosition: (d: MapAggregateFeature) => [
            d.geometry.coordinates[0],
            d.geometry.coordinates[1],
          ],
          getRadius: (d: MapAggregateFeature) => {
            const count = d.properties.total_count;
            return Math.min(25000, Math.max(4000, Math.sqrt(count) * 800));
          },
          getFillColor: (d: MapAggregateFeature) => {
            const p = d.properties;
            if (p.modis_count > 0 && p.viirs_count === 0) {
              return [249, 115, 22, 200]; // MODIS orange
            }
            if (p.viirs_count > 0 && p.modis_count === 0) {
              return [59, 130, 246, 200]; // VIIRS blue
            }
            return [139, 92, 246, 220]; // Co-observed purple
          },
          getLineColor: [255, 255, 255, 200],
          onClick: (info: any) => {
            if (info.object) {
              setSelectedCell(info.object.properties);
              setSelectedDetection(null);
              setPopupPos({ x: info.x, y: info.y });
            } else {
              setSelectedCell(null);
            }
          },
        })
      );
    } else if (individualFeatures.length > 0) {
      layers.push(
        new ScatterplotLayer<MapDetectionFeature>({
          id: "google-detections-layer",
          data: individualFeatures,
          pickable: true,
          opacity: 0.85,
          stroked: true,
          filled: true,
          radiusScale: 1,
          radiusMinPixels: 3,
          radiusMaxPixels: 8,
          lineWidthMinPixels: 1,
          getPosition: (d: MapDetectionFeature) => [
            d.geometry.coordinates[0],
            d.geometry.coordinates[1],
          ],
          getRadius: 300,
          getFillColor: (d: MapDetectionFeature) => {
            return d.properties.sensor === "MODIS"
              ? [249, 115, 22, 220]
              : [59, 130, 246, 220];
          },
          getLineColor: [255, 255, 255, 200],
          onClick: (info: any) => {
            if (info.object) {
              setSelectedDetection(info.object.properties);
              setSelectedCell(null);
              setPopupPos({ x: info.x, y: info.y });
            } else {
              setSelectedDetection(null);
            }
          },
        })
      );
    }

    overlayRef.current.setProps({ layers });
  }, [aggregateFeatures, individualFeatures]);

  const totalObs = useMemo(() => {
    if (aggregateFeatures.length > 0) {
      return aggregateFeatures.reduce((acc, f) => acc + f.properties.total_count, 0);
    }
    return individualFeatures.length;
  }, [aggregateFeatures, individualFeatures]);

  if (error) {
    return (
      <div
        className="google-map-fallback"
        style={{
          padding: "24px",
          background: "#0f172a",
          color: "#f8fafc",
          borderRadius: "8px",
          textAlign: "center",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "12px",
        }}
      >
        <div style={{ color: "#f87171", fontWeight: 600 }}>Google Maps / deck.gl Notice</div>
        <p style={{ color: "#94a3b8", fontSize: "13px", maxWidth: "440px" }}>
          {error}. MapLibre with OpenStreetMap raster tiles is available as the stable primary basemap.
        </p>
        {onSwitchToMapLibre && (
          <button
            type="button"
            onClick={onSwitchToMapLibre}
            style={{
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "6px 14px",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Switch to MapLibre (OSM)
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: "360px" }}>
      <div ref={mapContainerRef} style={{ width: "100%", height: "100%", minHeight: "360px" }} />

      {loading && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            background: "rgba(15, 23, 42, 0.85)",
            color: "#38bdf8",
            padding: "8px 16px",
            borderRadius: "4px",
            fontSize: "13px",
            fontWeight: 500,
            pointerEvents: "none",
          }}
        >
          Loading Google Maps & deck.gl overlay...
        </div>
      )}

      {/* Mode and scale indicator */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          left: "12px",
          background: "rgba(15, 23, 42, 0.9)",
          color: "#f8fafc",
          padding: "6px 12px",
          borderRadius: "6px",
          fontSize: "12px",
          border: "1px solid #334155",
          zIndex: 10,
        }}
      >
        <span style={{ fontWeight: 600, color: "#38bdf8" }}>deck.gl WebGL Layer</span> ·{" "}
        {zoomLevel < 6
          ? `National Hotspot Grid (0.5° · ${aggregateFeatures.length} cells · ${totalObs.toLocaleString()} obs)`
          : zoomLevel < 10
            ? `Regional Hotspot Grid (0.15° · ${aggregateFeatures.length} cells)`
            : `Individual Detections (Local view · ${individualFeatures.length} spots)`}
      </div>

      {/* Aggregate cell popup */}
      {selectedCell && popupPos && (
        <div
          style={{
            position: "absolute",
            left: `${popupPos.x + 10}px`,
            top: `${popupPos.y + 10}px`,
            background: "#0f172a",
            color: "#f8fafc",
            padding: "10px 14px",
            borderRadius: "6px",
            boxShadow: "0 10px 15px -3px rgba(0,0,0,0.5)",
            border: "1px solid #334155",
            fontSize: "12px",
            zIndex: 100,
            maxWidth: "280px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <strong style={{ color: "#38bdf8" }}>Hotspot Cell ({selectedCell.resolution_deg}°)</strong>
            <button
              onClick={() => setSelectedCell(null)}
              style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
            >
              ✕
            </button>
          </div>
          <div>Centroid: {selectedCell.latitude.toFixed(2)}°N, {selectedCell.longitude.toFixed(2)}°E</div>
          <div>Total Observations: <strong>{selectedCell.total_count.toLocaleString()}</strong></div>
          <div style={{ color: "#f97316" }}>MODIS: {selectedCell.modis_count.toLocaleString()} (avg {selectedCell.modis_avg_frp} MW)</div>
          <div style={{ color: "#3b82f6" }}>VIIRS: {selectedCell.viirs_count.toLocaleString()} (avg {selectedCell.viirs_avg_frp} MW)</div>
          <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px" }}>
            FRP values remain instrument-separated.
          </div>
        </div>
      )}

      {/* Individual detection popup */}
      {selectedDetection && popupPos && (
        <div
          style={{
            position: "absolute",
            left: `${popupPos.x + 10}px`,
            top: `${popupPos.y + 10}px`,
            background: "#0f172a",
            color: "#f8fafc",
            padding: "10px 14px",
            borderRadius: "6px",
            boxShadow: "0 10px 15px -3px rgba(0,0,0,0.5)",
            border: "1px solid #334155",
            fontSize: "12px",
            zIndex: 100,
            maxWidth: "280px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <strong style={{ color: selectedDetection.sensor === "MODIS" ? "#f97316" : "#3b82f6" }}>
              {selectedDetection.sensor} Detection
            </strong>
            <button
              onClick={() => setSelectedDetection(null)}
              style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
            >
              ✕
            </button>
          </div>
          <div>Satellite: {selectedDetection.satellite}</div>
          <div>Time (UTC): {selectedDetection.acquisition_datetime}</div>
          <div>FRP: {selectedDetection.frp != null ? `${selectedDetection.frp} MW` : "N/A"}</div>
          <div>Confidence: {selectedDetection.confidence ?? "N/A"}</div>
          <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px", wordBreak: "break-all" }}>
            ID: {selectedDetection.row_id}
          </div>
        </div>
      )}
    </div>
  );
}
