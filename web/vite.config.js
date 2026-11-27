import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the app on http://localhost:5173 and forwards the API calls to FastAPI.
// `npm run build` writes web/dist, which FastAPI serves on http://localhost:8000.
const API = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      ["/options", "/health", "/onboard", "/recommend", "/log_interaction", "/dishes"].map((p) => [p, API]),
    ),
  },
});
