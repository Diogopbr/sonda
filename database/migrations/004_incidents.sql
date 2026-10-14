ALTER TABLE monitors ADD COLUMN last_check_id uuid;
ALTER TABLE monitors ADD COLUMN failure_started_at timestamptz;
ALTER TABLE monitors ADD COLUMN failure_started_check_id uuid;
ALTER TABLE monitors ADD CONSTRAINT monitor_last_check_scope
  FOREIGN KEY(workspace_id,id,last_check_id) REFERENCES check_runs(workspace_id,monitor_id,id);
ALTER TABLE monitors ADD CONSTRAINT monitor_first_failure_scope
  FOREIGN KEY(workspace_id,id,failure_started_check_id) REFERENCES check_runs(workspace_id,monitor_id,id);
ALTER TABLE monitors ADD CONSTRAINT monitor_failure_sequence CHECK(
  (failure_streak=0 AND failure_started_at IS NULL AND failure_started_check_id IS NULL)
  OR (failure_streak>0 AND failure_started_at IS NOT NULL AND failure_started_check_id IS NOT NULL)
);
CREATE TABLE incidents (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  monitor_id uuid NOT NULL,
  state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','acknowledged','resolved')),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  first_failure_at timestamptz NOT NULL,
  confirmed_at timestamptz NOT NULL CHECK(confirmed_at>=first_failure_at),
  first_failure_check_id uuid NOT NULL,
  confirmation_check_id uuid NOT NULL,
  acknowledged_at timestamptz,
  acknowledged_by uuid,
  acknowledgement text CHECK(char_length(btrim(acknowledgement)) BETWEEN 3 AND 500),
  resolved_at timestamptz,
  resolution_check_id uuid,
  UNIQUE(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,monitor_id) REFERENCES monitors(workspace_id,id) ON DELETE CASCADE,
  FOREIGN KEY(workspace_id,monitor_id,first_failure_check_id) REFERENCES check_runs(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,monitor_id,confirmation_check_id) REFERENCES check_runs(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,monitor_id,resolution_check_id) REFERENCES check_runs(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,acknowledged_by) REFERENCES users(workspace_id,id),
  CHECK(acknowledged_at IS NULL OR acknowledged_at>=confirmed_at),
  CHECK(resolved_at IS NULL OR resolved_at>=confirmed_at),
  CHECK((
    (state='open' AND acknowledged_at IS NULL AND acknowledged_by IS NULL AND acknowledgement IS NULL
      AND resolved_at IS NULL AND resolution_check_id IS NULL)
    OR (state='acknowledged' AND acknowledged_at IS NOT NULL AND acknowledged_by IS NOT NULL
      AND acknowledgement IS NOT NULL AND resolved_at IS NULL AND resolution_check_id IS NULL)
    OR (state='resolved' AND resolved_at IS NOT NULL AND resolution_check_id IS NOT NULL AND (
      (acknowledged_at IS NULL AND acknowledged_by IS NULL AND acknowledgement IS NULL)
      OR (acknowledged_at IS NOT NULL AND acknowledged_by IS NOT NULL AND acknowledgement IS NOT NULL)
    ))
  ) IS TRUE)
);
CREATE UNIQUE INDEX one_active_incident ON incidents(workspace_id,monitor_id) WHERE state<>'resolved';
CREATE TABLE events (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  monitor_id uuid NOT NULL,
  incident_id uuid,
  check_id uuid,
  actor_id uuid NOT NULL,
  type text NOT NULL CHECK(type IN (
    'INCIDENT_OPENED','INCIDENT_ACKNOWLEDGED','INCIDENT_RESOLVED','MONITOR_CHANGED')),
  occurred_at timestamptz NOT NULL,
  payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
  FOREIGN KEY(workspace_id,monitor_id) REFERENCES monitors(workspace_id,id) ON DELETE CASCADE,
  FOREIGN KEY(workspace_id,monitor_id,incident_id) REFERENCES incidents(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,monitor_id,check_id) REFERENCES check_runs(workspace_id,monitor_id,id),
  FOREIGN KEY(workspace_id,actor_id) REFERENCES users(workspace_id,id)
);
CREATE INDEX incident_event_history ON events(workspace_id,incident_id,occurred_at);
CREATE FUNCTION protect_incident() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    IF EXISTS(SELECT 1 FROM workspaces WHERE id=OLD.workspace_id) THEN
      RAISE EXCEPTION 'Incident deletion requires whole environment collection' USING ERRCODE='23514';
    END IF;
    RETURN OLD;
  ELSIF TG_OP='INSERT' THEN
    IF NEW.state<>'open' THEN
      RAISE EXCEPTION 'Incidents must begin open' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state='resolved' OR NEW.version<>OLD.version+1 OR
    NOT ((OLD.state='open' AND NEW.state IN ('acknowledged','resolved'))
      OR (OLD.state='acknowledged' AND NEW.state='resolved')) OR
    ROW(NEW.id,NEW.workspace_id,NEW.monitor_id,NEW.first_failure_at,NEW.confirmed_at,
        NEW.first_failure_check_id,NEW.confirmation_check_id)
    IS DISTINCT FROM ROW(OLD.id,OLD.workspace_id,OLD.monitor_id,OLD.first_failure_at,OLD.confirmed_at,
        OLD.first_failure_check_id,OLD.confirmation_check_id) OR
    (OLD.state='acknowledged' AND ROW(NEW.acknowledged_at,NEW.acknowledged_by,NEW.acknowledgement)
      IS DISTINCT FROM ROW(OLD.acknowledged_at,OLD.acknowledged_by,OLD.acknowledgement)) THEN
    RAISE EXCEPTION 'Incident evidence and final state are immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER incident_guard BEFORE INSERT OR UPDATE OR DELETE ON incidents
  FOR EACH ROW EXECUTE FUNCTION protect_incident();
CREATE FUNCTION protect_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' AND NOT EXISTS(SELECT 1 FROM workspaces WHERE id=OLD.workspace_id) THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'Events are append only' USING ERRCODE='23514';
END;
$$;
CREATE TRIGGER event_guard BEFORE UPDATE OR DELETE ON events
  FOR EACH ROW EXECUTE FUNCTION protect_event();
