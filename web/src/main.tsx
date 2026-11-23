import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import "./app.css";
import App from "./App";
import SnapshotPage from "./SnapshotPage";
import { parseSnapshotQuery } from "./snapshot";

// `?snapshot=<key>` is the render target of the snapshot service (and an invalid one reports `error`)
const snapshot = new URLSearchParams(location.search).has("snapshot") ? parseSnapshotQuery(location.search) : undefined;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {snapshot ? <SnapshotPage query={snapshot} /> : snapshot === null ? <SnapshotError /> : <App />}
  </StrictMode>,
);

function SnapshotError() {
  useEffect(() => void ((window as unknown as { __stitchcraftSnapshot: string }).__stitchcraftSnapshot = "error"), []);
  return <div data-snapshot="error" />;
}
