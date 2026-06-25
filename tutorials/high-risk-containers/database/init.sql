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

-- High Risk Containers Tutorial Database Schema
--
-- Holds a list of container image tags that are considered high risk. The
-- continuous query joins this table to the live Pods running in a Kubernetes
-- cluster. The table name and columns are quoted and PascalCase ("RiskyImage",
-- "Image", "Reason", "Mitigation") so the node label and properties Drasi sees
-- match the Cypher continuous query (which uses (i:RiskyImage) and i.Image,
-- i.Reason, i.Mitigation) without any change to the query text.

-- Suppress noisy output during setup.
\set QUIET on
SET client_min_messages = ERROR;

-- Create a user with replication privileges for CDC.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'drasi_user') THEN
        CREATE USER drasi_user WITH REPLICATION LOGIN PASSWORD 'drasi_password';
    END IF;
END
$$;

-- Grant permissions on the database.
GRANT CREATE ON DATABASE high_risk_containers TO drasi_user;
GRANT ALL PRIVILEGES ON DATABASE high_risk_containers TO drasi_user;

-- Drop existing table if it exists.
DROP TABLE IF EXISTS "RiskyImage" CASCADE;

-- RiskyImage table: one row per container image tag considered high risk.
CREATE TABLE "RiskyImage" (
    "Id"         INTEGER PRIMARY KEY,
    "Image"      VARCHAR(500) NOT NULL,
    "Reason"     VARCHAR(200) NOT NULL,
    "Mitigation" VARCHAR(200) NOT NULL
);

-- Set REPLICA IDENTITY to FULL so change events include every column.
ALTER TABLE "RiskyImage" REPLICA IDENTITY FULL;

-- Ensure drasi_user owns the table.
ALTER TABLE "RiskyImage" OWNER TO drasi_user;

-- Grant permissions to drasi_user.
GRANT USAGE ON SCHEMA public TO drasi_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO drasi_user;

-- Create the publication for logical replication.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'drasi_high_risk_containers_pub') THEN
        CREATE PUBLICATION drasi_high_risk_containers_pub FOR TABLE "RiskyImage";
    END IF;
END
$$;

-- Seed the initial set of high risk images. These match the running Pods:
--   my-app:0.1   -> Security Risk    (my-app-1 runs this image, so it is flagged)
--   redis:6.2.3  -> Compliance Issue (no Pod runs it yet, so it stays dormant)
-- Seeding happens BEFORE the replication slot is created so the existing rows
-- are loaded via bootstrap and not replayed as change events.
INSERT INTO "RiskyImage" ("Id", "Image", "Reason", "Mitigation")
SELECT * FROM (VALUES
    (1, 'ghcr.io/drasi-project/my-app:0.1', 'Security Risk', 'Update to latest version'),
    (2, 'docker.io/library/redis:6.2.3-alpine', 'Compliance Issue', 'Use official image')
) AS d("Id", "Image", "Reason", "Mitigation")
WHERE NOT EXISTS (SELECT 1 FROM "RiskyImage");

-- Create the replication slot AFTER seeding. The slot captures only changes
-- made after this point; existing rows are retrieved via bootstrap when the
-- query starts, so the seed data is not double-counted.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'drasi_high_risk_containers_slot') THEN
        PERFORM pg_create_logical_replication_slot('drasi_high_risk_containers_slot', 'pgoutput');
    END IF;
END
$$;

-- Summary.
SET client_min_messages = NOTICE;
DO $$
BEGIN
    RAISE NOTICE 'High Risk Containers database initialized successfully!';
    RAISE NOTICE 'Table: RiskyImage';
    RAISE NOTICE 'Publication: drasi_high_risk_containers_pub';
    RAISE NOTICE 'Replication slot: drasi_high_risk_containers_slot';
END
$$;
