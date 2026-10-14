import type { IncidentSummary } from './types';

export function evidenceRole(
  checkId: string,
  incidents: IncidentSummary[],
): { id: string; label: string } | null {
  for (const incident of incidents) {
    if (incident.first_failure_check_id === checkId)
      return { id: incident.id, label: 'Primeira falha do incidente' };
    if (incident.confirmation_check_id === checkId)
      return { id: incident.id, label: 'Confirmação do incidente' };
    if (incident.resolution_check_id === checkId)
      return { id: incident.id, label: 'Recuperação confirmada' };
  }
  return null;
}
