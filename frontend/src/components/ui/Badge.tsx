import type { HTMLAttributes } from "react";
import { cn } from "./utils";
export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) { return <span className={cn("inline-flex items-center rounded-full bg-kurmesh-polar px-2.5 py-1 text-xs font-bold tracking-wide text-kurmesh-text", className)} {...props} />; }
