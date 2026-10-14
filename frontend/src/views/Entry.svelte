<script lang="ts">
  import Icon from '../components/Icon.svelte';
  import Notice from '../components/Notice.svelte';
  import type { Capabilities, Workspace } from '../lib/types';
  let {
    workspace,
    capabilities,
    onStart,
    onNavigate,
  }: {
    workspace: Workspace | null;
    capabilities: Capabilities;
    onStart: () => Promise<void>;
    onNavigate: (path: string) => void;
  } = $props();
  let busy = $state(false);
  let error = $state<unknown>(null);
  async function start(): Promise<void> {
    busy = true;
    error = null;
    try {
      await onStart();
    } catch (cause) {
      error = cause;
    } finally {
      busy = false;
    }
  }
</script>

<div class="entry-layout">
  <section class="entry-main">
    <h1>Acompanhe respostas HTTP e o histórico de cada incidente.</h1>
    <p class="entry-description">
      O Sonda acompanha respostas HTTP e registra o que confirmou uma falha ou uma recuperação. Cada
      estado pode ser conferido nas observações que o sustentam.
    </p>
    <div class="entry-actions">
      {#if workspace}<button class="button primary" onclick={() => onNavigate('/services')}
          >Abrir meu ambiente <Icon name="arrow" /></button
        >
      {:else if capabilities.demo_enabled}<button
          class="button primary"
          onclick={start}
          disabled={busy}
          >{busy ? 'Preparando ambiente…' : 'Iniciar demonstração'}<Icon name="arrow" /></button
        >{/if}
      {#if capabilities.login_enabled}<a class="button secondary" href="/login"
          >Acesso de operador</a
        >{/if}
    </div>
    <Notice {error} />
    <p class="entry-caption">
      Quatro serviços fictícios. Requisições reais. Ambiente separado por visitante, com duração de
      24 horas.
    </p>
  </section>
  <section class="entry-guide" aria-labelledby="guide-title">
    <h2 id="guide-title">Percorra um incidente</h2>
    <ol class="workflow-guide">
      <li>
        <strong>Observe a primeira resposta</strong>
        <p>Abra um serviço e faça uma verificação. O registro começa sem medições.</p>
      </li>
      <li>
        <strong>Confirme uma falha</strong>
        <p>Prepare o cenário HTTP 503 e verifique duas vezes. A sequência abre um incidente.</p>
      </li>
      <li>
        <strong>Registre a investigação</strong>
        <p>Reconheça o incidente com um comentário. Reconhecimento mantém a falha ativa.</p>
      </li>
      <li>
        <strong>Confira a recuperação</strong>
        <p>
          Restaure o cenário HTTP 200. Duas respostas saudáveis resolvem o incidente e preservam sua
          evidência.
        </p>
      </li>
    </ol>
  </section>
</div>
<section class="explanation" id="como-funciona">
  <h2>O que está sendo medido</h2>
  <p>
    Uma verificação registra status HTTP, duração e horário. Sucesso exige resposta 2xx. Falhas e
    recuperações precisam de duas observações consecutivas para mudar o estado confirmado.
  </p>
  <p>
    A demonstração permite preparar a resposta dos alvos fictícios. Alterar esse cenário prepara a
    próxima chamada; a observação só aparece quando você verifica o serviço. Não há cálculo de
    disponibilidade de 24 horas a partir dessas amostras manuais.
  </p>
</section>
