import type { ReactNode } from "react";
import { EmptyState } from "../components/ui/EmptyState";
export function PagePlaceholder({ title, description, children }: { title: string; description: string; children?: ReactNode }) { return <section aria-labelledby="page-title"><p className="font-mono text-sm font-bold text-kurmesh-blue">KURMESH OPERATIONS</p><h2 id="page-title" className="mt-1 text-3xl font-bold text-kurmesh-text">{title}</h2><div className="mt-6">{children ?? <EmptyState title={`${title} is awaiting connection`} description={description} />}</div></section>; }
