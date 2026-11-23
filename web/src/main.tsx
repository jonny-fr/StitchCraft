import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import "./app.css";
import App from "./App";
import SnapshotPage from "./SnapshotPage";
import { parseSnapshotQuery } from "./snapshot";
import { loadTheme } from "./storage";
import { applyTheme } from "./theme";

// `?snapshot=<key>` is the render target of the snapshot service (and an invalid one reports `error`)
const snapshot = new URLSearchParams(location.search).has("snapshot") ? parseSnapshotQuery(location.search) : undefined;
// before the first paint, so a light theme does not flash dark; the snapshot page keeps its own fixed background
if (snapshot === undefined) applyTheme(loadTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {snapshot ? <SnapshotPage query={snapshot} /> : snapshot === null ? <SnapshotError /> : <App />}
  </StrictMode>,
);

function SnapshotError() {
  useEffect(() => void ((window as unknown as { __stitchcraftSnapshot: string }).__stitchcraftSnapshot = "error"), []);
  return <div data-snapshot="error" />;
}
