import type { Check, Monitor } from './types';

export type Tone = 'quiet' | 'good' | 'warning' | 'bad' | 'recovery';
export function observationState(monitor: Monitor): { label: string; tone: Tone } {
  if (!monitor.enabled) return { label: 'Pausado', tone: 'quiet' };
  if (monitor.observed_state === 'unavailable') {
    return monitor.success_streak === 1
      ? { label: 'Recuperação · 1/2', tone: 'recovery' }
      : { label: 'Indisponível', tone: 'bad' };
  }
  if (monitor.failure_streak === 1) return { label: 'Falha observada · 1/2', tone: 'warning' };
  if (monitor.last_check === null || monitor.observed_state === 'unknown')
    return { label: 'Sem medição', tone: 'quiet' };
  return { label: 'Saudável', tone: 'good' };
}

const errors: Record<string, string> = {
  TIMEOUT: 'Prazo excedido',
  DNS_REJECTED: 'Destino de rede recusado',
  DNS_ERROR: 'DNS sem resposta',
  TARGET_REJECTED: 'Alvo não autorizado',
  CONNECT_ERROR: 'Conexão interrompida',
  TLS_ERROR: 'Certificado recusado',
};
export function checkLabel(check: Pick<Check, 'state' | 'status_code' | 'error_code'>): string {
  if (check.state === 'abandoned') return 'Descartada';
  if (check.state === 'pending') return 'Em andamento';
  if (check.status_code !== null) return `HTTP ${check.status_code}`;
  return errors[check.error_code ?? ''] ?? 'Sem resposta HTTP';
}

export function checkTone(check: Check): Tone {
  if (check.state !== 'finished') return 'quiet';
  return check.error_code === null ? 'good' : 'bad';
}

const dateFormatter = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});
export function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : 'Ainda não verificado';
}
export function resultAge(value: string | null, now = Date.now()): string {
  if (!value) return 'Sem observações';
  const minutes = Math.max(0, Math.floor((now - new Date(value).getTime()) / 60000));
  if (minutes === 0) return 'Há menos de 1 min';
  if (minutes < 60) return `Há ${minutes} min`;
  if (minutes < 1440) return `Há ${Math.floor(minutes / 60)} h`;
  return `Há ${Math.floor(minutes / 1440)} dias`;
}
