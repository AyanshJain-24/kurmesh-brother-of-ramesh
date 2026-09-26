import { useState, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
export function AppShell({ children }: { children: ReactNode }) { const [open, setOpen] = useState(false); const [collapsed, setCollapsed] = useState(false); return <div className="min-h-screen bg-kurmesh-polar lg:flex"><Sidebar open={open} collapsed={collapsed} onClose={() => setOpen(false)} onToggle={() => setCollapsed((value) => !value)} />{open && <button aria-label="Close navigation overlay" className="fixed inset-0 z-30 bg-kurmesh-navy/30 lg:hidden" onClick={() => setOpen(false)} />}<div className="min-w-0 flex-1"><Topbar onMenu={() => setOpen(true)} /><main className="mx-auto max-w-[1600px] p-4 sm:p-6">{children}</main></div></div>; }
