import { expect, it } from 'vitest';
import { observationState, checkLabel } from './status';
import type { Monitor } from './types';

const monitor: Monitor = {
  id: 'm',
  name: 'API de pedidos',
  target_kind: 'fixture',
  target_url: '',
  interval_seconds: 60,
  fixture_mode: 'available',
  enabled: true,
  observed_state: 'unknown',
  version: 1,
  failure_streak: 0,
  success_streak: 0,
  last_check: null,
  active_incident: null,
};

it('never labels an unmeasured monitor healthy and distinguishes a first failure from confirmed outage', () => {
  expect(observationState(monitor).label).toBe('Sem medição');
  expect(observationState({ ...monitor, failure_streak: 1 }).label).toBe('Falha observada · 1/2');
  expect(
    observationState({ ...monitor, observed_state: 'unavailable', failure_streak: 2 }).label,
  ).toBe('Indisponível');
});

it('does not call one recovery sample healthy and preserves a paused state', () => {
  const unavailable = { ...monitor, observed_state: 'unavailable' as const, success_streak: 1 };
  expect(observationState(unavailable).label).toBe('Recuperação · 1/2');
  expect(observationState({ ...unavailable, enabled: false }).label).toBe('Pausado');
});

it('distinguishes discarded execution and missing HTTP response from service failure', () => {
  expect(checkLabel({ state: 'abandoned', status_code: null, error_code: null })).toBe(
    'Descartada',
  );
  expect(checkLabel({ state: 'finished', status_code: null, error_code: 'TIMEOUT' })).toBe(
    'Prazo excedido',
  );
  expect(checkLabel({ state: 'finished', status_code: 503, error_code: 'HTTP_STATUS' })).toBe(
    'HTTP 503',
  );
});
