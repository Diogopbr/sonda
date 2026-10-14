# HTTP do Sonda

Este contrato registra as rotas implementadas. A demonstração usa alvos fictícios
controlados pelo Sonda e realiza chamadas HTTP reais.

## Sessões e comandos

`sonda_session` contém um identificador aleatório assinado; o banco armazena seu
hash e um token CSRF independente. Cookies são HttpOnly e SameSite=Lax; produção
exige Secure. `sonda_visitor` identifica a demo entre sessões e resets, sem expor
o id do ambiente. Recuperar acesso não prolonga a validade de 24 horas.

Respostas de `/api/*` usam `Cache-Control: no-store`. Corpos de comandos têm
limite de 16 KiB. Erros não repetem senhas ou o conteúdo recebido.

Escritas precisam de `Origin` exatamente igual à `APP_URL` e `X-CSRF-Token`
obtido em `/api/auth/csrf`. Comandos vinculados ao ambiente também precisam de
`X-Sonda-Workspace`, capturado antes de obter o CSRF. Esse valor é uma expectativa
de geração, nunca um seletor de autorização: a sessão do banco determina o acesso.
Uma geração diferente é recusada antes do CSRF com 404.
Leituras de recursos também recusam uma expectativa de geração diferente quando
esse header é enviado. A consulta de autenticação permite recuperar a geração atual.

| Método e rota | Resultado |
| --- | --- |
| GET `/api/auth/csrf` | 200 `{csrf}`; cria sessão anônima se necessário |
| GET `/api/auth` | 200 `{workspace_id,kind,expires_at}`; 404 sem ambiente válido |
| POST `/api/demo/start` | 201 com projeção de acesso; recupera demo válida ou cria outra |
| POST `/api/demo/reset` | 201 com nova geração; requer geração e identidade demo |
| POST `/api/auth/login` | 200 com projeção de acesso; JSON estrito `{email,password}` |
| POST `/api/auth/logout` | 200 `{signed_out:true}`; exige geração e invalida a sessão |
| GET `/api/monitors` | 200 `{monitors:[...]}` do ambiente autorizado |
| GET `/api/monitors/{uuid}` | 200 com serviço autorizado; 404 para outro ambiente |
| PATCH `/api/monitors/{uuid}` | 200 com serviço atualizado; JSON `{expected_version,enabled?,fixture_mode?}` |
| POST `/api/monitors/{uuid}/checks` | JSON `{key:uuid}`; 200 com resultado ou 202 com replay ainda pending |
| GET `/api/checks/{uuid}` | 200 com tentativa autorizada |
| GET `/api/incidents/{uuid}` | 200 com incidente, evidências e eventos |
| POST `/api/incidents/{uuid}/ack` | JSON `{expected_version,comment}`; 200 com reconhecimento |

Projeções de monitor contêm `id`, `name`, `target_kind`, `target_url`,
`interval_seconds`, `fixture_mode`, `enabled`, `observed_state`, `version`,
`failure_streak`, `success_streak`, `last_check` e `active_incident`.
O detalhe acrescenta `checks` (até 60 mais recentes), `history_limit:60`,
`incidents` (até 20 mais recentes, incluindo resolvidos) e `incident_history_limit:20`.
Não há resultados inventados, token de lease ou segredo interno nessas projeções.
Datas são ISO 8601 com zona UTC. Identificadores são UUID.

## Erros e limites

Erros de domínio: `{error:{code,message,current?}}`. `NOT_FOUND` usa 404,
`CSRF_INVALID` usa 419, `LOGIN_INVALID` usa 401, `INPUT_INVALID` usa 422,
`BODY_TOO_LARGE` usa 413 e `RATE_LIMITED` usa 429 com `Retry-After` em segundos.
Login desconhecido e senha incorreta usam a mesma resposta; ambos executam scrypt.
Não há cadastro público. Flags de demo/login desabilitadas retornam 404.

Inícios: 10 por minuto/IP. Login: 10 por minuto/IP, incluindo tentativas inválidas.
Reset: 1 por minuto/visitante e 10 por hora/IP; a propriedade é verificada antes
de consumir esses limites. Contadores usam janelas fixas e relógio PostgreSQL.
Verificações: 6 por minuto/visitante e 60 tentativas aceitas por geração, incluindo
abandonadas. Replays não consomem outro limite. Quota total retorna 429 DEMO_QUOTA,
com prazo restante da geração em Retry-After. Alteração de cenário, pausa e
reconhecimento: 30 por minuto/visitante. Alvos normais são imutáveis na API.

Versão antiga retorna 409 VERSION_CONFLICT com `current`. Lease em andamento
retorna 409 CHECK_RUNNING. Chave vinculada a outro monitor retorna 409
IDEMPOTENCY_CONFLICT. Resultado atrasado retorna 410 CHECK_SUPERSEDED.
Monitor pausado recusa nova execução com 409 MONITOR_PAUSED.

Reconhecimento exige comentário de 3 a 500 caracteres e versão atual; não resolve
o incidente. Incidentes reconhecidos ou resolvidos recusam outro reconhecimento
com 409 INCIDENT_READONLY. Duas falhas abrem o incidente; dois sucessos
consecutivos o resolvem. Evidências e eventos permanecem na consulta do incidente.

## Alvos internos da demonstração

GET `/probe/{uuid}` exige `X-Sonda-Probe`, um segredo interno distinto do de
sessão. Autenticação ocorre antes da consulta ao monitor. Sem esse segredo,
monitor inexistente, geração revogada ou vencida retornam 404 sem dados de ambiente.
Um alvo válido devolve corpo vazio e 200 ou 503 conforme `fixture_mode` no banco,
com `Cache-Control: no-store`. Essa rota não aceita alterações administrativas.
