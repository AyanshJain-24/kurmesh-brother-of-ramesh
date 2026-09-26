import { LoaderCircle } from "lucide-react";
export function LoadingState({ label = "Loading" }: { label?: string }) { return <div role="status" className="flex min-h-32 items-center justify-center gap-3 text-kurmesh-muted"><LoaderCircle className="h-6 w-6 animate-spin" aria-hidden="true" />{label}<span className="sr-only">…</span></div>; }
