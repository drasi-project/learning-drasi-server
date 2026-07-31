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

// Database access for the Curbside Pickup web console.
//
// Connects directly to the two tutorial databases - PostgreSQL (Retail
// Operations / orders) and MySQL (Physical Operations / vehicles) - and exposes
// read + write helpers. A log callback is invoked with the human-readable SQL
// and the database it ran against, so the UI can show exactly what happened
// where.

import pg from 'pg';
import mysql from 'mysql2/promise';

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
    mysql: {
      host: env.MYSQL_HOST || 'localhost',
      port: parseInt(env.MYSQL_PORT || '3309', 10),
      database: env.MYSQL_DATABASE || 'PhysicalOperations',
      user: env.MYSQL_USER || 'drasi_user',
      password: env.MYSQL_PASSWORD || 'drasi_password',
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
    this.mysqlPool = null;
  }

  async connect() {
    // Safe to call repeatedly (the server retries): drop any pools from a
    // previous failed attempt before creating fresh ones.
    await this.close();

    this.pgPool = new pg.Pool({
      host: this.config.postgres.host,
      port: this.config.postgres.port,
      database: this.config.postgres.database,
      user: this.config.postgres.user,
      password: this.config.postgres.password,
      max: 4,
      connectionTimeoutMillis: 5000,
    });

    this.mysqlPool = mysql.createPool({
      host: this.config.mysql.host,
      port: this.config.mysql.port,
      database: this.config.mysql.database,
      user: this.config.mysql.user,
      password: this.config.mysql.password,
      connectionLimit: 4,
      connectTimeout: 5000,
    });

    // Probe both connections in parallel so failures surface immediately and a
    // slow database doesn't add to a fast one's connect time.
    await Promise.all([
      this.pgPool.query('SELECT 1'),
      this.mysqlPool.query('SELECT 1'),
    ]);
  }

  async close() {
    try { if (this.pgPool) await this.pgPool.end(); } catch { /* ignore */ }
    try { if (this.mysqlPool) await this.mysqlPool.end(); } catch { /* ignore */ }
  }

  // ---- Reads -------------------------------------------------------------

  async fetchOrders() {
    const res = await this.pgPool.query(
      'SELECT id, customer_name, driver_name, plate, status FROM orders ORDER BY id',
    );
    return res.rows;
  }

  async fetchVehicles() {
    const [rows] = await this.mysqlPool.query(
      'SELECT plate, driver_name, customer_name, make, model, color, location FROM vehicles ORDER BY plate',
    );
    return rows;
  }

  // ---- Writes ------------------------------------------------------------

  async setOrderStatus(id, status) {
    const display = `UPDATE orders SET status=${lit(status)} WHERE id=${id};`;
    this.onSql('PostgreSQL', display);
    await this.pgPool.query(
      'UPDATE orders SET status = $1 WHERE id = $2',
      [status, id],
    );
  }

  async setVehicleLocation(plate, location) {
    const display = `UPDATE vehicles SET location=${lit(location)} WHERE plate=${lit(plate)};`;
    this.onSql('MySQL', display);
    await this.mysqlPool.query(
      'UPDATE vehicles SET location = ? WHERE plate = ?',
      [location, plate],
    );
  }
}

export function nextOrderStatus(current) {
  return current === 'ready' ? 'preparing' : 'ready';
}

export function nextVehicleLocation(current) {
  return current === 'Curbside' ? 'Parking' : 'Curbside';
}

export { ORDER_STATUSES, VEHICLE_LOCATIONS };
