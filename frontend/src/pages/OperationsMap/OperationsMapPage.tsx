import { OperationalMap } from "../../components/map/OperationalMap";

export function OperationsMapPage() {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-kurmesh-blue">Operations</p>
        <h2 className="mt-1 text-2xl font-bold text-kurmesh-text">Operations Map</h2>
        <p className="mt-2 max-w-2xl text-sm text-kurmesh-muted">
          A neutral Antarctic map foundation. Validated operational layers are not connected yet.
        </p>
      </div>
      <OperationalMap />
    </section>
  );
}
