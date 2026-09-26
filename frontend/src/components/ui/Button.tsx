import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "./utils";

type ButtonVariant = "primary" | "secondary" | "outline" | "danger" | "ghost" | "success";
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant; loading?: boolean; icon?: ReactNode; iconPosition?: "start" | "end";
}
const variants: Record<ButtonVariant, string> = {
  primary: "bg-kurmesh-navy text-white hover:bg-[#082d43]",
  secondary: "bg-kurmesh-blue text-white hover:bg-[#066888]",
  outline: "border border-kurmesh-navy bg-white text-kurmesh-navy hover:bg-kurmesh-polar",
  danger: "bg-kurmesh-danger text-white hover:bg-[#a83030]",
  ghost: "text-kurmesh-navy hover:bg-kurmesh-polar",
  success: "bg-kurmesh-success text-white hover:bg-[#116c49]",
};
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({ className, variant = "primary", loading = false, disabled, icon, iconPosition = "start", children, type = "button", ...props }, ref) {
  const adornment = loading ? <LoaderCircle aria-hidden="true" className="h-5 w-5 animate-spin" /> : icon;
  return <button ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined} className={cn("inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-base font-semibold transition-colors focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-kurmesh-cyan disabled:cursor-not-allowed disabled:opacity-55", variants[variant], className)} {...props}>
    {adornment && iconPosition === "start" && adornment}{children}{adornment && iconPosition === "end" && adornment}
  </button>;
});
