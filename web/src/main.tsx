import "@fontsource-variable/noto-sans";
import "@fontsource-variable/noto-sans-devanagari";
import "./styles/app.css";
import "./i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
