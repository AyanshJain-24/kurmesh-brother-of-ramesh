import { useState } from "react";
import { useMissions, useRouteCandidates } from "../../api/queries";
import { OperationalMap } from "../../components/map/OperationalMap";
import { LoadingState } from "../../components/ui/LoadingState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";

export function OperationsMapPage() {
  const missions = useMissions();
  const [selectedMissionId, setSelectedMissionId] = useState<string>();

  const activeMission = missions.data?.items.find((m) => m.id === selectedMissionId) ?? missions.data?.items[0];
  const candidates = useRouteCandidates(activeMission?.id);
  const [selectedRouteId, setSelectedRouteId] = useState<string>();

  const candidateItems = candidates.data?.items ?? [];
  const activeRouteId = selectedRouteId ?? candidateItems[0]?.id;

  return (
    <section className="space-y-6" aria-labelledby="operations-map-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-kurmesh-blue">Operations</p>
          <h2 id="operations-map-title" className="mt-1 text-2xl font-bold text-kurmesh-text">Operations Map</h2>
          <p className="mt-2 max-w-2xl text-sm text-kurmesh-muted">
            Polar stereographic operational navigation foundation with active mission route candidates and waypoint intelligence.
          </p>
        </div>
        {activeMission && (
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-kurmesh-muted">Active Mission:</span>
            <Badge>{activeMission.name}</Badge>
          </div>
        )}
      </div>

      {missions.isPending ? (
        <LoadingState label="Loading operational mission..." />
      ) : missions.isError ? (
        <ErrorState title="Missions unavailable" message="Failed to load mission data for operations map." />
      ) : (
        <div className="space-y-4">
          <OperationalMap
            routes={candidateItems}
            selectedRouteId={activeRouteId}
          />
          {candidateItems.length > 0 && (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-bold text-kurmesh-text">Candidate Routes ({candidateItems.length})</h3>
                  <p className="text-xs text-kurmesh-muted">Select a route option to highlight on the polar stereographic map</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {candidateItems.map((candidate, idx) => (
                    <button
                      key={candidate.id}
                      type="button"
                      onClick={() => setSelectedRouteId(candidate.id)}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        candidate.id === activeRouteId
                          ? "bg-kurmesh-blue text-white shadow-sm"
                          : "bg-kurmesh-polar text-kurmesh-text hover:bg-kurmesh-border"
                      }`}
                    >
                      Option {idx + 1} ({candidate.status})
                      {candidate.risk_score !== null && ` · Risk ${(candidate.risk_score * 100).toFixed(1)}%`}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}
