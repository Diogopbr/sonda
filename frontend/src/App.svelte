<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { api, ApiError } from './lib/api';
  import { formatDate } from './lib/status';
  import type { Capabilities, Workspace } from './lib/types';
  import Entry from './views/Entry.svelte';
  import Services from './views/Services.svelte';
  import Monitor from './views/Monitor.svelte';
  import Incident from './views/Incident.svelte';
  import Login from './views/Login.svelte';
  import Icon from './components/Icon.svelte';
  import Notice from './components/Notice.svelte';

  let workspace = $state<Workspace | null>(null);
  let capabilities = $state<Capabilities>({ demo_enabled: false, login_enabled: false });
  let pathname = $state(window.location.pathname);
  let loading = $state(true);
  let error = $state<unknown>(null);
  let resetError = $state<unknown>(null);
  let resetting = $state(false);
  let dialog: HTMLDialogElement | undefined = $state();
  let main: HTMLElement | undefined = $state();
  let resetInvoker: HTMLElement | null = null;
  const route = $derived(pathname.split('/').filter(Boolean));
  const protectedRoute = $derived(route[0] === 'services' || route[0] === 'incidents');

  async function navigate(path: string): Promise<void> {
    const target = new URL(path, window.location.origin);
    window.history.pushState({}, '', target.pathname + target.hash);
    pathname = target.pathname;
    await tick();
    if (target.hash) {
      const destination = document.getElementById(target.hash.slice(1));
      destination?.scrollIntoView();
      destination?.focus({ preventScroll: true });
    } else {
      window.scrollTo(0, 0);
      main?.focus({ preventScroll: true });
    }
  }
  function follow(event: MouseEvent): void {
    const target = event.target instanceof Element ? event.target.closest('a') : null;
    if (
      !(target instanceof HTMLAnchorElement) ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      target.target ||
      target.hasAttribute('download')
    )
      return;
    const url = new URL(target.href);
    if (url.origin !== window.location.origin) return;
    event.preventDefault();
    void navigate(url.pathname + url.hash);
  }
  async function currentAccess(): Promise<void> {
    try {
      workspace = await api.read<Workspace>('/api/auth');
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) workspace = null;
      else throw cause;
    }
  }
  async function bootstrap(): Promise<void> {
    loading = true;
    error = null;
    try {
      capabilities = await api.read<Capabilities>('/api/capabilities');
      await currentAccess();
    } catch (cause) {
      error = cause;
    } finally {
      loading = false;
    }
  }
  async function start(): Promise<void> {
    workspace = await api.write<Workspace>('/api/demo/start', {});
    await navigate('/services');
  }
  async function openCurrent(): Promise<void> {
    try {
      await currentAccess();
      dialog?.close();
      await navigate(workspace ? '/services' : '/');
      error = null;
    } catch (cause) {
      error = cause;
    }
  }
  async function logout(): Promise<void> {
    if (!workspace) return;
    const generation = workspace.workspace_id;
    try {
      await api.write('/api/auth/logout', {}, generation);
      workspace = null;
      await navigate('/');
    } catch (cause) {
      error = cause;
    }
  }
  async function openReset(): Promise<void> {
    resetError = null;
    resetInvoker = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    await tick();
    document.getElementById('cancel-reset')?.focus();
  }
  async function reset(): Promise<void> {
    if (!workspace) return;
    const generation = workspace.workspace_id;
    resetting = true;
    resetError = null;
    try {
      workspace = await api.write<Workspace>('/api/demo/reset', {}, generation);
      dialog?.close();
      await navigate('/services');
    } catch (cause) {
      resetError = cause;
    } finally {
      resetting = false;
    }
  }
  onMount(() => {
    void bootstrap();
  });
</script>

<svelte:window
  onclick={follow}
  onpopstate={() => {
    pathname = window.location.pathname;
  }}
/>
<a class="skip-link" href="#content">Ir para o conteúdo</a>
<header class="app-header">
  <div class="header-inner">
    <a class="brand" href="/" aria-label="Sonda, página inicial"
      ><svg width="25" height="28" viewBox="0 0 25 28" fill="none" aria-hidden="true"
        ><path d="M5 4v20M20 4v20M5 10h15M5 18h15" stroke="currentColor" stroke-width="2" /><circle
          cx="5"
          cy="10"
          r="3"
          fill="currentColor"
        /><circle cx="20" cy="18" r="3" fill="currentColor" /></svg
      ><span>Sonda</span></a
    >
    <nav class="primary-navigation" aria-label="Navegação principal">
      {#if workspace}<a href="/services" aria-current={protectedRoute ? 'page' : undefined}
          >Serviços</a
        >{/if}<a href="/#como-funciona">Como funciona</a>
    </nav>
    <div class="session-actions">
      {#if workspace}<span class="session-kind"
          >{workspace.kind === 'demo' ? 'Demonstração' : 'Instalação administrada'}</span
        >
        {#if workspace.kind === 'demo'}<button class="header-button" onclick={openReset}
            ><Icon name="refresh" size={18} />Reiniciar demo</button
          >{/if}
        <button class="header-button" onclick={logout}>Sair</button>
      {:else if capabilities.login_enabled}<a class="header-button" href="/login"
          >Acesso de operador</a
        >{/if}
    </div>
  </div>
</header>

<main id="content" class="content" tabindex="-1" bind:this={main}>
  <Notice {error} onReload={bootstrap} />
  {#if loading}<p class="loading-records" role="status">Preparando o registro de serviços…</p>
  {:else if route[0] === 'login'}<Login
      enabled={capabilities.login_enabled}
      onLogin={(value) => {
        workspace = value;
        void navigate('/services');
      }}
    />
  {:else if !workspace || route.length === 0}<Entry
      {workspace}
      {capabilities}
      onStart={start}
      onNavigate={(path) => {
        void navigate(path);
      }}
    />
  {:else}
    {#key `${workspace.workspace_id}:${pathname}`}
      {#if route[0] === 'services' && route.length === 1}<Services
          {workspace}
          onCurrent={openCurrent}
        />
      {:else if route[0] === 'services' && route.length === 2}<Monitor
          {workspace}
          id={route[1]}
          onCurrent={openCurrent}
        />
      {:else if route[0] === 'incidents' && route.length === 2}<Incident
          {workspace}
          id={route[1]}
          onCurrent={openCurrent}
        />
      {:else}<div class="empty-state">
          <h1>Registro não encontrado</h1>
          <a href="/services" class="button secondary">Voltar aos serviços</a>
        </div>{/if}
    {/key}
  {/if}
  {#if workspace?.kind === 'demo' && protectedRoute}<footer class="workspace-footer">
      <span>Ambiente temporário · expira em {formatDate(workspace.expires_at)} · Brasília</span
      ><button class="text-button" onclick={openCurrent}>Abrir ambiente atual</button>
    </footer>{/if}
</main>
<footer class="app-footer">
  <div>
    <span>Sonda · Observações HTTP e incidentes</span><a
      href="https://github.com/Diogopbr/sonda"
      target="_blank"
      rel="noreferrer">Ver código <Icon name="external" size={16} /></a
    >
  </div>
</footer>

<dialog
  class="reset-dialog"
  bind:this={dialog}
  onclose={() => {
    resetInvoker?.focus();
  }}
>
  <div class="dialog-heading">
    <h2>Reiniciar demonstração?</h2>
    <button
      class="icon-button"
      aria-label="Fechar diálogo"
      onclick={() => dialog?.close()}
      disabled={resetting}><Icon name="close" /></button
    >
  </div>
  <p>
    Os registros do ambiente atual deixam de ficar acessíveis. Você receberá quatro serviços sem
    observações. Os limites de uso continuam vinculados ao visitante.
  </p>
  <p>Se houver um comentário não enviado, copie-o antes de continuar.</p>
  <Notice error={resetError} />
  <div class="dialog-actions">
    <button
      id="cancel-reset"
      class="button secondary"
      onclick={() => dialog?.close()}
      disabled={resetting}>Manter ambiente</button
    ><button class="button primary" onclick={reset} disabled={resetting}
      >{resetting ? 'Reiniciando…' : 'Reiniciar ambiente'}</button
    >
  </div>
</dialog>
