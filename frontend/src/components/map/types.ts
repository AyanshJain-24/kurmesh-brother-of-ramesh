export type OperationalLayerKind = "vessel" | "sea_ice" | "iceberg" | "weather" | "ocean_current" | "route" | "restricted_area" | "forecast";
export interface OperationalLayer { id: string; label: string; kind: OperationalLayerKind; visible: boolean; status: "LIVE" | "STALE" | "DEGRADED" | "UNAVAILABLE" | "ERROR"; }
