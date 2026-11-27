import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Inter: fallback when the system font (SF Pro on Apple devices) is not available.
// Fraunces italic: the logo signature only.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
