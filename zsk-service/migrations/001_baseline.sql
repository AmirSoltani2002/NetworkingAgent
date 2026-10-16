-- ZSK synthetic training and prediction tables, PostgreSQL 14+.
-- Populate from the provided CSV files. This is a simulation, not OEM telemetry.
CREATE TABLE IF NOT EXISTS zsk_labeled_measurements (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    machine_id TEXT NOT NULL,
    recipe TEXT NOT NULL CHECK (recipe IN ('A','B','C')),
    screw_speed_rpm DOUBLE PRECISION NOT NULL,
    screw_torque_pct DOUBLE PRECISION NOT NULL,
    motor_current_a DOUBLE PRECISION NOT NULL,
    motor_power_kw DOUBLE PRECISION NOT NULL,
    gearbox_vibration_rms_mm_s DOUBLE PRECISION NOT NULL,
    gearbox_oil_temp_c DOUBLE PRECISION NOT NULL,
    barrel_zone_temp_c DOUBLE PRECISION NOT NULL,
    melt_temp_c DOUBLE PRECISION NOT NULL,
    melt_pressure_bar DOUBLE PRECISION NOT NULL,
    feed_rate_kg_h DOUBLE PRECISION NOT NULL,
    alarm_active SMALLINT NOT NULL CHECK (alarm_active IN (0,1)),
    fault_type_simulated TEXT,
    health_label SMALLINT NOT NULL CHECK (health_label IN (0,1)),
    UNIQUE(machine_id, timestamp)
);
CREATE TABLE IF NOT EXISTS zsk_unlabeled_measurements (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    machine_id TEXT NOT NULL,
    recipe TEXT NOT NULL CHECK (recipe IN ('A','B','C')),
    screw_speed_rpm DOUBLE PRECISION NOT NULL,
    screw_torque_pct DOUBLE PRECISION NOT NULL,
    motor_current_a DOUBLE PRECISION NOT NULL,
    motor_power_kw DOUBLE PRECISION NOT NULL,
    gearbox_vibration_rms_mm_s DOUBLE PRECISION NOT NULL,
    gearbox_oil_temp_c DOUBLE PRECISION NOT NULL,
    barrel_zone_temp_c DOUBLE PRECISION NOT NULL,
    melt_temp_c DOUBLE PRECISION NOT NULL,
    melt_pressure_bar DOUBLE PRECISION NOT NULL,
    feed_rate_kg_h DOUBLE PRECISION NOT NULL,
    alarm_active SMALLINT NOT NULL CHECK (alarm_active IN (0,1)),
    UNIQUE(machine_id, timestamp)
);
CREATE TABLE IF NOT EXISTS zsk_predictions (
    id BIGSERIAL PRIMARY KEY,
    source_table TEXT NOT NULL CHECK (source_table IN ('zsk_labeled_measurements','zsk_unlabeled_measurements')),
    measurement_id BIGINT NOT NULL,
    model_version TEXT NOT NULL,
    predicted_health_label SMALLINT NOT NULL CHECK (predicted_health_label IN (0,1)),
    fault_probability DOUBLE PRECISION NOT NULL CHECK (fault_probability BETWEEN 0 AND 1),
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_table, measurement_id, model_version)
);
CREATE INDEX IF NOT EXISTS idx_zsk_labeled_machine_time ON zsk_labeled_measurements(machine_id,timestamp);
CREATE INDEX IF NOT EXISTS idx_zsk_unlabeled_machine_time ON zsk_unlabeled_measurements(machine_id,timestamp);
CREATE INDEX IF NOT EXISTS idx_zsk_predictions_version ON zsk_predictions(model_version,predicted_at);
-- Import via psql's client-side \copy (run from the directory containing the CSVs):
-- \copy zsk_labeled_measurements(timestamp,machine_id,recipe,screw_speed_rpm,screw_torque_pct,motor_current_a,motor_power_kw,gearbox_vibration_rms_mm_s,gearbox_oil_temp_c,barrel_zone_temp_c,melt_temp_c,melt_pressure_bar,feed_rate_kg_h,alarm_active,fault_type_simulated,health_label) FROM 'zsk_labeled_1000.csv' CSV HEADER
-- \copy zsk_unlabeled_measurements(timestamp,machine_id,recipe,screw_speed_rpm,screw_torque_pct,motor_current_a,motor_power_kw,gearbox_vibration_rms_mm_s,gearbox_oil_temp_c,barrel_zone_temp_c,melt_temp_c,melt_pressure_bar,feed_rate_kg_h,alarm_active) FROM 'zsk_unlabeled_1000.csv' CSV HEADER
