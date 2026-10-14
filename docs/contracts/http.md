# HTTP do Sonda

Este contrato registra as rotas implementadas. Verificações e incidentes serão
acrescentados quando suas regras e persistência estiverem prontas.

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

As projeções iniciais de monitor contêm `id`, `name`, `enabled`, `observed_state`,
`version`, `failure_streak` e `success_streak`. Não há resultados inventados.
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
Verificações e seus limites ainda não fazem parte das rotas implementadas.
