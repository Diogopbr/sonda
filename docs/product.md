# Sonda — monitoramento HTTP e incidentes

## Objetivo e recorte

Construir o quarto produto de portfólio, independente dos demais, com Python,
FastAPI, TypeScript/Svelte e PostgreSQL. O percurso principal verifica um serviço,
provoca duas falhas, abre um incidente, registra reconhecimento e observa duas
verificações bem-sucedidas encerrarem o incidente. Resultados e eventos são reais,
persistentes e explicáveis; o cenário da demonstração é fictício.

Uma página de métricas sem execução, um agregador de APIs externas e uma plataforma
com filas/notificações foram considerados. A escolha é um monólito pequeno com
executor HTTP e leases no banco: demonstra rede, concorrência e regras de estado
sem adicionar serviços de infraestrutura que o fluxo não exige.

## Ambientes e acesso

Cada visitante recebe identidade aleatória, sessão em PostgreSQL e ambiente demo
com duração fixa de24h. Recuperar o ambiente não prolonga a validade. Reset revoga
a geração anterior, invalida sessões e cria outra; a identidade e os limites por
visitante permanecem. Recursos de outro ambiente retornam404.

Cookie de sessão assinado, aleatório, HttpOnly/Secure/SameSite=Lax em produção.
Escritas exigem origem exata e token CSRF. O cliente captura a geração antes de
obter CSRF e não envia um rascunho antigo à geração nova após reset em outra aba.
No reset, o diálogo explica perda dos dados, contém foco e devolve foco ao abrir/fechar.

Uma instalação administrada é criada por comando explícito, com credenciais por
stdin. Login usa scrypt salgado e sessões regeneradas. Não há senha default,
cadastro público ou configuração de alvos por visitantes. Login pode permanecer
desabilitado na demonstração pública.

Limites demo: quatro monitores fixos,60 tentativas aceitas por geração incluindo
tentativas abandonadas,6 verificações/minuto/visitante,10 inícios/minuto/IP,
reset1/minuto/visitante e10/hora/IP. Login10/minuto/IP. Limites usam relógio e
contadores atômicos no PostgreSQL, com429 e Retry-After. Comandos repetidos não
consomem outra tentativa. Coleta remove gerações expiradas/revogadas em lotes
limitados e não remove ambiente normal ou uma geração com lock de operação ativo.

## Monitores e alvos

Campos: nome, alvo autorizado, intervalo de execução, habilitado, estado observado,
última verificação, contadores consecutivos de falha/sucesso e versão.
Intervalo mínimo60s; timeout fixo5s nesta entrega; sucesso exige status HTTP2xx.
Latência mede o tempo até os headers, em milissegundos, e não decide incidentes.
Monitores novos são desconhecidos até a primeira verificação concluída.

A demo contém Portal editorial, API de pedidos, Área de downloads e Página de
suporte. Os alvos são endpoints HTTPS do próprio Sonda, com estado controlado
por geração/monitor: disponível200 ou indisponível503. A UI identifica-os como
fictícios e oferece alterar o cenário e verificar agora. Não são respostas
mockadas no executor: ele realiza a chamada HTTP e persiste status/latência.
Os endpoints de alvo exigem um segredo interno próprio, não devolvem dados de
ambiente e não são uma API administrativa. O token não aparece em URLs ou logs.

Na instalação administrada, alvos são provisionados por CLI e precisam de hostname
explicitamente permitido na configuração, HTTPS e porta443. URLs com credenciais,
fragmento, controles, IP literal ou query são rejeitadas. Não há wildcard de host,
proxy de ambiente, redirecionamento seguido ou headers de autenticação definidos
pelo usuário. O segredo de fixture só é enviado ao alvo interno exato configurado.

## Proteção do executor de rede

Resolver DNS antes da conexão e rejeitar todo o conjunto se algum endereço não
for global: loopback, privado, link-local, multicast, reservado e formas IPv4
mapeadas em IPv6 não são destinos permitidos. Conectar usando os endereços já
validados, preservando hostname para Host/SNI e verificação TLS; não resolver
novamente no transporte. O resolver customizado de aiohttp fornece esse vínculo.
Redirecionamentos são resultados de falha, sem segunda chamada. Timeout cobre
DNS/conexão/headers; não carregar corpo completo nem salvar corpo ou headers.

Desenvolvimento local permite somente o alvo interno exato da APP_URL local para
as fixtures. Essa exceção é impossível com NODE_ENV equivalente de produção;
alvos normais continuam exigindo HTTPS e endereços públicos. Testes do transporte
local são distinguidos da prova de DNS/TLS no runtime hospedado.

Erros persistidos usam códigos estáveis como DNS_REJECTED, CONNECT_ERROR,
TLS_ERROR, TIMEOUT, REDIRECT_NOT_ALLOWED e HTTP_STATUS. Nunca incluir segredo,
stack, endereço privado ou resposta remota nos erros públicos.

## Execução, idempotência e concorrência

Uma verificação tem id, chave idempotente do cliente, geração, monitor, origem
manual/runner, lease aleatório, horário de claim e estado pending/finished/abandoned.
A chave é única no ambiente e ligada ao monitor; reutilização em outro monitor
retorna409. Um replay terminado devolve o resultado anterior sem chamada de rede.
Um replay em andamento retorna o mesmo id e estado, permitindo consultar o resultado.

Claim bloqueia ambiente FOR SHARE e monitor FOR UPDATE, valida validade/pausa,
limites e lease, grava tentativa e lease de30s e conclui a transação. Em demos,
um advisory lock por geração serializa somente a quota de60 tentativas
entre os quatro monitores. A prova de disputa do lease usa ambiente normal para
observar o lock do monitor, separadamente da proteção da quota.
Outro claim enquanto o lease vigora retorna409 CHECK_RUNNING sem gastar quota. Não manter
transação/conexão de banco aberta durante a chamada HTTP.

Finish obtém os mesmos locks, verifica geração, lease e relógio do PostgreSQL,
grava resultado, estado do monitor, incidente e eventos atomicamente. Token
substituído, lease vencido ou monitor alterado não admite resultado tardio:
410 CHECK_SUPERSEDED, sem mudar incidente ou contadores. Geração antiga retorna404.
O próximo claim pode abandonar uma tentativa cujo lease expirou; abandono não
é uma falha de serviço. Pausa ou mudança de cenário invalida tentativa em andamento.
Uma versão antiga para pausa/cenário retorna409 VERSION_CONFLICT com current.
Mutações de cenário, pausa e reconhecimento têm limite30/minuto/visitante.

Runner `run-due --once` busca monitores normais vencidos com FOR UPDATE SKIP LOCKED,
usa o mesmo claim/finish e tem lote máximo10. Não verifica demos em background.
Um operador pode agendar o comando no ambiente administrado; não haverá loop,
thread ou tarefa ASGI que prometa continuar depois da resposta serverless.
A demo publicada oferece somente verificações manuais e declara esse limite.

## Estados e incidentes

Primeiro resultado saudável muda desconhecido para saudável. Uma falha deixa o
registro de último resultado visível e mantém a contagem; a segunda falha
consecutiva muda o estado para indisponível e abre exatamente um incidente.
O incidente registra a primeira falha da sequência e o instante de confirmação.
Falhas seguintes acrescentam verificações, sem novos incidentes duplicados.

Um sucesso interrompe a sequência de falhas. Duas verificações saudáveis
consecutivas recuperam um monitor indisponível e resolvem o incidente ativo.
Um sucesso seguido de outra falha mantém o incidente aberto. Não confundir
reconhecimento com recuperação: reconhecer exige comentário3..500 caracteres,
ator e versão atual, e não fecha o incidente. Depois de resolvido, o incidente
é somente leitura. Não há encerramento manual sem evidência de recuperação.

Índice parcial único impede dois incidentes não resolvidos por monitor/ambiente.
Resultados e eventos são imutáveis para a role de runtime, exceto cascade ao
remover uma geração inteira. FK composta mantém monitor/ator/incidente no mesmo
ambiente. Uma tentativa pending pode receber exatamente uma transição final;
um trigger impede reescrever tentativas finished/abandoned e eventos anteriores.
Eventos incluem antes/depois quando pertinente e datas UTC; UI usa
Português/Brasília com zona explícita. Não calcular disponibilidade24h a partir
de amostras manuais ou preencher um gráfico com dados que não foram medidos.

## Interface

Entrada com um exemplo de percurso e acesso à demo. Registro de serviços com
último status, idade da medição, latência, sequência e ação explícita. Detalhe
com configurações, cenário demo, verificações em ordem e incidente ativo.
Detalhe de incidente com evidências que o abriram, comentário de reconhecimento
e verificação que o resolveu. Distinguir desconhecido, saudável, sequência de
falhas, indisponível, recuperação em andamento e pausado por texto.

A interface usa registros alinhados e uma sequência de observações reais. No celular, linhas viram registros com rótulos e há acesso direto aos controles. Formulários preservam comentários em409/404/rede, erros recebem foco e resposta
fora de ordem não substitui dados de monitor ou geração diferente.

## Organização e implantação

Monólito modular: configuração/migrations; acesso/ambientes; alvos/HTTP; claims/
resultados; incidentes; contratos HTTP. SQL explícito via psycopg3, validação
Pydantic/FastAPI e frontend Svelte/TypeScript. Nenhuma migration ou usuário
criado no startup; scripts administrativos explícitos e segredos fora do Git.

Banco PostgreSQL17 próprio, role limitada e banco de testes separado. Preparar
Vercel/FastAPI com frontend gerado e comprovar o comportamento real antes de
declarar deploy. Não contratar serviço pago nem exigir cron frequente no plano
Free. Credenciais administrativas usadas somente no provisionamento e migrations.

## Verificação e aceite

1. Percurso real: iniciar, verificar saudável, provocar duas503, abrir incidente,
   reconhecer com comentário, restaurar duas200 e observar resolução persistente.
2. DNS privado/misto/mapeado rejeitado, redirects não seguidos, timeout/TLS e
   pinagem dos endereços testados; nenhuma requisição ocorre para destino rejeitado.
3. Dois processos PostgreSQL disputam claim, com bloqueio observado; um lease
   vence. Controle negativo sem proteção admite dois claims, distinguindo a prova.
4. Expiração/substituição/pausa/reset durante uma chamada rejeita resultado tardio;
   falha injetada no evento reverte resultado, estado e incidente.
5. Sequências de sucesso/falha, idempotência, quorum2/2, índice de incidente único,
   versões de reconhecimento, quota e imutabilidade são testados no banco real.
6. Visitantes distintos, CSRF/origem/cookie, geração antiga, TTL e limites; runner
   não toca demos; coleta preserva normal/locks. Sem skips por banco ausente.
7. Browser desktop/mobile/teclado, estados vazios/erro/carregamento, comentários
   preservados e axe. Capturas reais e revisão independente, em rodadas limitadas.
8. CI, build e runtime hospedado; chamadas HTTPS reais às fixtures, arquivos
   privados404, TLS/permissões do banco e sessão/dados após redeploy. GitHub público
   após revisão.

## Limites e decisões em aberto

Não há notificações externas, websockets, tracing distribuído, agentes em máquinas,
scripts de usuário, cobrança, TLS privado ou monitoramento contínuo na demo.
Versões exatas estão nos lockfiles; empacotamento e assets são descritos em
[implantação](deployment.md). Não há resultados comerciais ou usuários a alegar.

Configuração: SONDA_ENV=development/test/production, APP_URL, DATABASE_URL,
DB_TLS, SESSION_SECRET e PROBE_SECRET. Produção exige HTTPS, TLS verificado,
segredos independentes de pelo menos32 caracteres e flags booleanas explícitas.
SONDA_DEMO_ENABLED e SONDA_LOGIN_ENABLED controlam os acessos; TRUST_VERCEL_INGRESS
só permite tratar headers da plataforma quando seu marcador de runtime também
está presente. Não aceitar segredo ou certificado inseguros como fallback.

Fontes consultadas: [FastAPI na Vercel](https://vercel.com/docs/frameworks/backend/fastapi),
[cliente/resolver aiohttp](https://docs.aiohttp.org/en/stable/client_advanced.html),
[psycopg assíncrono](https://www.psycopg.org/psycopg3/docs/advanced/async.html).
