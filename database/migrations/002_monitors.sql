ALTER TABLE sessions ADD COLUMN actor_id uuid;
ALTER TABLE sessions ADD CONSTRAINT session_actor_scope
  FOREIGN KEY(workspace_id,actor_id) REFERENCES users(workspace_id,id) ON DELETE CASCADE;
ALTER TABLE sessions ADD CONSTRAINT session_actor_required
  CHECK((workspace_id IS NULL AND actor_id IS NULL)
    OR (workspace_id IS NOT NULL AND actor_id IS NOT NULL));
CREATE TABLE monitors (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name text NOT NULL CHECK(char_length(name) BETWEEN 3 AND 80),
  target_kind text NOT NULL CHECK(target_kind IN ('fixture','normal')),
  target_url text NOT NULL CHECK(char_length(target_url)<=2048),
  fixture_mode text CHECK(fixture_mode IN ('available','unavailable')),
  interval_seconds integer NOT NULL DEFAULT 60 CHECK(interval_seconds>=60),
  enabled boolean NOT NULL DEFAULT true,
  observed_state text NOT NULL DEFAULT 'unknown'
    CHECK(observed_state IN ('unknown','healthy','unavailable')),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  failure_streak integer NOT NULL DEFAULT 0 CHECK(failure_streak>=0),
  success_streak integer NOT NULL DEFAULT 0 CHECK(success_streak>=0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(workspace_id,id),
  UNIQUE(workspace_id,name),
  CHECK((target_kind='fixture' AND fixture_mode IS NOT NULL)
    OR (target_kind='normal' AND fixture_mode IS NULL))
);
