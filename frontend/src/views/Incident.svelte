<script lang="ts">
  import { onMount } from 'svelte';
  import { api, ApiError } from '../lib/api';
  import { verify } from '../lib/check-command';
  import { QueryGate } from '../lib/query';
  import { checkLabel, checkTone, formatDate } from '../lib/status';
  import type {
    Incident,
    IncidentSummary,
    Monitor,
    MonitorDetail,
    Workspace,
    Check,
  } from '../lib/types';
  import Status from '../components/Status.svelte';
  import Notice from '../components/Notice.svelte';
  import AcknowledgementForm from '../components/AcknowledgementForm.svelte';
  import MonitorControls from '../components/MonitorControls.svelte';
  let {
    workspace,
    id,
    onCurrent,
  }: { workspace: Workspace; id: string; onCurrent: () => Promise<void> } = $props();
  let incident = $state<Incident | null>(null);
  let monitor = $state<MonitorDetail | null>(null);
  let loading = $state(true);
  let error = $state<unknown>(null);
  const gate = new QueryGate();
  const titles: Record<string, string> = {
    INCIDENT_OPENED: 'Falhas confirmadas',
    INCIDENT_ACKNOWLEDGED: 'Investigação reconhecida',
    INCIDENT_RESOLVED: 'Recuperação confirmada',
  };
  async function load(requireFresh = false): Promise<void> {
    try {
      const next = await gate.run(`${workspace.workspace_id}:${id}`, async (signal) => {
        const record = await api.read<Incident>(
          `/api/incidents/${id}`,
          workspace.workspace_id,
          signal,
        );
        const service = await api.read<MonitorDetail>(
          `/api/monitors/${record.monitor_id}`,
          workspace.workspace_id,
          signal,
        );
        return { record, service };
      });
      if (next) {
        incident = next.record;
        monitor = next.service;
        error = null;
        loading = false;
      } else if (requireFresh) {
        throw new Error('A leitura foi substituída. Revise os dados novamente.');
      }
    } catch (cause) {
      error = cause;
      loading = false;
      if (requireFresh) throw cause;
    }
  }
  async function refresh(): Promise<void> {
    await load(true);
  }
  async function acknowledge(comment: string, version: number): Promise<void> {
    const saved = await api.write<IncidentSummary>(
      `/api/incidents/${id}/ack`,
      { comment, expected_version: version },
      workspace.workspace_id,
    );
    if (incident) incident = { ...incident, ...saved };
    await load();
  }
  async function check(): Promise<Check> {
    if (!monitor) throw new Error('Service is unavailable');
    const result = await verify(workspace.workspace_id, monitor.id);
    await load();
    return result;
  }
  async function change(
    fields: { enabled?: boolean; fixture_mode?: 'available' | 'unavailable' },
    version: number,
  ): Promise<void> {
    if (!monitor) return;
    const saved = await api.write<Monitor>(
      `/api/monitors/${monitor.id}`,
      { ...fields, expected_version: version },
      workspace.workspace_id,
      'PATCH',
    );
    monitor = { ...monitor, ...saved };
    await load();
  }
  onMount(() => {
    void load();
    return () => gate.cancel();
  });
</script>

<Notice
  {error}
  onReload={error instanceof ApiError && error.status === 404 ? onCurrent : refresh}
/>
{#if loading && !incident}<p role="status" class="loading-records">
    Carregando as evidências do incidente…
  </p>{/if}
{#if incident && monitor}
  <a class="back-link" href={`/services/${monitor.id}`}>Voltar ao serviço</a>
  <header class="page-header">
    <div>
      <h1>Incidente em {monitor.name}</h1>
      <p>Da primeira falha à recuperação confirmada · horários de Brasília.</p>
    </div>
    <Status
      label={incident.state === 'resolved'
        ? 'Resolvido'
        : incident.state === 'acknowledged'
          ? 'Reconhecido'
          : 'Ativo'}
      tone={incident.state === 'resolved' ? 'good' : 'bad'}
    />
  </header>
  <a class="mobile-action-link" href="#next-observation">Verificar ou alterar cenário</a>
  <div class="work-layout">
    <div class="observations">
      <section class="evidence-section">
        <h2>Evidências do incidente</h2>
        <ol class="evidence-ledger">
          {#each [{ label: 'Primeira falha', check: incident.evidence.first_failure }, { label: 'Confirmação', check: incident.evidence.confirmation }, { label: 'Recuperação', check: incident.evidence.resolution }] as item}
            <li>
              <strong>{item.label}</strong>{#if item.check}<Status
                  label={checkLabel(item.check)}
                  tone={checkTone(item.check)}
                /><span class="numeric">{item.check.duration_ms} ms</span><time
                  datetime={item.check.finished_at ?? item.check.started_at}
                  >{formatDate(item.check.finished_at)}</time
                >
              {:else}<span class="supporting evidence-pending"
                  >Ainda sem recuperação confirmada. São necessárias duas respostas saudáveis
                  consecutivas.</span
                >{/if}
            </li>
          {/each}
        </ol>
      </section>
      <AcknowledgementForm {incident} onAcknowledge={acknowledge} onReload={refresh} />
      <section class="event-history">
        <h2>Histórico do incidente</h2>
        <ol class="event-list">
          {#each incident.events as event (event.id)}<li>
              <div>
                <strong>{titles[event.type] ?? 'Registro do incidente'}</strong><time
                  datetime={event.occurred_at}>{formatDate(event.occurred_at)}</time
                >
              </div>
              <p>
                {event.type === 'INCIDENT_ACKNOWLEDGED'
                  ? (event.actor.name ?? 'Operador')
                  : 'Confirmado pelas verificações registradas.'}
              </p>
            </li>{/each}
        </ol>
      </section>
    </div>
    <aside class="control-area">
      <MonitorControls {monitor} onVerify={check} onChange={change} onReload={refresh} />
    </aside>
  </div>
{/if}
