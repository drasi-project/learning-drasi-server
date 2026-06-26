-- Copyright 2025 The Drasi Authors.
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Curbside Pickup Tutorial - Physical Operations (Microsoft SQL Server)
--
-- Tracks the pickup vehicles. A driver updates their `location` to 'Curbside'
-- when they arrive at the pickup zone. The Drasi MS SQL source captures changes
-- via SQL Server Change Data Capture (CDC), so the database must have CDC
-- enabled on the database and on the `vehicles` table (done below). SQL Server
-- Agent must be running for CDC capture (the container sets MSSQL_AGENT_ENABLED).
--
-- The table is `dbo.vehicles`; CDC creates the capture instance `dbo_vehicles`.
-- The Drasi source is configured with `tables: [dbo.vehicles]`, which yields the
-- node label `vehicles`, matching (v:vehicles) in the Cypher continuous queries.

-- Create the database.
IF DB_ID('PhysicalOperations') IS NULL
    CREATE DATABASE PhysicalOperations;
GO

-- Allow snapshot isolation. The Drasi MS SQL bootstrap provider reads its
-- initial snapshot inside a SNAPSHOT-isolation transaction, so this must be
-- enabled. We do it now, before CDC is enabled, while the database is idle -
-- once the CDC capture jobs are running this ALTER would block on their
-- transactions.
ALTER DATABASE PhysicalOperations SET ALLOW_SNAPSHOT_ISOLATION ON;
GO
ALTER DATABASE PhysicalOperations SET READ_COMMITTED_SNAPSHOT ON;
GO

USE PhysicalOperations;
GO

-- vehicles table: one row per pickup vehicle. `plate` is the natural key and the
-- join key to the orders table in PostgreSQL.
IF OBJECT_ID('dbo.vehicles', 'U') IS NOT NULL
    DROP TABLE dbo.vehicles;
GO

CREATE TABLE dbo.vehicles (
    plate         VARCHAR(10)  NOT NULL PRIMARY KEY,
    driver_name   VARCHAR(50)  NOT NULL,
    customer_name VARCHAR(50)  NOT NULL,
    make          VARCHAR(50)  NOT NULL,
    model         VARCHAR(50)  NOT NULL,
    color         VARCHAR(30)  NOT NULL,
    location      VARCHAR(20)  NOT NULL
        CONSTRAINT DF_vehicles_location DEFAULT 'Parking',
    -- Epoch milliseconds, set by the TUI (JavaScript Date.now()) on every change.
    -- The MS SQL source does not populate drasi.changeDateTime() and converts
    -- DATETIME2 to a string, so we store an integer the queries can do datetime
    -- arithmetic on via datetime({epochMillis: ...}). It is part of the table
    -- BEFORE CDC is enabled so the CDC capture instance includes it.
    updated_at    BIGINT       NOT NULL
        CONSTRAINT DF_vehicles_updated_at DEFAULT (DATEDIFF_BIG(MILLISECOND, '1970-01-01', SYSUTCDATETIME()))
);
GO

-- Seed three vehicles, all parked. The plates match the seeded orders in the
-- PostgreSQL database.
INSERT INTO dbo.vehicles (plate, driver_name, customer_name, make, model, color, location) VALUES
    ('A1234', 'Elijah Brooks', 'Sophia Carter', 'Toyota', 'Camry', 'Blue',  'Parking'),
    ('B5678', 'Isabella Reed', 'Mason Rivera',  'Ford',   'F-150', 'Red',   'Parking'),
    ('C9876', 'Liam Bennett',  'Ava Mitchell',  'Honda',  'Civic', 'Black', 'Parking');
GO

-- Enable Change Data Capture on the database.
EXEC sys.sp_cdc_enable_db;
GO

-- Enable CDC on the vehicles table. This creates the capture instance
-- `dbo_vehicles` and the change table cdc.dbo_vehicles_CT. @role_name = NULL
-- means no gating role, so any reader with SELECT can read the changes.
EXEC sys.sp_cdc_enable_table
    @source_schema      = N'dbo',
    @source_name        = N'vehicles',
    @role_name          = NULL,
    @supports_net_changes = 0;
GO

-- Create the Drasi login/user. For this tutorial it is given db_owner on the
-- PhysicalOperations database so it can read both the table and the CDC change
-- tables (in the `cdc` schema) without extra grants.
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'drasi_user')
    CREATE LOGIN drasi_user WITH PASSWORD = 'Drasi_Passw0rd!', CHECK_POLICY = OFF;
GO

USE PhysicalOperations;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'drasi_user')
    CREATE USER drasi_user FOR LOGIN drasi_user;
GO

ALTER ROLE db_owner ADD MEMBER drasi_user;
GO

PRINT 'Physical Operations (SQL Server) database initialized with CDC enabled.';
GO
