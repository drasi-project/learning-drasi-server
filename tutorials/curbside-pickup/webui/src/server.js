// Copyright 2025 The Drasi Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Curbside Pickup web console (server)
//
// A tiny Express server that drives change against the two tutorial databases.
// It connects directly to both - PostgreSQL (Retail Operations / orders) and
// MySQL (Physical Operations / vehicles) - and serves a static page that lets
// you toggle rows. Every action runs a real SQL UPDATE and is reported with the
// database it hit. The browser polls /api/state; toggling a row POSTs to the
// server, which runs the UPDATE and returns the refreshed state plus the SQL
// log. It is started automatically alongside Drasi Server (see
// scripts/start-server.sh); open http://localhost:3001 once it is running.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import dotenv from 'dotenv';
import express from 'express';
import {
  Db,
  loadConfig,
  nextOrderStatus,
  nextVehicleLocation,
} from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load environment defaults from the tutorial's .env (two levels up), if present.
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

const MAX_LOG = 20;

// Rolling log of the SQL statements run, shared with the browser. Each entry is
// { db, text, t } - the database it hit, the statement, and an ISO timestamp.
const sqlLog = [];
function pushLog(db, text) {
  sqlLog.push({ db, text, t: new Date().toISOString() });
  while (sqlLog.length > MAX_LOG) sqlLog.shift();
}

const db = new Db(loadConfig(), pushLog);

// Track database readiness so the HTTP server can come up instantly and report
// a friendly "connecting" state until both pools are live.
let dbReady = false;

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'static')));

async function currentState() {
  const [orders, vehicles] = await Promise.all([
    db.fetchOrders(),
    db.fetchVehicles(),
  ]);
  return { orders, vehicles, log: sqlLog };
}

app.get('/api/state', async (_req, res) => {
  if (!dbReady) return res.json({ connecting: true, log: sqlLog });
  try {
    res.json(await currentState());
  } catch (e) {
    res.status(500).json({ error: e.message || String(e) });
  }
});

app.post('/api/orders/:id/toggle', async (req, res) => {
  if (!dbReady) return res.status(503).json({ error: 'connecting to databases' });
  try {
    const orders = await db.fetchOrders();
    const row = orders.find((o) => String(o.id) === String(req.params.id));
    if (!row) return res.status(404).json({ error: 'order not found' });
    await db.setOrderStatus(row.id, nextOrderStatus(row.status));
    res.json(await currentState());
  } catch (e) {
    pushLog('error', e.message || String(e));
    res.status(500).json({ error: e.message || String(e) });
  }
});

app.post('/api/vehicles/:plate/toggle', async (req, res) => {
  if (!dbReady) return res.status(503).json({ error: 'connecting to databases' });
  try {
    const vehicles = await db.fetchVehicles();
    const row = vehicles.find((v) => v.plate === req.params.plate);
    if (!row) return res.status(404).json({ error: 'vehicle not found' });
    await db.setVehicleLocation(row.plate, nextVehicleLocation(row.location));
    res.json(await currentState());
  } catch (e) {
    pushLog('error', e.message || String(e));
    res.status(500).json({ error: e.message || String(e) });
  }
});

const port = parseInt(process.env.WEBUI_PORT || '3001', 10);
// Bind host: default to undefined so Node listens on the dual-stack wildcard
// (::), which accepts both IPv6 (::1) and IPv4 (127.0.0.1) loopback. Binding
// explicitly to 0.0.0.0 is IPv4-only, and on Windows "localhost" resolves to
// ::1 first - so the browser stalls retrying IPv6 before falling back, making
// the console appear to "take forever to load". Set WEBUI_HOST to override.
const host = process.env.WEBUI_HOST || undefined;

// Start the HTTP server right away so the page is reachable immediately, even
// while the databases are still coming up.
const server = app.listen(port, host, () => {
  console.log(`Curbside Pickup web console running at http://localhost:${port}`);
  console.log('Drive changes here and watch the Drasi dashboard react in real time.');
});

// Connect to the databases in the background, retrying until they are ready.
// The two databases and Drasi Server all start together, so a few early
// attempts may fail while the containers finish initializing.
(async function connectWithRetry() {
  for (let attempt = 1; ; attempt += 1) {
    try {
      await db.connect();
      dbReady = true;
      console.log('Connected to PostgreSQL and MySQL.');
      return;
    } catch (e) {
      if (attempt === 1 || attempt % 5 === 0) {
        console.log(`Waiting for the databases... (${e.message || e})`);
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
})();

async function shutdown() {
  server.close();
  await db.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
