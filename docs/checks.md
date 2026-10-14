# Tentativas, leases e resultados

Os serviços de persistência, comando HTTP integrado e transições de incidentes
estão implementados. A interface e o runtime hospedado ainda serão verificados.

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
Estado observado, sequências, incidente e eventos também fazem parte dessa
transação. Uma falha injetada no evento reverte todas essas alterações.

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

## Incidentes

Duas falhas consecutivas confirmam indisponibilidade e abrem um incidente único,
com a primeira falha e a verificação que confirmou a sequência. Uma primeira
falha não inventa indisponibilidade confirmada. Abandono não altera a saúde.

O reconhecimento registra um comentário de 3 a 500 caracteres, inclusive quebras
de linha, ator e horário. Ocorre uma vez, com versão atual. Um conflito devolve
os dados atuais; o comentário enviado não substitui o anterior.
Reconhecimento mantém o incidente ativo. Dois sucessos consecutivos confirmam
recuperação e o resolvem; sucesso seguido de falha mantém o incidente aberto.
Incidente resolvido é somente leitura e conserva suas evidências.

Uma consulta única monta cada projeção de monitor ou incidente com resultado,
evidências e eventos, evitando misturar snapshots de versões diferentes.
O detalhe do monitor devolve até 60 tentativas mais recentes, limite explícito;
todos os resultados continuam armazenados. A demo inteira tem quota de 60.
O detalhe também mantém acesso aos 20 incidentes mais recentes, incluindo
resolvidos; recuperar o serviço não faz sua evidência desaparecer da navegação.

## Runner

Somente ambientes normais entram em `run-due --once`. A seleção usa
FOR UPDATE SKIP LOCKED, lote máximo dez, chaves UUID geradas pelo servidor e o
mesmo serviço de claim/finalização. Próxima execução é definida depois do claim,
com intervalo mínimo de 60 segundos. A transação termina antes da rede.
Até quatro verificações são executadas simultaneamente no lote.

O teste com dois processos mantém o primeiro lote bloqueado e comprova que o
segundo termina com os monitores restantes antes de liberar o primeiro.
Nenhum endpoint público dispara o runner e não há cron contratado na Vercel.
