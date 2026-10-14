<script lang="ts">
  import { onMount } from 'svelte';
  import { api, ApiError } from '../lib/api';
  import { verify } from '../lib/check-command';
  import { QueryGate } from '../lib/query';
  import { evidenceRole } from '../lib/evidence';
  import { checkLabel, formatDate, observationState } from '../lib/status';
  import type { Check, Monitor, MonitorDetail, Workspace } from '../lib/types';
  import Status from '../components/Status.svelte';
  import Notice from '../components/Notice.svelte';
  import MonitorControls from '../components/MonitorControls.svelte';
  import SampleStrip from '../components/SampleStrip.svelte';
  import CheckTable from '../components/CheckTable.svelte';
  let {
    workspace,
    id,
    onCurrent,
  }: { workspace: Workspace; id: string; onCurrent: () => Promise<void> } = $props();
  let monitor = $state<MonitorDetail | null>(null);
  let loading = $state(true);
  let error = $state<unknown>(null);
  let selected = $state<string | null>(null);
  const gate = new QueryGate();
  const selectedCheck = $derived(monitor?.checks.find((check) => check.id === selected) ?? null);
  const selectedEvidence = $derived(
    selected ? evidenceRole(selected, monitor?.incidents ?? []) : null,
  );
  async function load(): Promise<void> {
    try {
      const next = await gate.run(`${workspace.workspace_id}:${id}`, (signal) =>
        api.read<MonitorDetail>(`/api/monitors/${id}`, workspace.workspace_id, signal),
      );
      if (next) {
        monitor = next;
        error = null;
        loading = false;
        if (!selected) selected = next.checks[0]?.id ?? null;
      }
    } catch (cause) {
      error = cause;
      loading = false;
    }
  }
  async function check(): Promise<Check> {
    const result = await verify(workspace.workspace_id, id);
    selected = result.id;
    await load();
    return result;
  }
  async function change(
    fields: { enabled?: boolean; fixture_mode?: 'available' | 'unavailable' },
    version: number,
  ): Promise<void> {
    const updated = await api.write<Monitor>(
      `/api/monitors/${id}`,
      { expected_version: version, ...fields },
      workspace.workspace_id,
      'PATCH',
    );
    if (monitor) monitor = { ...monitor, ...updated };
    await load();
  }
  onMount(() => {
    void load();
    return () => gate.cancel();
  });
</script>

<a class="back-link" href="/services">Voltar ao registro de serviços</a>
<Notice {error} onReload={error instanceof ApiError && error.status === 404 ? onCurrent : load} />
{#if loading && !monitor}<p class="loading-records" role="status">
    Carregando o registro do serviço…
  </p>{/if}
{#if monitor}
  {@const state = observationState(monitor)}
  <header class="page-header">
    <div>
      <h1>{monitor.name}</h1>
      <p>
        {monitor.target_kind === 'fixture'
          ? 'Alvo fictício, controlado nesta demonstração.'
          : monitor.target_url}
      </p>
    </div>
    <Status {...state} />
  </header>
  <a class="mobile-action-link" href="#next-observation">Verificar ou alterar cenário</a>
  <div class="work-layout">
    <div class="observations">
      <section class="latest-reading" aria-labelledby="last-title">
        <h2 id="last-title">Última resposta registrada</h2>
        {#if monitor.last_check}<p class="reading-result">
            <strong>{checkLabel(monitor.last_check)}</strong><span class="numeric"
              >{monitor.last_check.duration_ms} ms</span
            >
          </p>
          <p class="supporting">
            <time datetime={monitor.last_check.finished_at ?? monitor.last_check.started_at}
              >{formatDate(monitor.last_check.finished_at)}</time
            > · Brasília
          </p>
        {:else}<p class="unmeasured">Nenhuma resposta foi medida.</p>
          <p class="supporting">
            O estado começa desconhecido. A primeira verificação cria o registro.
          </p>{/if}
      </section>
      {#if monitor.active_incident}<a
          class="incident-link"
          href={`/incidents/${monitor.active_incident.id}`}
          ><span
            ><strong>Incidente ativo</strong><span
              >{monitor.active_incident.state === 'acknowledged'
                ? 'Investigação reconhecida'
                : 'Aguardando reconhecimento'} · confirmado em {formatDate(
                monitor.active_incident.confirmed_at,
              )}</span
            ></span
          ><span>Ver evidências</span></a
        >{/if}
      <SampleStrip
        checks={monitor.checks}
        {selected}
        onSelect={(value) => {
          selected = value;
        }}
      />
      {#if selectedCheck}<p class="selected-reading" role="status">
          Selecionada: <strong>{checkLabel(selectedCheck)}</strong> · {formatDate(
            selectedCheck.started_at,
          )}{#if selectedCheck.abandon_reason}
            · {selectedCheck.abandon_reason === 'LEASE_EXPIRED'
              ? 'prazo de execução encerrado'
              : 'serviço alterado antes do resultado'}{/if}
          {#if selectedEvidence}
            · <a href={`/incidents/${selectedEvidence.id}`}>{selectedEvidence.label}</a>
          {/if}
        </p>{/if}
      <section class="check-history">
        <h2>Verificações registradas</h2>
        <CheckTable
          checks={monitor.checks}
          {selected}
          onSelect={(value) => {
            selected = value;
          }}
        />{#if monitor.checks.length === monitor.history_limit}<p class="field-help">
            As {monitor.history_limit} verificações mais recentes. Todos os resultados permanecem armazenados.
          </p>{/if}
      </section>
      <section class="incident-history">
        <h2>Incidentes registrados</h2>
        {#if monitor.incidents.length === 0}<p class="supporting">
            Nenhum incidente foi confirmado neste serviço.
          </p>
        {:else}<ul class="incident-list">
            {#each monitor.incidents as incident (incident.id)}<li>
                <a href={`/incidents/${incident.id}`}
                  ><span
                    >{incident.state === 'resolved'
                      ? 'Recuperação confirmada'
                      : incident.state === 'acknowledged'
                        ? 'Investigação reconhecida'
                        : 'Incidente ativo'}</span
                  ><time datetime={incident.confirmed_at}>{formatDate(incident.confirmed_at)}</time
                  ></a
                >
              </li>{/each}
          </ul>{/if}
      </section>
    </div>
    <aside class="control-area">
      <MonitorControls {monitor} onVerify={check} onChange={change} onReload={load} />
    </aside>
  </div>
{/if}
