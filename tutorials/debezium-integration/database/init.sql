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

-- Debezium Integration Tutorial Database Schema
--
-- Same Building -> Floor -> Room model as the Building Comfort tutorial.
-- Debezium (Server or Kafka Connect) owns the replication slot / publication.
-- Tables are quoted PascalCase so node labels match the Cypher queries.

\set QUIET on
SET client_min_messages = ERROR;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'drasi_user') THEN
        CREATE USER drasi_user WITH REPLICATION LOGIN PASSWORD 'drasi_password';
    END IF;
END
$$;

GRANT CREATE ON DATABASE building_comfort TO drasi_user;
GRANT ALL PRIVILEGES ON DATABASE building_comfort TO drasi_user;

DROP TABLE IF EXISTS "Room" CASCADE;
DROP TABLE IF EXISTS "Floor" CASCADE;
DROP TABLE IF EXISTS "Building" CASCADE;

CREATE TABLE "Building" (
    id   VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE "Floor" (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    building_id VARCHAR(50) NOT NULL,
    FOREIGN KEY (building_id) REFERENCES "Building"(id) ON DELETE CASCADE
);

CREATE TABLE "Room" (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    temperature INTEGER,
    humidity    INTEGER,
    co2         INTEGER,
    floor_id    VARCHAR(50) NOT NULL,
    FOREIGN KEY (floor_id) REFERENCES "Floor"(id) ON DELETE CASCADE
);

-- FULL replica identity so update/delete events include every column.
ALTER TABLE "Building" REPLICA IDENTITY FULL;
ALTER TABLE "Floor" REPLICA IDENTITY FULL;
ALTER TABLE "Room" REPLICA IDENTITY FULL;

ALTER TABLE "Building" OWNER TO drasi_user;
ALTER TABLE "Floor" OWNER TO drasi_user;
ALTER TABLE "Room" OWNER TO drasi_user;

GRANT USAGE ON SCHEMA public TO drasi_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO drasi_user;
-- Debezium creates a filtered publication over tables owned by drasi_user
-- and a logical replication slot (requires REPLICATION, already granted).
GRANT CREATE ON SCHEMA public TO drasi_user;

INSERT INTO "Building" (id, name)
SELECT * FROM (VALUES ('building_01', 'Building 01')) AS d(id, name)
WHERE NOT EXISTS (SELECT 1 FROM "Building");

INSERT INTO "Floor" (id, name, building_id)
SELECT * FROM (VALUES
    ('floor_01_01', 'Floor 01', 'building_01'),
    ('floor_01_02', 'Floor 02', 'building_01'),
    ('floor_01_03', 'Floor 03', 'building_01')
) AS d(id, name, building_id)
WHERE NOT EXISTS (SELECT 1 FROM "Floor");

INSERT INTO "Room" (id, name, temperature, humidity, co2, floor_id)
SELECT * FROM (VALUES
    ('room_01_01_01', 'Room 01', 70, 40, 10, 'floor_01_01'),
    ('room_01_01_02', 'Room 02', 70, 40, 10, 'floor_01_01'),
    ('room_01_01_03', 'Room 03', 70, 40, 10, 'floor_01_01'),
    ('room_01_02_01', 'Room 01', 70, 40, 10, 'floor_01_02'),
    ('room_01_02_02', 'Room 02', 70, 40, 10, 'floor_01_02'),
    ('room_01_02_03', 'Room 03', 70, 40, 10, 'floor_01_02'),
    ('room_01_03_01', 'Room 01', 70, 40, 10, 'floor_01_03'),
    ('room_01_03_02', 'Room 02', 70, 40, 10, 'floor_01_03'),
    ('room_01_03_03', 'Room 03', 70, 40, 10, 'floor_01_03')
) AS d(id, name, temperature, humidity, co2, floor_id)
WHERE NOT EXISTS (SELECT 1 FROM "Room");

SET client_min_messages = NOTICE;
DO $$
BEGIN
    RAISE NOTICE 'Debezium integration database initialized successfully!';
    RAISE NOTICE 'Tables: Building, Floor, Room (seeded, ready for Debezium snapshot)';
END
$$;
