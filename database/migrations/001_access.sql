CREATE TABLE visitors (
  id uuid PRIMARY KEY,
  token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE workspaces (
  id uuid PRIMARY KEY,
  kind text NOT NULL CHECK(kind IN ('normal','demo')),
  visitor_id uuid REFERENCES visitors(id),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  revoked_at timestamptz,
  CHECK((kind='demo' AND visitor_id IS NOT NULL AND expires_at IS NOT NULL)
    OR (kind='normal' AND visitor_id IS NULL AND expires_at IS NULL))
);
CREATE UNIQUE INDEX one_normal_workspace ON workspaces(kind) WHERE kind='normal';
CREATE INDEX workspace_collection ON workspaces(expires_at) WHERE kind='demo';
CREATE TABLE users (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email text NOT NULL,
  name text NOT NULL,
  password_hash text NOT NULL,
  UNIQUE(workspace_id,id),
  UNIQUE(workspace_id,email)
);
CREATE TABLE sessions (
  id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{64}$'),
  workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
  payload jsonb NOT NULL,
  expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE rate_limits (
  key text NOT NULL,
  bucket timestamptz NOT NULL,
  hits integer NOT NULL CHECK(hits>0),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(key,bucket)
);
CREATE INDEX rate_limits_expiry ON rate_limits(expires_at);
CREATE TABLE maintenance (
  id boolean PRIMARY KEY DEFAULT true CHECK(id),
  last_cleanup_at timestamptz
);
INSERT INTO maintenance(id) VALUES(true);
