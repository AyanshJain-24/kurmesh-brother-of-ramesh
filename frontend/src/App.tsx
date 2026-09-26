import { useLocation } from "react-router-dom";
import { AppRoutes } from "./app/routes";
import { AppShell } from "./components/layout/AppShell";

export function App() {
  const location = useLocation();
  return ["/login", "/docs"].includes(location.pathname) ? <AppRoutes /> : <AppShell><AppRoutes /></AppShell>;
}
