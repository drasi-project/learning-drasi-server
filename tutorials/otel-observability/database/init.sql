-- Copyright 2026 The Drasi Authors.
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

-- OTel Observability Tutorial Database Schema
--
-- Holds per-service SLO thresholds. The continuous query joins this table to
-- OTel-projected Service/Metric nodes. The table name is unquoted snake_case
-- so the node label Drasi sees matches the validated Cypher
-- ((p:service_slo_policy)).

\set QUIET on
SET client_min_messages = ERROR;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'drasi_user') THEN
        CREATE USER drasi_user WITH REPLICATION LOGIN PASSWORD 'drasi_password';
    END IF;
END
$$;

GRANT CREATE ON DATABASE otel_observability TO drasi_user;
GRANT ALL PRIVILEGES ON DATABASE otel_observability TO drasi_user;

DROP TABLE IF EXISTS service_slo_policy CASCADE;

CREATE TABLE service_slo_policy (
    service_name text NOT NULL,
    metric_name text NOT NULL,
    threshold_ms double precision NOT NULL,
    PRIMARY KEY (service_name, metric_name)
);

ALTER TABLE service_slo_policy REPLICA IDENTITY FULL;
ALTER TABLE service_slo_policy OWNER TO drasi_user;

GRANT USAGE ON SCHEMA public TO drasi_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO drasi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO drasi_user;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'drasi_otel_observability_pub') THEN
        CREATE PUBLICATION drasi_otel_observability_pub FOR TABLE service_slo_policy;
    END IF;
END
$$;

INSERT INTO service_slo_policy (service_name, metric_name, threshold_ms)
SELECT * FROM (VALUES
    ('checkout', 'latency_p99_ms', 750::double precision)
) AS d(service_name, metric_name, threshold_ms)
WHERE NOT EXISTS (SELECT 1 FROM service_slo_policy);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'drasi_otel_observability_slot') THEN
        PERFORM pg_create_logical_replication_slot('drasi_otel_observability_slot', 'pgoutput');
    END IF;
END
$$;

SET client_min_messages = NOTICE;
DO $$
BEGIN
    RAISE NOTICE 'OTel Observability database initialized successfully!';
    RAISE NOTICE 'Table: service_slo_policy';
    RAISE NOTICE 'Publication: drasi_otel_observability_pub';
    RAISE NOTICE 'Replication slot: drasi_otel_observability_slot';
END
$$;
