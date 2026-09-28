import type { RouteCandidate } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/Table";

export function RouteComparison({
  routes,
  selectedRouteId,
  onSelect,
}: {
  routes: RouteCandidate[];
  selectedRouteId?: string;
  onSelect: (route: RouteCandidate) => void;
}) {
  if (!routes.length) {
    return <EmptyState title="No candidate routes" description="No route candidates are currently available for this mission." />;
  }

  return (
    <Table>
      <TableHead>
        <TableRow>
          <TableHeader>Candidate</TableHeader>
          <TableHeader>Version</TableHeader>
          <TableHeader>Status</TableHeader>
          <TableHeader>Distance</TableHeader>
          <TableHeader>Risk score</TableHeader>
          <TableHeader>Data confidence</TableHeader>
          <TableHeader>
            <span className="sr-only">Select</span>
          </TableHeader>
        </TableRow>
      </TableHead>
      <TableBody>
        {routes.map((route, index) => {
          const confidence = route?.metadata?.data_confidence;
          const hasConfidence = typeof confidence === "string" || typeof confidence === "number";
          const isDraftOrMissingML = route.status === "DRAFT" || !hasConfidence;

          return (
            <TableRow key={route.id} aria-selected={route.id === selectedRouteId}>
              <TableCell className="font-semibold">Route {String.fromCharCode(65 + index)}</TableCell>
              <TableCell>v{route.version}</TableCell>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <span>{route.status}</span>
                  {isDraftOrMissingML && (
                    <span className="inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800">
                      Human Review Required
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell>{route.distance_nm === null ? "Unavailable" : `${route.distance_nm} nautical miles`}</TableCell>
              <TableCell>{route.risk_score === null ? "Unavailable" : route.risk_score}</TableCell>
              <TableCell>
                {hasConfidence ? (
                  String(confidence)
                ) : (
                  <span className="text-amber-700">Missing (Review Required)</span>
                )}
              </TableCell>
              <TableCell>
                <Button
                  className="min-h-9 px-3 py-1 text-sm"
                  variant={route.id === selectedRouteId ? "primary" : "secondary"}
                  onClick={() => onSelect(route)}
                >
                  View route
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
