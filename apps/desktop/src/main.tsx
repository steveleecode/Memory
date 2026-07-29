import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@memory/ui/styles.css";
import { MemoryFoundation } from "@memory/ui";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element not found");
}

createRoot(root).render(
  <StrictMode>
    <MemoryFoundation />
  </StrictMode>,
);
