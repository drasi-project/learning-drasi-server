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

// Database access for the Curbside Pickup TUI.
//
// Connects directly to the two tutorial databases - PostgreSQL (Retail
// Operations / orders) and SQL Server (Physical Operations / vehicles) - and
// exposes read + write helpers. Every write also bumps an `updated_at` column to
// the current epoch-millisecond time (Date.now()); the Drasi MS SQL source does
// not populate change timestamps itself, so the continuous queries read this
// column instead. A log callback is invoked with the human-readable SQL and the
// database it ran against, so the UI can show exactly what happened where.

import pg from 'pg';
import sql from 'mssql';

const ORDER_STATUSES = ['preparing', 'ready'];
const VEHICLE_LOCATIONS = ['Parking', 'Curbside'];

export function loadConfig() {
  const env = process.env;
  return {
    postgres: {
      host: env.POSTGRES_HOST || 'localhost',
      port: parseInt(env.POSTGRES_PORT || '5742', 10),
      database: env.POSTGRES_DATABASE || 'RetailOperations',
      user: env.POSTGRES_USER || 'drasi_user',
      password: env.POSTGRES_PASSWORD || 'drasi_password',
    },
    mssql: {
      host: env.MSSQL_HOST || 'localhost',
      port: parseInt(env.MSSQL_PORT || '1435', 10),
      database: env.MSSQL_DATABASE || 'PhysicalOperations',
      user: env.MSSQL_USER || 'drasi_user',
      password: env.MSSQL_PASSWORD || 'Drasi_Passw0rd!',
    },
  };
}

// Format a value for display inside a logged SQL statement.
function lit(value) {
  if (typeof value === 'number') return String(value);
  return `'${String(value).replace(/'/g, "''")}'`;
}

export class Db {
  constructor(config, onSql) {
    this.config = config;
    this.onSql = onSql || (() => {});
    this.pgPool = null;
    this.mssqlPool = null;
  }

  async connect() {
    this.pgPool = new pg.Pool({
      host: this.config.postgres.host,
      port: this.config.postgres.port,
      database: this.config.postgres.database,
      user: this.config.postgres.user,
      password: this.config.postgres.password,
      max: 4,
    });
    // Probe the connection so failures surface immediately.
    await this.pgPool.query('SELECT 1');

    this.mssqlPool = await new sql.ConnectionPool({
      server: this.config.mssql.host,
      port: this.config.mssql.port,
      database: this.config.mssql.database,
      user: this.config.mssql.user,
      password: this.config.mssql.password,
      options: { encrypt: false, trustServerCertificate: true },
      pool: { max: 4 },
    }).connect();
  }

  async close() {
    try { if (this.pgPool) await this.pgPool.end(); } catch { /* ignore */ }
    try { if (this.mssqlPool) await this.mssqlPool.close(); } catch { /* ignore */ }
  }

  // ---- Reads -------------------------------------------------------------

  async fetchOrders() {
    const res = await this.pgPool.query(
      'SELECT id, customer_name, driver_name, plate, status FROM orders ORDER BY id',
    );
    return res.rows;
  }

  async fetchVehicles() {
    const res = await this.mssqlPool.request().query(
      'SELECT plate, driver_name, customer_name, make, model, color, location FROM dbo.vehicles ORDER BY plate',
    );
    return res.recordset;
  }

  // ---- Writes ------------------------------------------------------------

  async setOrderStatus(id, status) {
    const ts = Date.now();
    const display = `UPDATE orders SET status=${lit(status)}, updated_at=${ts} WHERE id=${id};`;
    this.onSql('PostgreSQL', display);
    await this.pgPool.query(
      'UPDATE orders SET status = $1, updated_at = $2 WHERE id = $3',
      [status, ts, id],
    );
  }

  async setVehicleLocation(plate, location) {
    const ts = Date.now();
    const display = `UPDATE dbo.vehicles SET location=${lit(location)}, updated_at=${ts} WHERE plate=${lit(plate)};`;
    this.onSql('SQL Server', display);
    await this.mssqlPool
      .request()
      .input('loc', sql.VarChar(20), location)
      .input('ts', sql.BigInt, ts)
      .input('plate', sql.VarChar(10), plate)
      .query('UPDATE dbo.vehicles SET location = @loc, updated_at = @ts WHERE plate = @plate');
  }
}

export function nextOrderStatus(current) {
  return current === 'ready' ? 'preparing' : 'ready';
}

export function nextVehicleLocation(current) {
  return current === 'Curbside' ? 'Parking' : 'Curbside';
}

export { ORDER_STATUSES, VEHICLE_LOCATIONS };
