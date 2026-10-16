-- A prediction may be reused by multiple idempotent batch jobs without losing job history.
CREATE TABLE zsk_job_predictions (
 job_id UUID NOT NULL REFERENCES zsk_jobs(id),
 prediction_id BIGINT NOT NULL REFERENCES zsk_predictions(id) ON DELETE CASCADE,
 PRIMARY KEY(job_id,prediction_id)
);
INSERT INTO zsk_job_predictions SELECT job_id,id FROM zsk_predictions WHERE job_id IS NOT NULL ON CONFLICT DO NOTHING;
CREATE FUNCTION zsk_prediction_reference() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.source_table='zsk_unlabeled_measurements' THEN
  IF NOT EXISTS(SELECT 1 FROM zsk_unlabeled_measurements WHERE id=NEW.measurement_id) THEN RAISE foreign_key_violation USING MESSAGE='Unknown unlabeled measurement'; END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM zsk_labeled_measurements WHERE id=NEW.measurement_id) THEN RAISE foreign_key_violation USING MESSAGE='Unknown labeled measurement'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER zsk_prediction_source BEFORE INSERT OR UPDATE ON zsk_predictions FOR EACH ROW EXECUTE FUNCTION zsk_prediction_reference();
