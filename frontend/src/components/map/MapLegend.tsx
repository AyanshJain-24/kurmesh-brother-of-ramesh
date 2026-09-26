import { Layers3 } from "lucide-react";
import { EmptyState } from "../ui/EmptyState";
import type { OperationalLayer } from "./types";
export function MapLegend({ layers = [] }: { layers?: OperationalLayer[] }) { if (!layers.length) return <div className="absolute bottom-4 left-4 z-10 w-64 rounded-lg border border-kurmesh-border bg-white/95 p-3 shadow-card"><EmptyState title="Operational layers unavailable" description="Validated layers will be listed here when connected." icon={<Layers3 aria-hidden="true" className="h-5 w-5" />} /></div>; return <aside aria-label="Map legend">{layers.map((layer) => <p key={layer.id}>{layer.label}</p>)}</aside>; }
