<script lang="ts">
  import { checkLabel, checkTone, formatDate } from '../lib/status';
  import type { Check } from '../lib/types';
  import Status from './Status.svelte';
  let {
    checks,
    selected = null,
    onSelect,
  }: { checks: Check[]; selected?: string | null; onSelect?: (id: string) => void } = $props();
</script>

{#if checks.length === 0}
  <div class="empty-state">
    <h3>A primeira resposta ainda está por vir</h3>
    <p>Use “Verificar agora” para registrar uma observação deste serviço.</p>
  </div>
{:else}
  <table class="data-table check-table">
    <caption class="sr-only"
      >Verificações do serviço, mais recentes primeiro. Horários de Brasília.</caption
    >
    <thead
      ><tr><th>Momento · Brasília</th><th>Resposta</th><th>Duração</th><th>Execução</th></tr></thead
    >
    <tbody>
      {#each checks as check (check.id)}
        <tr class:selected-row={selected === check.id}>
          <td data-label="Momento · Brasília">
            {#if onSelect}<button class="text-button numeric" onclick={() => onSelect?.(check.id)}
                >{formatDate(check.started_at)}</button
              >
            {:else}<time datetime={check.started_at}>{formatDate(check.started_at)}</time>{/if}
          </td>
          <td data-label="Resposta"><Status label={checkLabel(check)} tone={checkTone(check)} /></td
          >
          <td data-label="Duração" class="numeric"
            >{check.duration_ms !== null ? `${check.duration_ms} ms` : '—'}</td
          >
          <td data-label="Execução"
            >{check.origin === 'manual' ? 'Manual' : 'Agendada'}{#if check.state === 'abandoned'}
              · interrompida{/if}</td
          >
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
