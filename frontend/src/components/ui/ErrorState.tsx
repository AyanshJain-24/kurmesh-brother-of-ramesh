import type { ReactNode } from "react";
import { Alert } from "./Alert";
export function ErrorState({ title = "Unable to load information", message, retry }: { title?: string; message?: string; retry?: ReactNode }) { return <Alert variant="danger" title={title}><p>{message ?? "Please check the connection and try again."}</p>{retry && <div className="mt-3">{retry}</div>}</Alert>; }
