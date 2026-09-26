import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // GitHub Pages serves this repository below /kurmesh/; normal deployments stay at root.
  base: mode === "github-pages" ? "/kurmesh/" : "/",
}));
