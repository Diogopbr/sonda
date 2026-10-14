export type Workspace = { workspace_id: string; kind: 'demo' | 'normal'; expires_at: string };
export type Capabilities = { demo_enabled: boolean; login_enabled: boolean };
export type CheckState = 'pending' | 'finished' | 'abandoned';
export type Check = {
  id: string;
  monitor_id: string;
  state: CheckState;
  status_code: number | null;
  duration_ms: number | null;
  error_code: string | null;
  abandon_reason: string | null;
  started_at: string;
  finished_at: string | null;
  origin: 'manual' | 'runner';
};
export type IncidentSummary = {
  id: string;
  monitor_id: string;
  state: 'open' | 'acknowledged' | 'resolved';
  version: number;
  first_failure_at: string;
  confirmed_at: string;
  first_failure_check_id: string;
  confirmation_check_id: string;
  resolved_at: string | null;
  resolution_check_id: string | null;
  acknowledged_at: string | null;
  acknowledgement: string | null;
  acknowledged_by: { id: string; name: string | null } | null;
};
export type Incident = IncidentSummary & {
  evidence: { first_failure: Check; confirmation: Check; resolution: Check | null };
  events: {
    id: string;
    type: string;
    occurred_at: string;
    payload: Record<string, unknown>;
    actor: { id: string; name: string | null };
  }[];
};
export type Monitor = {
  id: string;
  name: string;
  target_kind: 'fixture' | 'normal';
  target_url: string;
  interval_seconds: number;
  fixture_mode: 'available' | 'unavailable' | null;
  enabled: boolean;
  observed_state: 'unknown' | 'healthy' | 'unavailable';
  version: number;
  failure_streak: number;
  success_streak: number;
  last_check: Check | null;
  active_incident: IncidentSummary | null;
};
export type MonitorDetail = Monitor & {
  checks: Check[];
  history_limit: number;
  incidents: IncidentSummary[];
  incident_history_limit: number;
};
