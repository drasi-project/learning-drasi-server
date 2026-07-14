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
// It is the browser-based sibling of the terminal UI (tui/) and deliberately
// reuses the *exact same* data-access layer - ../../tui/src/db.js - so both
// front-ends run the identical SQL and report the same "which database did this
// hit" log. The browser polls /api/state; toggling a row POSTs to the server,
// which runs a real UPDATE and returns the refreshed state plus the SQL log.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import dotenv from 'dotenv';
import express from 'express';
import {
  Db,
  loadConfig,
  nextOrderStatus,
  nextVehicleLocation,
} from '../../tui/src/db.js';

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

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

async function currentState() {
  const [orders, vehicles] = await Promise.all([
    db.fetchOrders(),
    db.fetchVehicles(),
  ]);
  return { orders, vehicles, log: sqlLog };
}

app.get('/api/state', async (_req, res) => {
  try {
    res.json(await currentState());
  } catch (e) {
    res.status(500).json({ error: e.message || String(e) });
  }
});

app.post('/api/orders/:id/toggle', async (req, res) => {
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
const host = process.env.WEBUI_HOST || '0.0.0.0';

try {
  await db.connect();
} catch (e) {
  console.error('Could not connect to the databases:', e.message || String(e));
  console.error('Make sure the setup script has run and the containers are healthy.');
  process.exit(1);
}

const server = app.listen(port, host, () => {
  console.log(`Curbside Pickup web console running at http://localhost:${port}`);
  console.log('Drive changes here and watch the Drasi dashboard react in real time.');
});

async function shutdown() {
  server.close();
  await db.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
