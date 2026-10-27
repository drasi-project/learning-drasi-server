// Copyright 2026 The Drasi Authors.
// Licensed under the Apache License, Version 2.0.
// Node 22+ supplies WebSocket; no npm dependencies are needed.
import { appendFileSync, writeFileSync } from "node:fs";

const [url, output, ready] = process.argv.slice(2);
if (!url || !output || !ready) {
  throw new Error("Usage: node watch-dashboard.mjs <ws-url> <events.jsonl> <ready-file>");
}
const socket = new WebSocket(url);
let stopping = false;
socket.addEventListener("open", () => writeFileSync(ready, "connected\n"));
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  appendFileSync(output, JSON.stringify(message) + "\n");
});
socket.addEventListener("error", (error) => {
  if (!stopping) {
    console.error("Dashboard WebSocket failed:", error);
    process.exitCode = 1;
  }
  socket.close();
});
process.on("SIGTERM", () => {
  stopping = true;
  socket.close();
});
