<script lang="ts">
  import { tick } from 'svelte';
  import { errorMessage, ApiError } from '../lib/api';
  let { error, onReload }: { error: unknown; onReload?: () => void | Promise<void> } = $props();
  let node: HTMLDivElement | undefined = $state();
  $effect(() => {
    if (error) void tick().then(() => node?.focus());
  });
</script>

{#if error}
  <div class="notice error" role="alert" tabindex="-1" bind:this={node}>
    <p>{errorMessage(error)}</p>
    {#if error instanceof ApiError && error.retryAfter}<p>
        Aguarde {error.retryAfter} segundos antes de repetir.
      </p>{/if}
    {#if onReload}<button class="button secondary" onclick={onReload}>Revisar dados atuais</button
      >{/if}
  </div>
{/if}
