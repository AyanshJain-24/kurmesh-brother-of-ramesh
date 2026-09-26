import { forwardRef, type HTMLAttributes, type TableHTMLAttributes } from "react";
import { cn } from "./utils";
export const Table = forwardRef<HTMLTableElement, TableHTMLAttributes<HTMLTableElement>>(function Table({ className, ...props }, ref) { return <div className="overflow-x-auto rounded-card border border-kurmesh-border"><table ref={ref} className={cn("min-w-full divide-y divide-kurmesh-border text-left", className)} {...props} /></div>; });
export function TableHead(props: HTMLAttributes<HTMLTableSectionElement>) { return <thead className="bg-kurmesh-polar text-sm text-kurmesh-muted" {...props} />; }
export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) { return <tbody className="divide-y divide-kurmesh-border bg-white" {...props} />; }
export function TableRow(props: HTMLAttributes<HTMLTableRowElement>) { return <tr className="hover:bg-kurmesh-polar/60" {...props} />; }
export function TableHeader(props: HTMLAttributes<HTMLTableCellElement>) { return <th scope="col" className="px-4 py-3 font-bold" {...props} />; }
export function TableCell(props: HTMLAttributes<HTMLTableCellElement>) { return <td className="px-4 py-3 text-sm" {...props} />; }
