<script lang="ts">
  import { checkLabel, checkTone, formatDate } from '../lib/status';
  import type { Check } from '../lib/types';
  let {
    checks,
    selected,
    onSelect,
  }: { checks: Check[]; selected: string | null; onSelect: (id: string) => void } = $props();
  const chronological = $derived([...checks].reverse());
</script>

{#if checks.length}
  <div class="sample-heading">
    <h2>Sequência de observações</h2>
    <p>Selecione uma resposta para ler seu registro.</p>
  </div>
  <ol class="sample-strip" aria-label="Verificações em ordem cronológica">
    {#each chronological as check (check.id)}
      <li>
        <button
          class={`sample ${checkTone(check)}`}
          class:sample-selected={selected === check.id}
          aria-pressed={selected === check.id}
          onclick={() => onSelect(check.id)}
          aria-label={`${checkLabel(check)}, ${formatDate(check.started_at)}`}
        >
          <span class="sample-mark" aria-hidden="true"></span><span class="sample-value"
            >{check.status_code ?? (check.state === 'abandoned' ? '—' : '…')}</span
          >
        </button>
      </li>
    {/each}
  </ol>
{/if}
