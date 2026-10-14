<script lang="ts">
  import { onMount } from 'svelte';
  import { api, ApiError } from '../lib/api';
  import { QueryGate } from '../lib/query';
  import { observationState, resultAge, checkLabel, formatDate } from '../lib/status';
  import type { Monitor, Workspace } from '../lib/types';
  import Status from '../components/Status.svelte';
  import Icon from '../components/Icon.svelte';
  import Notice from '../components/Notice.svelte';
  let { workspace, onCurrent }: { workspace: Workspace; onCurrent: () => Promise<void> } = $props();
  let monitors = $state<Monitor[]>([]);
  let loading = $state(true);
  let error = $state<unknown>(null);
  let filter = $state<'all' | 'unknown' | 'failures' | 'paused'>('all');
  const gate = new QueryGate();
  const visible = $derived(
    monitors.filter(
      (monitor) =>
        filter === 'all' ||
        (filter === 'unknown' && monitor.last_check === null && monitor.enabled) ||
        (filter === 'failures' &&
          (monitor.failure_streak > 0 || monitor.observed_state === 'unavailable')) ||
        (filter === 'paused' && !monitor.enabled),
    ),
  );
  const filters = [
    { id: 'all', label: 'Todos' },
    { id: 'unknown', label: 'Sem medição' },
    { id: 'failures', label: 'Com falhas' },
    { id: 'paused', label: 'Pausados' },
  ] as const;
  async function load(): Promise<void> {
    loading = true;
    try {
      const next = await gate.run(workspace.workspace_id, (signal) =>
        api.read<{ monitors: Monitor[] }>('/api/monitors', workspace.workspace_id, signal),
      );
      if (next) {
        monitors = next.monitors;
        error = null;
        loading = false;
      }
    } catch (cause) {
      error = cause;
      loading = false;
    }
  }
  onMount(() => {
    void load();
    return () => gate.cancel();
  });
</script>

<header class="page-header">
  <div>
    <h1>Registro de serviços</h1>
    <p>O último resultado e a sequência que explica o estado atual.</p>
  </div>
  <button class="button secondary" onclick={load} disabled={loading}
    ><Icon name="refresh" />{loading ? 'Atualizando…' : 'Atualizar registros'}</button
  >
</header>
{#if workspace.kind === 'demo'}<p class="environment-note">
    Serviços fictícios desta demonstração · verificações manuais · até 60 tentativas aceitas por
    ambiente.
  </p>{/if}
<Notice {error} onReload={error instanceof ApiError && error.status === 404 ? onCurrent : load} />
<div class="registry-toolbar">
  <div class="filters" role="group" aria-label="Filtrar serviços">
    {#each filters as option}<button
        class="filter-button"
        aria-pressed={filter === option.id}
        onclick={() => {
          filter = option.id;
        }}>{option.label}</button
      >{/each}
  </div>
  <span class="record-count">{visible.length} {visible.length === 1 ? 'serviço' : 'serviços'}</span>
</div>
<section class="registry" aria-label="Serviços registrados" aria-busy={loading}>
  {#if loading && monitors.length === 0}<div class="loading-records">
      <p role="status">Carregando os serviços do seu ambiente…</p>
      <div class="loading-line" aria-hidden="true"></div>
      <div class="loading-line" aria-hidden="true"></div>
    </div>
  {:else if visible.length === 0}<div class="empty-state">
      <h2>Nenhum serviço neste filtro</h2>
      <p>Escolha “Todos” para voltar ao registro completo.</p>
      <button
        class="button secondary"
        onclick={() => {
          filter = 'all';
        }}>Mostrar todos</button
      >
    </div>
  {:else}<table class="data-table service-table">
      <caption class="sr-only">Serviços e seu último resultado medido.</caption>
      <thead
        ><tr
          ><th>Serviço</th><th>Estado observado</th><th>Última resposta</th><th>Tempo</th><th
            ><span class="sr-only">Abrir serviço</span></th
          ></tr
        ></thead
      >
      <tbody
        >{#each visible as monitor (monitor.id)}
          {@const state = observationState(monitor)}
          <tr
            ><td data-label="Serviço"
              ><a class="service-name" href={`/services/${monitor.id}`}>{monitor.name}</a><span
                class="service-type"
                >{monitor.target_kind === 'fixture' ? 'Alvo fictício' : 'Alvo autorizado'}</span
              ></td
            >
            <td data-label="Estado observado"><Status {...state} /></td>
            <td data-label="Última resposta"
              ><span class="numeric"
                >{monitor.last_check ? checkLabel(monitor.last_check) : '—'}</span
              ><span
                class="measurement-age"
                title={formatDate(monitor.last_check?.finished_at ?? null)}
                >{resultAge(monitor.last_check?.finished_at ?? null)}</span
              ></td
            >
            <td data-label="Tempo" class="numeric"
              >{monitor.last_check?.duration_ms !== null && monitor.last_check
                ? `${monitor.last_check.duration_ms} ms`
                : '—'}</td
            >
            <td class="row-action"
              ><a
                class="open-record"
                href={`/services/${monitor.id}`}
                aria-label={`Abrir registro de ${monitor.name}`}
                >Abrir <Icon name="arrow" size={18} /></a
              ></td
            >
          </tr>
        {/each}</tbody
      >
    </table>{/if}
</section>
<p class="registry-footnote">
  Uma única falha fica registrada. A confirmação de indisponibilidade exige duas falhas
  consecutivas.
</p>
