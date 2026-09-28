import type { RouteCandidate } from "../../api/types";
import { Alert } from "../../components/ui/Alert";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";

function JsonSection({ title, value }: { title: string; value?: Record<string, unknown> | null }) {
  return (
    <details className="border-t border-kurmesh-border pt-3">
      <summary className="cursor-pointer font-semibold">{title}</summary>
      <pre className="mt-3 overflow-x-auto rounded-lg bg-kurmesh-polar p-3 text-xs text-kurmesh-text">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </details>
  );
}

export function RouteDetail({ route }: { route?: RouteCandidate }) {
  if (!route) {
    return <EmptyState title="No route selected" description="Select a candidate route to view its available decision data." />;
  }

  const confidence = route.metadata?.data_confidence;
  const hasConfidence = typeof confidence === "string" || typeof confidence === "number";
  const isHumanReviewRequired = route.status === "DRAFT" || !hasConfidence;

  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold">Selected route</h3>
        {isHumanReviewRequired && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
            Human Review Required
          </span>
        )}
      </div>

      {isHumanReviewRequired && (
        <Alert variant="warning" title="Human Review Required" className="mt-4">
          This route is in {route.status} status and lacks verified ML model predictions. Under KURMESH human-in-the-loop governance, manual operator review and authorization are mandatory before route approval.
        </Alert>
      )}

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-kurmesh-muted">Route ID</dt>
          <dd className="break-all font-semibold">{route.id}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Version</dt>
          <dd className="font-semibold">{route.version}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Status</dt>
          <dd className="font-semibold">{route.status}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Risk Data Status</dt>
          <dd className="font-semibold">{route.risk_data_status ?? "UNKNOWN"}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Distance</dt>
          <dd className="font-semibold">{route.distance_nm === null ? "Unavailable" : `${route.distance_nm} nautical miles`}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Estimated duration</dt>
          <dd className="font-semibold">{route.estimated_duration_hours === null ? "Unavailable" : `${route.estimated_duration_hours} hours`}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Risk score</dt>
          <dd className="font-semibold">{route.risk_score ?? "Unavailable"}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Data Confidence</dt>
          <dd className="font-semibold">{hasConfidence ? String(confidence) : "Unavailable (Human Review Required)"}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Algorithm version</dt>
          <dd className="break-all font-semibold">{route.algorithm_version}</dd>
        </div>
        <div>
          <dt className="text-kurmesh-muted">Prediction ID</dt>
          <dd className="break-all font-semibold">{route.prediction_id ?? "Unavailable"}</dd>
        </div>
      </dl>

      <div className="mt-5 space-y-3">
        <JsonSection title="Risk components" value={route.risk_components} />
        <JsonSection title="Environmental snapshot" value={route.environmental_snapshot} />
        <JsonSection title="Metadata" value={route.metadata} />
      </div>
    </Card>
  );
}
