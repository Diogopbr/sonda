<script lang="ts">
  import { tick } from 'svelte';
  import { errorMessage, ApiError } from '../lib/api';
  import type { Check, Monitor } from '../lib/types';
  import Icon from './Icon.svelte';
  let {
    monitor,
    onVerify,
    onChange,
    onReload,
  }: {
    monitor: Monitor;
    onVerify: () => Promise<Check>;
    onChange: (
      fields: { enabled?: boolean; fixture_mode?: 'available' | 'unavailable' },
      version: number,
    ) => Promise<void>;
    onReload: () => Promise<void>;
  } = $props();
  let scenario = $state<'available' | 'unavailable'>('available');
  let busy = $state(false);
  let error = $state<unknown>(null);
  let message = $state('');
  let expired = $state(false);
  let conflict = $state(false);
  let alert: HTMLDivElement | undefined = $state();
  $effect(() => {
    if (!busy && !error) scenario = monitor.fixture_mode ?? 'available';
  });
  async function operate(action: () => Promise<void | Check>): Promise<void> {
    busy = true;
    error = null;
    message = '';
    conflict = false;
    try {
      const result = await action();
      if (result)
        message =
          result.state === 'pending'
            ? 'A verificação está em andamento. Consulte novamente para obter o resultado.'
            : result.state === 'abandoned'
              ? 'Esta tentativa foi descartada. Execute outra verificação para obter um resultado.'
              : 'Verificação registrada.';
    } catch (cause) {
      error = cause;
      expired = cause instanceof ApiError && cause.status === 404;
      conflict = cause instanceof ApiError && cause.status === 409;
      await tick();
      alert?.focus();
    } finally {
      busy = false;
    }
  }
  async function reload(): Promise<void> {
    try {
      await onReload();
      error = null;
      conflict = false;
    } catch (cause) {
      error = cause;
      await tick();
      alert?.focus();
    }
  }
</script>

<section
  id="next-observation"
  class="monitor-controls"
  aria-labelledby="actions-title"
  tabindex="-1"
>
  <h2 id="actions-title">Próxima observação</h2>
  <p class="supporting">
    Registre a resposta atual. Duas falhas consecutivas confirmam um incidente; duas respostas
    saudáveis confirmam a recuperação.
  </p>
  <button
    class="button primary verify-button"
    onclick={() => operate(onVerify)}
    disabled={busy || !monitor.enabled || expired}
  >
    <Icon name="play" />{busy ? 'Executando…' : 'Verificar agora'}
  </button>
  <p class="field-help">
    Prazo de até 5 segundos por chamada. {monitor.target_kind === 'fixture'
      ? 'A demo usa verificações manuais.'
      : `Intervalo administrado: ${monitor.interval_seconds} segundos.`}
  </p>
  {#if message}<p class="action-feedback" role="status">{message}</p>{/if}
  {#if error}
    <div class="notice error" role="alert" tabindex="-1" bind:this={alert}>
      <p>{errorMessage(error)}</p>
      {#if error instanceof ApiError && error.retryAfter}<p>
          Aguarde {error.retryAfter} segundos.
        </p>{/if}
      {#if conflict}<button class="button secondary" onclick={reload}>Revisar dados atuais</button
        >{/if}
      {#if expired}<p>Este ambiente foi encerrado. Abra o ambiente atual para continuar.</p>{/if}
    </div>
  {/if}
  {#if monitor.target_kind === 'fixture'}
    <div class="scenario-form">
      <label for="scenario">Cenário do alvo fictício</label>
      <select id="scenario" bind:value={scenario} disabled={busy || expired}>
        <option value="available">Disponível · HTTP 200</option><option value="unavailable"
          >Indisponível · HTTP 503</option
        >
      </select>
      <button
        class="button secondary"
        onclick={() => operate(() => onChange({ fixture_mode: scenario }, monitor.version))}
        disabled={busy || expired || scenario === monitor.fixture_mode || conflict}
        >Aplicar cenário</button
      >
      <p class="field-help">
        Alterar o cenário prepara a próxima resposta. O estado observado muda após verificar.
      </p>
    </div>
  {/if}
  <button
    class="button quiet pause-button"
    onclick={() => operate(() => onChange({ enabled: !monitor.enabled }, monitor.version))}
    disabled={busy || expired || conflict}
    ><Icon name={monitor.enabled ? 'pause' : 'play'} />{monitor.enabled
      ? 'Pausar monitor'
      : 'Retomar monitor'}</button
  >
</section>
