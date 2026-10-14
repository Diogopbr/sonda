import { expect, it } from 'vitest';
import { evidenceRole } from './evidence';
import type { IncidentSummary } from './types';

it('links only actual incident evidence and never invents a recovery sample', () => {
  const incident = {
    id: 'incident',
    first_failure_check_id: 'first',
    confirmation_check_id: 'second',
    resolution_check_id: null,
  } as IncidentSummary;
  expect(evidenceRole('first', [incident])).toEqual({
    id: 'incident',
    label: 'Primeira falha do incidente',
  });
  expect(evidenceRole('second', [incident])?.label).toBe('Confirmação do incidente');
  expect(evidenceRole('unrelated', [incident])).toBeNull();
  expect(
    evidenceRole('recovered', [{ ...incident, resolution_check_id: 'recovered' }])?.label,
  ).toBe('Recuperação confirmada');
});
