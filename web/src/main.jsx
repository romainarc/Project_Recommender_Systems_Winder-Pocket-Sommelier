import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Inter: fallback when the system font (SF Pro on Apple devices) is not available.
// Fraunces italic: the logo signature only.
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
