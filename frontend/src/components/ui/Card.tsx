import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "./utils";
export interface CardProps extends HTMLAttributes<HTMLDivElement> { variant?: "default" | "interactive" | "highlighted"; }
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card({ className, variant = "default", ...props }, ref) {
  return <div ref={ref} className={cn("rounded-card border bg-kurmesh-surface p-5 shadow-card", variant === "interactive" && "cursor-pointer transition-shadow hover:shadow-panel focus-within:shadow-panel", variant === "highlighted" ? "border-kurmesh-blue border-l-4" : "border-kurmesh-border", className)} {...props} />;
});
