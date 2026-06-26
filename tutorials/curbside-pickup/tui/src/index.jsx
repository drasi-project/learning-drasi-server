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

// Curbside Pickup TUI
//
// A single full-screen terminal app with two panels:
//   - Retail Operations  (PostgreSQL): toggle an order's status preparing<->ready
//   - Physical Operations (SQL Server): toggle a vehicle's location Parking<->Curbside
// Every change runs a real SQL UPDATE; the bottom pane logs each statement and
// the database it hit. Drive changes here and watch the Drasi dashboards at
// http://localhost:3000 react in real time.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import dotenv from 'dotenv';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { render, Box, Text, useApp, useInput } from 'ink';
import {
  Db,
  loadConfig,
  nextOrderStatus,
  nextVehicleLocation,
} from './db.js';

// Load environment defaults from the tutorial's .env (one level up), if present.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

const MAX_LOG = 8;

function pad(value, width) {
  const s = value == null ? '' : String(value);
  return s.length >= width ? s.slice(0, width) : s + ' '.repeat(width - s.length);
}

function Panel({ title, subtitle, focused, headers, widths, rows, selected, renderCell }) {
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={focused ? 'cyan' : 'gray'}
      paddingX={1}
      width="50%"
    >
      <Text bold color={focused ? 'cyan' : 'white'}>
        {title}
      </Text>
      <Text color="gray">{subtitle}</Text>
      <Box marginTop={1}>
        <Text bold color="gray">
          {'  '}
          {headers.map((h, i) => pad(h, widths[i])).join(' ')}
        </Text>
      </Box>
      {rows.map((row, idx) => {
        const isSel = focused && idx === selected;
        return (
          <Text key={idx} inverse={isSel}>
            {isSel ? '> ' : '  '}
            {row.map((cell, i) => {
              const node = renderCell ? renderCell(rows, idx, i, pad(cell.text, widths[i])) : pad(cell.text, widths[i]);
              return (
                <Text key={i} color={isSel ? undefined : cell.color}>
                  {node}
                  {i < row.length - 1 ? ' ' : ''}
                </Text>
              );
            })}
          </Text>
        );
      })}
      {rows.length === 0 && <Text color="gray">  (no rows)</Text>}
    </Box>
  );
}

function App() {
  const { exit } = useApp();
  const dbRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [orders, setOrders] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [focus, setFocus] = useState('orders'); // 'orders' | 'vehicles'
  const [orderSel, setOrderSel] = useState(0);
  const [vehicleSel, setVehicleSel] = useState(0);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);

  const pushLog = useCallback((db, text) => {
    setLog((prev) => [...prev.slice(-(MAX_LOG - 1)), { db, text, t: new Date() }]);
  }, []);

  const refresh = useCallback(async () => {
    const db = dbRef.current;
    if (!db) return;
    const [o, v] = await Promise.all([db.fetchOrders(), db.fetchVehicles()]);
    setOrders(o);
    setVehicles(v);
  }, []);

  useEffect(() => {
    let interval;
    (async () => {
      try {
        const db = new Db(loadConfig(), pushLog);
        await db.connect();
        dbRef.current = db;
        await refresh();
        setReady(true);
        interval = setInterval(() => {
          refresh().catch(() => {});
        }, 3000);
      } catch (e) {
        setError(e.message || String(e));
      }
    })();
    return () => {
      if (interval) clearInterval(interval);
      if (dbRef.current) dbRef.current.close();
    };
  }, [pushLog, refresh]);

  const toggleSelected = useCallback(async () => {
    if (busy || !ready) return;
    setBusy(true);
    try {
      if (focus === 'orders') {
        const row = orders[orderSel];
        if (row) await dbRef.current.setOrderStatus(row.id, nextOrderStatus(row.status));
      } else {
        const row = vehicles[vehicleSel];
        if (row) await dbRef.current.setVehicleLocation(row.plate, nextVehicleLocation(row.location));
      }
      await refresh();
    } catch (e) {
      pushLog('error', e.message || String(e));
    } finally {
      setBusy(false);
    }
  }, [busy, ready, focus, orders, orderSel, vehicles, vehicleSel, refresh, pushLog]);

  useInput((input, key) => {
    if (input === 'q' || (key.ctrl && input === 'c')) {
      exit();
      return;
    }
    if (key.tab || key.leftArrow || key.rightArrow) {
      setFocus((f) => (f === 'orders' ? 'vehicles' : 'orders'));
      return;
    }
    if (key.upArrow) {
      if (focus === 'orders') setOrderSel((s) => Math.max(0, s - 1));
      else setVehicleSel((s) => Math.max(0, s - 1));
      return;
    }
    if (key.downArrow) {
      if (focus === 'orders') setOrderSel((s) => Math.min(Math.max(0, orders.length - 1), s + 1));
      else setVehicleSel((s) => Math.min(Math.max(0, vehicles.length - 1), s + 1));
      return;
    }
    if (key.return || input === ' ') {
      toggleSelected();
    }
  });

  if (error) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text color="red" bold>Could not connect to the databases:</Text>
        <Text color="red">{error}</Text>
        <Text color="gray">Make sure ./scripts/setup-database.sh has run and the containers are healthy.</Text>
      </Box>
    );
  }

  if (!ready) {
    return (
      <Box padding={1}>
        <Text color="cyan">Connecting to PostgreSQL and SQL Server…</Text>
      </Box>
    );
  }

  const orderRows = orders.map((o) => [
    { text: o.id },
    { text: o.customer_name },
    { text: o.plate },
    { text: o.status, color: o.status === 'ready' ? 'green' : 'yellow' },
  ]);
  const vehicleRows = vehicles.map((v) => [
    { text: v.plate },
    { text: `${v.make} ${v.model}` },
    { text: v.color },
    { text: v.location, color: v.location === 'Curbside' ? 'green' : 'gray' },
  ]);

  const dbColor = (db) => (db === 'PostgreSQL' ? 'blue' : db === 'SQL Server' ? 'magenta' : 'red');

  return (
    <Box flexDirection="column">
      <Box justifyContent="center">
        <Text bold color="cyanBright">🚗  Curbside Pickup — Operations Console</Text>
      </Box>
      <Box>
        <Panel
          title="Retail Operations"
          subtitle="PostgreSQL · orders"
          focused={focus === 'orders'}
          headers={['ID', 'Customer', 'Plate', 'Status']}
          widths={[3, 16, 6, 10]}
          rows={orderRows}
          selected={orderSel}
        />
        <Panel
          title="Physical Operations"
          subtitle="SQL Server · vehicles"
          focused={focus === 'vehicles'}
          headers={['Plate', 'Vehicle', 'Color', 'Location']}
          widths={[6, 16, 7, 10]}
          rows={vehicleRows}
          selected={vehicleSel}
        />
      </Box>

      <Box flexDirection="column" borderStyle="round" borderColor="gray" paddingX={1}>
        <Text bold color="gray">SQL log (most recent last)</Text>
        {log.length === 0 && <Text color="gray">  no statements yet — select a row and press Enter</Text>}
        {log.map((entry, i) => (
          <Text key={i}>
            <Text color={dbColor(entry.db)}>[{entry.db}]</Text>
            <Text> {entry.text}</Text>
          </Text>
        ))}
      </Box>

      <Box paddingX={1}>
        <Text color="gray">
          Tab/←/→ switch panel · ↑/↓ select · Enter toggle · q quit{busy ? '  · working…' : ''}
        </Text>
      </Box>
    </Box>
  );
}

render(<App />);
