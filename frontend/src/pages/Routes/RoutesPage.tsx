import { useState } from "react";
import { useMissionRoutes, useMissions, useRouteCandidates } from "../../api/queries";
import type { RouteCandidate } from "../../api/types";
import { OperationalMap } from "../../components/map/OperationalMap";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { RouteComparison } from "../Missions/RouteComparison";
import { RouteDetail } from "../Missions/RouteDetail";
import { RouteReviewPanel } from "../Missions/RouteReviewPanel";

export function RoutesPage() {
  const missions = useMissions(); const [missionId, setMissionId] = useState(""); const [selected, setSelected] = useState<RouteCandidate>();
  const candidates = useRouteCandidates(missionId || undefined); const routes = useMissionRoutes(missionId || undefined);
  const mission = missions.data?.items.find((item) => item.id === missionId);
  const governedRoute = routes.data?.items.find((route) => route.route_candidate_id === selected?.id);
  if (missions.isPending) return <LoadingState label="Loading missions" />;
  if (missions.isError) return <ErrorState title="Mission data unavailable" message="The backend did not return missions for route management." />;
  return <section aria-labelledby="routes-title" className="space-y-6"><div><p className="font-mono text-sm font-bold text-kurmesh-blue">ROUTE MANAGEMENT</p><h2 id="routes-title" className="mt-1 text-3xl font-bold">Route candidates and human review</h2><p className="mt-2 text-kurmesh-muted">Candidates are generated from the Mission Workspace. Selection, review, and approval remain governed human actions.</p></div><Card><label className="block text-sm font-semibold">Mission<select aria-label="Route management mission" className="mt-2 min-h-11 w-full rounded-lg border border-kurmesh-border bg-white px-3" value={missionId} onChange={(event) => { setMissionId(event.target.value); setSelected(undefined); }}><option value="">Select a mission</option>{missions.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.state}</option>)}</select></label></Card>{!missionId ? <EmptyState title="Select a mission" description="Select a mission to view its backend route candidates and governed human-review workflow." /> : <>{candidates.isPending ? <LoadingState label="Loading candidate routes" /> : candidates.isError ? <ErrorState title="Route data unavailable" message="The backend did not return candidate routes." /> : !candidates.data?.items.length ? <EmptyState title="No candidate routes" description="No route candidates are currently available for this mission. Generate route options from the Mission Workspace when it is ready." /> : <RouteComparison routes={candidates.data.items} selectedRouteId={selected?.id} onSelect={setSelected} />}<section><h3 className="mb-3 text-xl font-bold">Operational map</h3><OperationalMap routes={candidates.data?.items ?? []} selectedRouteId={selected?.id} /></section><section className="grid gap-6 xl:grid-cols-2"><div><h3 className="mb-3 text-xl font-bold">Route detail</h3><RouteDetail route={selected} /></div><div><h3 className="mb-3 text-xl font-bold">Human Review</h3>{routes.isPending ? <LoadingState label="Loading governed routes" /> : routes.isError ? <ErrorState title="Route workflow unavailable" message="The backend did not return governed route records." /> : <RouteReviewPanel missionId={mission!.id} candidate={selected} route={governedRoute} />}</div></section></>}</section>;
}
