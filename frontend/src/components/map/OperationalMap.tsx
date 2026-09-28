import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { Map, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RouteCandidate } from "../../api/types";
import { LoadingState } from "../ui/LoadingState";
import { MapControls } from "./MapControls";
import { MapLegend } from "./MapLegend";
import { antarcticView, offlineDarkPolarStyle } from "./mapStyles";
import type { OperationalLayer } from "./types";

const routeSourceId = "candidate-routes";
const selectedRouteSourceId = "selected-candidate-route";

// Standard Antarctic Polar coastline (simplified authentic landmass outline)
const ANTARCTICA_OUTLINE: [number, number][] = [
  // Antarctic Peninsula
  [-57, -63.5], [-59, -64.5], [-63, -65], [-64, -66], [-66, -68],
  [-68, -70], [-71, -73], [-75, -74],
  // Ronne-Filchner Ice Shelf
  [-60, -75], [-50, -78], [-42, -78], [-35, -76],
  // Queen Maud Land & Enderby Land
  [-20, -72], [-10, -70.5], [0, -70], [10, -69.5], [20, -70],
  [30, -69], [40, -68], [50, -67], [55, -66.5],
  // Amery Ice Shelf & Prydz Bay
  [65, -67.5], [70, -69], [75, -71], [72, -73], [76, -73.5],
  [80, -70], [85, -67.5],
  // Wilkes Land
  [95, -66.5], [110, -66], [125, -66], [135, -66.5], [145, -67],
  // Victoria Land & Ross Sea
  [155, -70], [165, -72], [170, -74],
  // Ross Ice Shelf
  [175, -78], [-175, -81], [-165, -83.5], [-155, -82], [-150, -79],
  // Marie Byrd Land
  [-145, -76], [-135, -74.5], [-125, -74], [-115, -74], [-105, -73.5],
  // Ellsworth Land / Bellingshausen Sea
  [-95, -73], [-85, -73.5], [-75, -73], [-68, -70],
  // Back to base of Peninsula
  [-62, -67], [-57, -63.5]
];

const MERIDIANS = [
  { lon: 0, label: "0°" },
  { lon: 45, label: "45°E" },
  { lon: 90, label: "90°E" },
  { lon: 135, label: "135°E" },
  { lon: 180, label: "180°" },
  { lon: -135, label: "135°W" },
  { lon: -90, label: "90°W" },
  { lon: -45, label: "45°W" },
];

const PARALLELS = [-80, -70, -60];

function projectPoint(lon: number, lat: number, zoom: number, pan: { x: number; y: number }) {
  const cx = 400 + pan.x;
  const cy = 300 + pan.y;
  const baseScale = 14;
  const scale = baseScale * zoom;
  const poleX = cx;
  const poleY = cy + 8 * scale;
  const delta = Math.max(0, 90 + lat);
  const theta = ((lon - 90) * Math.PI) / 180;
  return {
    x: poleX + delta * scale * Math.cos(theta),
    y: poleY + delta * scale * Math.sin(theta),
  };
}

function parseGeometry(geom: unknown): { type: "LineString"; coordinates: [number, number][] } | null {
  if (!geom) return null;
  let parsed = geom;
  if (typeof geom === "string") {
    try {
      parsed = JSON.parse(geom);
    } catch {
      return null;
    }
  }
  if (typeof parsed === "object" && parsed !== null) {
    const candidate = parsed as { type?: string; coordinates?: unknown };
    if (candidate.type === "LineString" && Array.isArray(candidate.coordinates)) {
      const validCoords = candidate.coordinates
        .filter(
          (pt) =>
            Array.isArray(pt) &&
            pt.length >= 2 &&
            Number.isFinite(Number(pt[0])) &&
            Number.isFinite(Number(pt[1]))
        )
        .map((pt) => [Number(pt[0]), Number(pt[1])] as [number, number]);
      if (validCoords.length >= 2) {
        return { type: "LineString", coordinates: validCoords };
      }
    }
  }
  return null;
}

function features(routes: RouteCandidate[]) {
  return {
    type: "FeatureCollection" as const,
    features: routes
      .map((route) => {
        const geom = parseGeometry(route?.geometry);
        if (!geom) return null;
        return {
          type: "Feature" as const,
          properties: { id: route.id },
          geometry: geom,
        };
      })
      .filter((f): f is NonNullable<typeof f> => f !== null),
  };
}

function PolarSvgFallback({
  routes = [],
  selectedRouteId,
  zoom,
  pan,
  onMouseDown,
  onMouseMove,
  onMouseUp,
}: {
  routes: RouteCandidate[];
  selectedRouteId?: string;
  zoom: number;
  pan: { x: number; y: number };
  onMouseDown: (e: MouseEvent<SVGSVGElement>) => void;
  onMouseMove: (e: MouseEvent<SVGSVGElement>) => void;
  onMouseUp: () => void;
}) {
  const baseScale = 14;
  const scale = baseScale * zoom;
  const pole = useMemo(() => ({ x: 400 + pan.x, y: 300 + pan.y + 8 * scale }), [pan.x, pan.y, scale]);

  const continentPath = useMemo(() => {
    const points = ANTARCTICA_OUTLINE.map(([lon, lat]) => projectPoint(lon, lat, zoom, pan));
    if (!points.length) return "";
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") + " Z";
  }, [zoom, pan]);

  // Operational coordinates: origin (20°E, 70°S) and destination (50°E, 68°S)
  const originPos = useMemo(() => projectPoint(20, -70, zoom, pan), [zoom, pan]);
  const destPos = useMemo(() => projectPoint(50, -68, zoom, pan), [zoom, pan]);

  // Scale bar: 250 NM = (250 / 60) * 14 * zoom
  const scaleBarWidth = useMemo(() => Math.max(20, (250 / 60) * scale), [scale]);

  // Candidate routes coordinates
  const renderedRoutes = useMemo(() => {
    return routes.map((route) => {
      const geom = parseGeometry(route.geometry);
      if (!geom || geom.coordinates.length < 2) return null;
      const points = geom.coordinates.map(([lon, lat]) => projectPoint(lon, lat, zoom, pan));
      return {
        id: route.id,
        isSelected: route.id === selectedRouteId,
        points,
        polylineString: points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
      };
    }).filter((r): r is NonNullable<typeof r> => r !== null);
  }, [routes, selectedRouteId, zoom, pan]);

  const hasRouteGeometry = renderedRoutes.length > 0;

  return (
    <svg
      data-testid="polar-svg-fallback"
      viewBox="0 0 800 600"
      className="h-full w-full cursor-grab active:cursor-grabbing select-none"
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      <rect width="800" height="600" fill="#0d1b2a" />

      {/* Polar stereographic grid: concentric latitude circles centered at South Pole */}
      <g opacity="0.6">
        {PARALLELS.map((lat) => {
          const r = (90 + lat) * scale;
          return (
            <g key={`parallel-${lat}`}>
              <circle
                cx={pole.x}
                cy={pole.y}
                r={r}
                fill="none"
                stroke="#1e3a5f"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
              <text
                x={pole.x}
                y={pole.y - r - 4}
                textAnchor="middle"
                fill="#64748b"
                fontSize="10"
                className="select-none font-mono"
              >
                {Math.abs(lat)}°S
              </text>
            </g>
          );
        })}

        {/* Meridians radiating from pole */}
        {MERIDIANS.map(({ lon, label }) => {
          const outer = projectPoint(lon, -58, zoom, pan);
          const labelPos = projectPoint(lon, -54, zoom, pan);
          return (
            <g key={`meridian-${lon}`}>
              <line
                x1={pole.x}
                y1={pole.y}
                x2={outer.x}
                y2={outer.y}
                stroke="#1e3a5f"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor="middle"
                dominantBaseline="central"
                fill="#64748b"
                fontSize="10"
                className="select-none font-mono"
              >
                {label}
              </text>
            </g>
          );
        })}

        {/* South Pole marker */}
        <circle cx={pole.x} cy={pole.y} r="3" fill="#94a3b8" />
        <line x1={pole.x - 6} y1={pole.y} x2={pole.x + 6} y2={pole.y} stroke="#94a3b8" strokeWidth="1" />
        <line x1={pole.x} y1={pole.y - 6} x2={pole.x} y2={pole.y + 6} stroke="#94a3b8" strokeWidth="1" />
        <text
          x={pole.x + 8}
          y={pole.y - 8}
          fill="#94a3b8"
          fontSize="10"
          className="select-none font-mono"
        >
          90°S South Pole
        </text>
      </g>

      {/* Antarctic continent landmass outline */}
      <path
        d={continentPath}
        fill="#16293d"
        stroke="#2563eb"
        strokeWidth="1.5"
        strokeOpacity="0.8"
      />

      {/* Unselected route candidates */}
      {renderedRoutes.filter((r) => !r.isSelected).map((route) => (
        <polyline
          key={`route-${route.id}`}
          points={route.polylineString}
          fill="none"
          stroke="#0B3C5D"
          strokeWidth="2.5"
          strokeOpacity="0.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}

      {/* Direct planned baseline if no candidate routes have geometry */}
      {!hasRouteGeometry && (
        <line
          x1={originPos.x}
          y1={originPos.y}
          x2={destPos.x}
          y2={destPos.y}
          stroke="#0284C7"
          strokeWidth="2"
          strokeDasharray="6 4"
          strokeOpacity="0.6"
        />
      )}

      {/* Selected route candidate polyline & highlighted waypoints */}
      {renderedRoutes.filter((r) => r.isSelected).map((route) => (
        <g key={`selected-route-${route.id}`}>
          <polyline
            points={route.polylineString}
            fill="none"
            stroke="#0284C7"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {route.points.map((p, idx) => (
            <circle
              key={`wp-${idx}`}
              cx={p.x}
              cy={p.y}
              r={idx === 0 || idx === route.points.length - 1 ? 5 : 3.5}
              fill="#38BDF8"
              stroke="#0B3C5D"
              strokeWidth="1.5"
            >
              <title>{`Waypoint ${idx + 1}`}</title>
            </circle>
          ))}
        </g>
      ))}

      {/* Origin Point (20°E, 70°S) with pulse animation */}
      <g transform={`translate(${originPos.x.toFixed(1)}, ${originPos.y.toFixed(1)})`}>
        <circle r="16" fill="#10B981" fillOpacity="0.25">
          <animate attributeName="r" values="8;24;8" dur="2.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.8;0.1;0.8" dur="2.4s" repeatCount="indefinite" />
        </circle>
        <circle r="6" fill="#10B981" stroke="#ffffff" strokeWidth="2" />
        <rect x="10" y="-12" width="135" height="22" rx="4" fill="#0f172a" fillOpacity="0.9" stroke="#10B981" strokeWidth="1" />
        <text x="16" y="3" fill="#34D399" fontSize="11" fontWeight="bold" className="select-none font-sans">
          Origin (20°E, 70°S)
        </text>
      </g>

      {/* Destination Point (50°E, 68°S) with pulse animation */}
      <g transform={`translate(${destPos.x.toFixed(1)}, ${destPos.y.toFixed(1)})`}>
        <circle r="16" fill="#EF4444" fillOpacity="0.25">
          <animate attributeName="r" values="8;24;8" dur="2.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.8;0.1;0.8" dur="2.4s" repeatCount="indefinite" />
        </circle>
        <circle r="6" fill="#EF4444" stroke="#ffffff" strokeWidth="2" />
        <rect x="10" y="-12" width="165" height="22" rx="4" fill="#0f172a" fillOpacity="0.9" stroke="#EF4444" strokeWidth="1" />
        <text x="16" y="3" fill="#F87171" fontSize="11" fontWeight="bold" className="select-none font-sans">
          Destination (50°E, 68°S)
        </text>
      </g>

      {/* Scale Indicator */}
      <g data-testid="scale-indicator" transform="translate(40, 545)">
        <rect x="-8" y="-20" width={Math.max(160, scaleBarWidth + 24)} height="32" rx="4" fill="#0f172a" fillOpacity="0.85" stroke="#334155" strokeWidth="1" />
        <line x1="0" y1="0" x2={scaleBarWidth} y2="0" stroke="#94A3B8" strokeWidth="3" />
        <line x1="0" y1="-4" x2="0" y2="4" stroke="#94A3B8" strokeWidth="2" />
        <line x1={scaleBarWidth} y1="-4" x2={scaleBarWidth} y2="4" stroke="#94A3B8" strokeWidth="2" />
        <text x={scaleBarWidth / 2} y="-6" textAnchor="middle" fill="#CBD5E1" fontSize="10" fontWeight="bold" className="select-none font-mono">
          250 NM / 463 km
        </text>
      </g>

      {/* Cartographic datum label */}
      <text x="780" y="580" textAnchor="end" fill="#475569" fontSize="10" className="select-none font-mono">
        Polar Stereographic · Centered [0°E, 82°S]
      </text>
    </svg>
  );
}

export function OperationalMap({
  layers = [],
  routes = [],
  selectedRouteId,
}: {
  layers?: OperationalLayer[];
  routes?: RouteCandidate[];
  selectedRouteId?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<Map | null>(null);
  const [mapMode, setMapMode] = useState<"loading" | "webgl" | "fallback">("loading");

  // Fallback SVG pan & zoom states
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const routeFeatures = useMemo(() => features(routes), [routes]);
  const selectedFeatures = useMemo(
    () => features(routes.filter((route) => route.id === selectedRouteId)),
    [routes, selectedRouteId]
  );
  const selectedRoute = routes.find((route) => route.id === selectedRouteId);
  const isHumanReviewRequired =
    selectedRoute?.status === "DRAFT" ||
    selectedRoute?.risk_data_status === "UNKNOWN" ||
    !selectedRoute?.metadata?.data_confidence;

  useEffect(() => {
    if (!container.current) return;

    let isSupported = false;
    try {
      isSupported =
        typeof (Map as unknown as { supported?: () => boolean }).supported === "function"
          ? (Map as unknown as { supported: () => boolean }).supported()
          : true;
    } catch {
      isSupported = false;
    }

    if (!isSupported) {
      setMapMode("fallback");
      return;
    }

    try {
      const instance = new Map({
        container: container.current,
        style: offlineDarkPolarStyle,
        center: antarcticView.center,
        zoom: antarcticView.zoom,
        maxBounds: antarcticView.maxBounds,
        attributionControl: false,
      });
      map.current = instance;

      instance.on("load", () => {
        requestAnimationFrame(() => {
          instance.resize();
        });
        setMapMode("webgl");
      });

      instance.on("error", (e) => {
        console.warn("MapLibre runtime event error, engaging polar SVG fallback:", e);
        setMapMode("fallback");
      });

      const observer = new ResizeObserver(() => {
        requestAnimationFrame(() => {
          instance.resize();
        });
      });
      observer.observe(container.current);

      return () => {
        observer.disconnect();
        instance.remove();
        map.current = null;
      };
    } catch (err) {
      console.warn("MapLibre constructor error, engaging polar SVG fallback:", err);
      setMapMode("fallback");
    }
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (mapMode !== "webgl" || !instance) return;
    try {
      if (!instance.getSource(routeSourceId)) {
        instance.addSource(routeSourceId, { type: "geojson", data: routeFeatures });
        instance.addLayer({
          id: "candidate-routes-line",
          type: "line",
          source: routeSourceId,
          paint: { "line-color": "#0B3C5D", "line-width": 3, "line-opacity": 0.8 },
        });
        instance.addSource(selectedRouteSourceId, { type: "geojson", data: selectedFeatures });
        instance.addLayer({
          id: "selected-candidate-route-line",
          type: "line",
          source: selectedRouteSourceId,
          paint: { "line-color": "#0284C7", "line-width": 5 },
        });
      } else {
        const source = instance.getSource(routeSourceId);
        const selectedSource = instance.getSource(selectedRouteSourceId);
        if (source && source.type === "geojson") (source as GeoJSONSource).setData(routeFeatures);
        if (selectedSource && selectedSource.type === "geojson") (selectedSource as GeoJSONSource).setData(selectedFeatures);
      }

      const selectedGeom = parseGeometry(selectedRoute?.geometry);
      if (selectedGeom && selectedGeom.coordinates.length >= 2) {
        const longitudes = selectedGeom.coordinates.map(([longitude]) => longitude);
        const latitudes = selectedGeom.coordinates.map(([, latitude]) => latitude);
        const minLon = Math.min(...longitudes);
        const maxLon = Math.max(...longitudes);
        const minLat = Math.min(...latitudes);
        const maxLat = Math.max(...latitudes);
        if (Number.isFinite(minLon) && Number.isFinite(maxLon) && Number.isFinite(minLat) && Number.isFinite(maxLat)) {
          instance.fitBounds([[minLon, minLat], [maxLon, maxLat]], { padding: 56, maxZoom: 7, duration: 0 });
        }
      }
    } catch (e) {
      console.warn("Operational map layer update error:", e);
    }
  }, [routeFeatures, routes, selectedFeatures, selectedRoute, selectedRouteId, mapMode]);

  const handleZoomIn = () => {
    if (map.current) {
      map.current.zoomIn();
    } else {
      setZoom((z) => Math.min(3.0, z * 1.25));
    }
  };

  const handleZoomOut = () => {
    if (map.current) {
      map.current.zoomOut();
    } else {
      setZoom((z) => Math.max(0.6, z / 1.25));
    }
  };

  const handleReset = () => {
    if (map.current) {
      map.current.jumpTo({ center: antarcticView.center, zoom: antarcticView.zoom });
    } else {
      setZoom(1.0);
      setPan({ x: 0, y: 0 });
    }
  };

  const handleMouseDown = (e: MouseEvent<SVGSVGElement>) => {
    isDragging.current = true;
    dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: MouseEvent<SVGSVGElement>) => {
    if (!isDragging.current) return;
    setPan({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
    });
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const hasGeometry = routeFeatures.features.length > 0;

  return (
    <section
      aria-label="Operational map"
      className="relative w-full overflow-hidden rounded-card border border-kurmesh-border bg-[#0d1b2a]"
      style={{ minHeight: "480px", height: "480px", width: "100%", position: "relative" }}
    >
      <div
        ref={container}
        className={`absolute inset-0 h-full w-full ${mapMode === "fallback" ? "hidden" : "block"}`}
        style={{ minHeight: "480px", width: "100%", position: "relative" }}
      />

      {mapMode === "fallback" && (
        <PolarSvgFallback
          routes={routes}
          selectedRouteId={selectedRouteId}
          zoom={zoom}
          pan={pan}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        />
      )}

      {mapMode === "loading" && (
        <div className="absolute inset-0 z-20 bg-[#0d1b2a]/80">
          <LoadingState label="Preparing Antarctic map foundation" />
        </div>
      )}

      <MapControls onZoomIn={handleZoomIn} onZoomOut={handleZoomOut} onReset={handleReset} />
      <MapLegend layers={layers} />

      <div className="absolute left-4 top-4 z-10 max-w-xs rounded-lg border border-kurmesh-border bg-white/95 p-3 text-sm text-kurmesh-muted shadow-card">
        <div className="flex items-center justify-between gap-2">
          <p className="font-bold text-kurmesh-text">Antarctic operational map</p>
          <span className="rounded bg-kurmesh-polar px-1.5 py-0.5 font-mono text-[10px] font-bold text-kurmesh-blue">
            {mapMode === "webgl" ? "WebGL" : "Polar SVG"}
          </span>
        </div>
        <p className="mt-1">
          {hasGeometry
            ? "Candidate route geometry from the selected mission is shown."
            : "No candidate route geometry is available for the selected mission."}
        </p>
        {selectedRoute && isHumanReviewRequired && (
          <p className="mt-2 font-semibold text-amber-600">
            ⚠️ Human Review Required ({selectedRoute.status === "DRAFT" ? "DRAFT status" : "Unverified ML confidence"})
          </p>
        )}
      </div>
    </section>
  );
}
