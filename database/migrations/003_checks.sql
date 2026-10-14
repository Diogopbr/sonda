ALTER TABLE monitors ADD COLUMN lease_id uuid;
ALTER TABLE monitors ADD COLUMN lease_token uuid;
ALTER TABLE monitors ADD COLUMN lease_until timestamptz;
ALTER TABLE monitors ADD COLUMN next_due_at timestamptz NOT NULL DEFAULT clock_timestamp();
ALTER TABLE monitors ADD CONSTRAINT monitor_lease_complete CHECK(
  (lease_id IS NULL AND lease_token IS NULL AND lease_until IS NULL)
  OR (lease_id IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
);
CREATE TABLE check_runs (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  monitor_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  client_key uuid NOT NULL,
  origin text NOT NULL CHECK(origin IN ('manual','runner')),
  lease_token uuid NOT NULL,
  monitor_version integer NOT NULL CHECK(monitor_version>0),
  started_at timestamptz NOT NULL,
  lease_until timestamptz NOT NULL CHECK(lease_until>started_at),
  state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','finished','abandoned')),
  finished_at timestamptz,
  status_code smallint CHECK(status_code BETWEEN 100 AND 599),
  duration_ms integer CHECK(duration_ms>=0),
  error_code text,
  abandon_reason text CHECK(abandon_reason IN ('LEASE_EXPIRED','MONITOR_CHANGED')),
  UNIQUE(workspace_id,id),
  UNIQUE(workspace_id,monitor_id,id),
  UNIQUE(workspace_id,client_key),
  FOREIGN KEY(workspace_id,monitor_id) REFERENCES monitors(workspace_id,id) ON DELETE CASCADE,
  FOREIGN KEY(workspace_id,actor_id) REFERENCES users(workspace_id,id),
  CHECK(finished_at IS NULL OR finished_at>=started_at),
  CHECK((
    (state='pending' AND finished_at IS NULL AND status_code IS NULL
      AND duration_ms IS NULL AND error_code IS NULL AND abandon_reason IS NULL)
    OR (state='abandoned' AND finished_at IS NOT NULL AND abandon_reason IS NOT NULL
      AND status_code IS NULL AND duration_ms IS NULL AND error_code IS NULL)
    OR (state='finished' AND finished_at IS NOT NULL AND duration_ms IS NOT NULL
      AND abandon_reason IS NULL AND (
        (status_code BETWEEN 200 AND 299 AND error_code IS NULL)
        OR (status_code BETWEEN 300 AND 399 AND error_code='REDIRECT_NOT_ALLOWED')
        OR (status_code IS NOT NULL AND status_code NOT BETWEEN 200 AND 399 AND error_code='HTTP_STATUS')
        OR (status_code IS NULL AND error_code IN (
          'TARGET_REJECTED','DNS_REJECTED','DNS_ERROR','CONNECT_ERROR','TLS_ERROR','TIMEOUT'))
      ))
  ) IS TRUE)
);
CREATE INDEX monitor_check_history ON check_runs(workspace_id,monitor_id,started_at DESC);
ALTER TABLE monitors ADD CONSTRAINT monitor_lease_scope
  FOREIGN KEY(workspace_id,id,lease_id) REFERENCES check_runs(workspace_id,monitor_id,id);
CREATE FUNCTION protect_check_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    IF EXISTS(SELECT 1 FROM workspaces WHERE id=OLD.workspace_id) THEN
      RAISE EXCEPTION 'Check deletion requires whole environment collection' USING ERRCODE='23514';
    END IF;
    RETURN OLD;
  ELSIF TG_OP='INSERT' THEN
    IF NEW.state<>'pending' THEN
      RAISE EXCEPTION 'Checks must begin pending' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state<>'pending' OR NEW.state NOT IN ('finished','abandoned') OR
    ROW(NEW.id,NEW.workspace_id,NEW.monitor_id,NEW.actor_id,NEW.client_key,NEW.origin,
        NEW.lease_token,NEW.monitor_version,NEW.started_at,NEW.lease_until)
    IS DISTINCT FROM
    ROW(OLD.id,OLD.workspace_id,OLD.monitor_id,OLD.actor_id,OLD.client_key,OLD.origin,
        OLD.lease_token,OLD.monitor_version,OLD.started_at,OLD.lease_until) THEN
    RAISE EXCEPTION 'Check identity and final results are immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER check_run_guard BEFORE INSERT OR UPDATE OR DELETE ON check_runs
  FOR EACH ROW EXECUTE FUNCTION protect_check_run();
