import type { ReactNode } from "react";
import { Bot, CloudSun, Snowflake, Waves } from "lucide-react";
import { useEnvironmentObservations, useEnvironmentSources } from "../../api/queries";
import type { AvailabilityStatus, EnvironmentObservation, EnvironmentSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { StatusBadge } from "../../components/ui/StatusBadge";

const dataBearingStatuses = new Set<AvailabilityStatus>(["LIVE", "STALE", "DEGRADED"]);
const severity: Record<AvailabilityStatus, number> = { LIVE: 0, STALE: 1, DEGRADED: 2, UNAVAILABLE: 3, ERROR: 4 };

function summaryStatus(observations: EnvironmentObservation[]) {
  if (!observations.length) return "UNAVAILABLE" as const;
  return observations.reduce((current, observation) => severity[observation.status] > severity[current] ? observation.status : current, observations[0].status);
}

function readable(value: unknown) {
  return typeof value === "number" || typeof value === "string" ? String(value) : null;
}

function SourceDetail({ observation, source }: { observation?: EnvironmentObservation; source?: EnvironmentSource }) {
  if (!observation) return <p className="mt-4 text-sm text-kurmesh-muted">No authorized provider observation is available.</p>;
  return <div className="mt-4 border-t border-kurmesh-border pt-3 text-xs text-kurmesh-muted"><p>Valid time: {observation.valid_to ? new Date(observation.valid_to).toLocaleString() : observation.valid_from ? new Date(observation.valid_from).toLocaleString() : "Not supplied"}</p><p className="mt-1">Retrieved: {new Date(observation.retrieved_at).toLocaleString()}</p><p className="mt-1">Source: {source ? `${source.provider} · ${source.source}` : `Source ID ${observation.source_id}`}</p>{source?.url && <a className="mt-1 inline-block break-all text-kurmesh-blue underline" href={source.url} target="_blank" rel="noreferrer">Source reference</a>}</div>;
}

function Metric({ label, observation, valueKey }: { label: string; observation?: EnvironmentObservation; valueKey: string }) {
  const value = observation && dataBearingStatuses.has(observation.status) ? readable(observation.value?.[valueKey]) : null;
  return <div className="flex items-start justify-between gap-3 border-b border-kurmesh-border py-2 last:border-0"><div><p className="text-sm font-semibold">{label}</p><p className="mt-0.5 text-sm text-kurmesh-muted">{value === null ? "Unavailable" : `${value}${observation?.units ? ` ${observation.units}` : ""}`}</p></div>{observation && <StatusBadge status={observation.status} />}</div>;
}

function IntelligenceCard({ title, icon, observations, sources, children }: { title: string; icon: ReactNode; observations: EnvironmentObservation[]; sources: EnvironmentSource[]; children: ReactNode }) {
  const primary = observations[0]; const source = primary ? sources.find((item) => item.id === primary.source_id) : undefined;
  return <Card><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="rounded-lg bg-kurmesh-polar p-2 text-kurmesh-blue">{icon}</span><h4 className="font-bold">{title}</h4></div><StatusBadge status={summaryStatus(observations)} /></div><div className="mt-4">{children}</div><SourceDetail observation={primary} source={source} /></Card>;
}

export function EnvironmentalIntelligence() {
  const observations = useEnvironmentObservations(); const sources = useEnvironmentSources();
  if (observations.isPending || sources.isPending) return <section aria-labelledby="environmental-intelligence-title"><h3 id="environmental-intelligence-title" className="mb-3 text-xl font-bold">Environmental Intelligence</h3><LoadingState label="Loading environmental intelligence" /></section>;
  if (observations.isError || sources.isError) return <section aria-labelledby="environmental-intelligence-title"><h3 id="environmental-intelligence-title" className="mb-3 text-xl font-bold">Environmental Intelligence</h3><ErrorState title="Environmental intelligence unavailable" message="The backend did not return the authorized environment records required for this mission workspace." /></section>;
  const items = observations.data?.items ?? []; const sourceItems = sources.data?.items ?? [];
  const seaIce = items.filter((item) => item.observation_type === "sea_ice_concentration");
  const weather = items.filter((item) => ["wind", "air_temperature", "sea_level_pressure", "weather"].includes(item.observation_type));
  const ocean = items.filter((item) => ["ocean_current", "sea_water_temperature", "ocean_conditions"].includes(item.observation_type));
  const wind = weather.find((item) => item.observation_type === "wind"); const airTemperature = weather.find((item) => item.observation_type === "air_temperature"); const pressure = weather.find((item) => item.observation_type === "sea_level_pressure");
  const current = ocean.find((item) => item.observation_type === "ocean_current"); const waterTemperature = ocean.find((item) => item.observation_type === "sea_water_temperature");
  const iceberg = items.filter((item) => ["iceberg", "iceberg_drift"].includes(item.observation_type));
  return <section aria-labelledby="environmental-intelligence-title"><div className="mb-3 flex flex-wrap items-baseline justify-between gap-2"><div><p className="font-mono text-xs font-bold tracking-wide text-kurmesh-blue">AUTHORIZED PROVIDER RECORDS</p><h3 id="environmental-intelligence-title" className="mt-1 text-xl font-bold">Environmental Intelligence</h3></div><p className="text-sm text-kurmesh-muted">Latest persisted provider observations; no values are inferred in this workspace.</p></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><IntelligenceCard title="Sea Ice" icon={<Snowflake aria-hidden="true" className="h-5 w-5" />} observations={seaIce} sources={sourceItems}><Metric label="Concentration" observation={seaIce[0]} valueKey="concentration" /></IntelligenceCard><IntelligenceCard title="Weather" icon={<CloudSun aria-hidden="true" className="h-5 w-5" />} observations={weather} sources={sourceItems}><Metric label="Wind" observation={wind} valueKey="speed" /><Metric label="Temperature" observation={airTemperature} valueKey="temperature" /><Metric label="Pressure" observation={pressure} valueKey="pressure" /></IntelligenceCard><IntelligenceCard title="Ocean" icon={<Waves aria-hidden="true" className="h-5 w-5" />} observations={ocean} sources={sourceItems}><Metric label="Current speed" observation={current} valueKey="speed" /><Metric label="Current direction" observation={current} valueKey="direction_degrees" /><Metric label="Temperature" observation={waterTemperature} valueKey="temperature" /></IntelligenceCard>{iceberg.length > 0 ? <IntelligenceCard title="Iceberg Intelligence" icon={<Bot aria-hidden="true" className="h-5 w-5" />} observations={iceberg} sources={sourceItems}><Metric label="Target iceberg" observation={iceberg[0]} valueKey="target_id" /><Metric label="Predicted 24h drift" observation={iceberg[0]} valueKey="drift_speed_m_per_day" /><Metric label="Displacement dx" observation={iceberg[0]} valueKey="predicted_drift_dx_m" /></IntelligenceCard> : <Card><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="rounded-lg bg-kurmesh-polar p-2 text-kurmesh-blue"><Bot aria-hidden="true" className="h-5 w-5" /></span><h4 className="font-bold">Iceberg Intelligence</h4></div><Badge className="bg-slate-100 text-kurmesh-muted">MODEL_UNAVAILABLE</Badge></div><p className="mt-4 text-sm text-kurmesh-muted">The validated demo model requires a complete frozen trajectory feature vector. That input is not available from this mission workspace.</p><div className="mt-4 border-t border-kurmesh-border pt-3 text-xs text-kurmesh-muted"><p>Prediction: unavailable</p><p className="mt-1">Model and dataset provenance: unavailable until contract-valid inference can run.</p></div></Card>}</div></section>;
}
