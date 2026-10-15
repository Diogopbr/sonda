<script lang="ts">
  import { tick } from 'svelte';
  import { ApiError, errorMessage } from '../lib/api';
  import { formatDate } from '../lib/status';
  import type { IncidentSummary } from '../lib/types';

  let {
    incident,
    onAcknowledge,
    onReload,
  }: {
    incident: IncidentSummary;
    onAcknowledge: (comment: string, version: number) => Promise<void>;
    onReload: () => Promise<void>;
  } = $props();
  let draft = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);
  let conflict = $state(false);
  let expired = $state(false);
  let alert: HTMLDivElement | undefined = $state();

  async function fail(cause: unknown): Promise<void> {
    error = errorMessage(cause);
    conflict = conflict || (cause instanceof ApiError && cause.status === 409);
    expired = expired || (cause instanceof ApiError && cause.status === 404);
    await tick();
    alert?.focus();
  }
  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (busy || conflict || expired || incident.state !== 'open') return;
    const comment = draft;
    const version = incident.version;
    busy = true;
    error = null;
    try {
      await onAcknowledge(comment, version);
      draft = '';
      conflict = false;
    } catch (cause) {
      await fail(cause);
    } finally {
      busy = false;
    }
  }
  async function reload(): Promise<void> {
    busy = true;
    try {
      await onReload();
      error = null;
      conflict = false;
    } catch (cause) {
      await fail(cause);
    } finally {
      busy = false;
    }
  }
</script>

<section class="acknowledgement" aria-labelledby="ack-title">
  <h2 id="ack-title">Investigação</h2>
  {#if incident.acknowledgement}
    <p class="ack-author">
      Reconhecido por {incident.acknowledged_by?.name ?? 'Operador'} · {formatDate(
        incident.acknowledged_at,
      )}
    </p>
    <p class="recorded-comment">{incident.acknowledgement}</p>
  {:else}
    <p class="supporting">
      Registre o que está sendo investigado. A recuperação depende das próximas respostas do
      serviço.
    </p>
  {/if}
  {#if error}
    <div class="notice error" role="alert" tabindex="-1" bind:this={alert}>
      <p>{error}</p>
      <p>Seu comentário continua aqui.</p>
      {#if conflict}<button class="button secondary" type="button" onclick={reload} disabled={busy}
          >Revisar dados atuais</button
        >{/if}
      {#if expired}<p>
          Este ambiente foi encerrado. Copie seu rascunho antes de abrir outro ambiente.
        </p>{/if}
    </div>
  {/if}
  {#if incident.state === 'open' && !expired}
    <form onsubmit={submit}>
      <label for="ack-comment">Comentário de investigação</label>
      <textarea
        id="ack-comment"
        bind:value={draft}
        rows="4"
        minlength="3"
        maxlength="500"
        required
        disabled={busy}
        aria-describedby="ack-help"
        placeholder="O que você está verificando?"></textarea>
      <p id="ack-help" class="field-help">
        3 a 500 caracteres. O reconhecimento fica registrado e mantém o incidente ativo.
      </p>
      <button class="button primary" type="submit" disabled={busy || conflict}
        >{busy ? 'Registrando…' : 'Reconhecer incidente'}</button
      >
    </form>
  {:else if draft}
    <label for="unsent-draft">Rascunho não enviado</label>
    <textarea id="unsent-draft" value={draft} rows="4" readonly></textarea>
    <p class="field-help">
      O registro atual foi preservado. Você pode selecionar e copiar este texto.
    </p>
  {:else if incident.state === 'resolved'}
    <p class="supporting">
      Incidente resolvido. As evidências e o comentário permanecem disponíveis para leitura.
    </p>
  {/if}
</section>
