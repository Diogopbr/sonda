# Tentativas, leases e resultados

Esta etapa implementa os serviços de persistência. O comando HTTP para executar
uma verificação e as transições de incidentes serão ligados a eles na etapa seguinte.

## Claim e repetição

Cada tentativa aceita recebe UUID, chave idempotente do cliente, monitor, ator,
origem, token de lease e prazo de 30 segundos. A chave é única por ambiente e
permanece vinculada ao monitor. Repetir a chave devolve a tentativa existente,
sem outra tentativa ou consumo de limite. Usá-la em outro monitor retorna 409.

A transação bloqueia o ambiente em FOR SHARE, serializa a chave e bloqueia o
monitor em FOR UPDATE. A quota demo usa outro advisory lock, por geração, para
contar as tentativas dos quatro monitores. O relógio do PostgreSQL é consultado
novamente após as esperas, antes de definir início, lease e próxima execução.

Enquanto o lease está válido, outro comando recebe CHECK_RUNNING. Um lease
expirado pode ser abandonado pelo próximo claim. Pausa ou mudança de versão
também impede que a tentativa anterior produza resultado. Abandono preserva
a tentativa aceita e não é falha do serviço.

## Finalização

Claim termina sua transação antes da rede. Finish abre outra, obtém os locks,
consulta o relógio atual e verifica ambiente, ator, monitor, token, prazo, versão
e estado pending. Um resultado atrasado recebe 410 CHECK_SUPERSEDED; ambiente
revogado ou de outro visitante recebe 404. Não altera resultado ou contadores.

A finalização grava os campos de resultado e libera o lease na mesma transação.
Um erro injetado na atualização do monitor reverte o resultado para pending.
As regras de saúde e incidentes serão adicionadas nessa mesma transação.

## Invariantes no banco

FKs compostas mantêm tentativa, monitor, ator e lease no mesmo ambiente. Um
trigger exige início pending, permite uma única transição para finished ou
abandoned e proíbe reescrever identidade ou resultado final. Constraints exigem
campos completos, inclusive quando a validação SQL envolve valores NULL.

Excluir uma tentativa individual é proibido. A coleta da geração inteira pode
removê-la por cascade. Não há alteração de migrations já versionadas.

## Limites demo

Até 60 tentativas aceitas por geração, incluindo abandonadas, e seis por minuto
por visitante. Replays não consomem esses limites; reset preserva a identidade
usada no limite por visitante. 429 temporário inclui Retry-After. A quota total
informa o prazo restante da geração; reiniciá-la é uma ação explícita.

## Provas locais

Dois processos Python e conexões PostgreSQL separados disputam o mesmo monitor.
O observador confirma pg_blocking_pids antes de liberar o primeiro processo.
Só uma tentativa é aceita. O controle negativo sem FOR UPDATE deixa ambos
aceitarem a partir do mesmo snapshot, mostrando por que a proteção é necessária.

Outro teste disputa a quota entre monitores com 58 e 59 tentativas abandonadas
preexistentes. Observa o bloqueio no advisory lock e confirma máximo 60, além de
um início de lease posterior à liberação. A versão que reutilizava o relógio
anterior à espera falhou nesse teste antes da correção.

Uma disputa da mesma chave em dois monitores espera pelo lock da chave e devolve
IDEMPOTENCY_CONFLICT ao segundo. Testes também cobrem replay finalizado, perda de
lease, pausa, reset, isolamento, FKs, limite de frequência e rollback.
