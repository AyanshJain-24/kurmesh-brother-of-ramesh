import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "./Button";
export function Modal({ open, onClose, title, children, labelledBy }: { open: boolean; onClose: () => void; title: string; children: ReactNode; labelledBy?: string }) {
  const closeRef = useRef<HTMLButtonElement>(null); const titleId = labelledBy ?? "kurmesh-modal-title";
  useEffect(() => { if (!open) return; closeRef.current?.focus(); const handler = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; document.addEventListener("keydown", handler); return () => document.removeEventListener("keydown", handler); }, [open, onClose]);
  if (!open) return null;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-kurmesh-navy/45 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section role="dialog" aria-modal="true" aria-labelledby={titleId} className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-card bg-white p-6 shadow-panel"><div className="flex items-start justify-between gap-4"><h2 id={titleId} className="text-xl font-bold">{title}</h2><Button ref={closeRef} variant="ghost" className="min-h-11 min-w-11 p-2" aria-label="Close dialog" onClick={onClose}><X aria-hidden="true" /></Button></div><div className="mt-5">{children}</div></section></div>;
}
