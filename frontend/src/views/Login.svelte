<script lang="ts">
  import { api } from '../lib/api';
  import type { Workspace } from '../lib/types';
  import Notice from '../components/Notice.svelte';
  let { enabled, onLogin }: { enabled: boolean; onLogin: (workspace: Workspace) => void } =
    $props();
  let email = $state('');
  let password = $state('');
  let busy = $state(false);
  let error = $state<unknown>(null);
  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      onLogin(await api.write<Workspace>('/api/auth/login', { email, password }));
      password = '';
    } catch (cause) {
      error = cause;
    } finally {
      busy = false;
    }
  }
</script>

<section class="login-area">
  <h1>Acesso de operador</h1>
  {#if enabled}<p>
      Entre na instalação administrada. Os alvos são configurados previamente pelo operador.
    </p>
    <Notice {error} />
    <form onsubmit={submit}>
      <label for="email">E-mail</label><input
        id="email"
        type="email"
        bind:value={email}
        autocomplete="username"
        required
        maxlength="254"
        disabled={busy}
      />
      <label for="password">Senha</label><input
        id="password"
        type="password"
        bind:value={password}
        autocomplete="current-password"
        required
        maxlength="128"
        disabled={busy}
      />
      <button class="button primary" type="submit" disabled={busy}
        >{busy ? 'Entrando…' : 'Entrar'}</button
      >
    </form>
  {:else}<p>A entrada de operadores está desabilitada neste ambiente.</p>
    <a class="button secondary" href="/">Voltar à demonstração</a>{/if}
</section>
