# Arquitetura

Sonda é um monólito modular. FastAPI atende acesso, consultas e comandos;
Svelte apresenta os registros e captura a versão e a geração de cada ação.
PostgreSQL é a autoridade de identidade, relógio, limites e estado.

## Ciclo de uma verificação

1. O comando resolve a sessão e confere a geração esperada antes do CSRF.
2. Uma transação bloqueia o ambiente para leitura e o monitor para alteração.
   A chave idempotente é serializada antes do monitor; a quota demo tem um
   bloqueio próprio por ambiente.
3. O claim grava uma tentativa e um lease de 30 segundos, e libera a conexão.
4. O executor valida o alvo, resolve DNS, rejeita conjuntos com endereços
   privados e conecta aos IPs já validados. Host e SNI preservam o hostname.
5. Outra transação verifica validade, lease e versão. Resultado, contadores,
   incidente e eventos são gravados juntos. Uma resposta tardia não muda o estado.

Nenhuma conexão ou transação fica retida durante a chamada HTTP. O tempo medido
vai até os headers; o corpo remoto não é armazenado. Repetir uma chave finalizada
devolve a mesma evidência, sem outra chamada ou consumo de quota.

## Estado e evidência

Dois resultados de falha consecutivos abrem um incidente. Dois sucessos
consecutivos o resolvem. Uma única recuperação seguida de falha mantém o
incidente aberto. Reconhecer um incidente registra operador e comentário; não
declara recuperação. O reconhecimento ocorre uma vez e exige a versão atual.

Resultados finalizados e eventos são imutáveis. Chaves estrangeiras compostas
impedem referências entre ambientes. A coleta pode remover uma geração inteira,
mas não reescrever sua história. Índice parcial garante um incidente ativo por
monitor. Pausar ou alterar cenário invalida a execução pendente, sem inventar falha.

## Interface e concorrência

Cada leitura tem cancelamento e sequência de resposta. Trocar de monitor ou
geração impede que uma resposta antiga substitua a tela atual. Comandos capturam
a geração antes de pedir CSRF; a API confere a expectativa contra a sessão.

Um conflito exige atualizar os dados explicitamente. Comentários permanecem na
tela, inclusive após reset em outra aba. A chave da verificação permanece até um
resultado terminal; repetir a consulta recupera o mesmo comando. A sequência de
observações e a tabela usam os mesmos resultados, sem preencher lacunas fictícias.

## Execução e limites

O processo HTTP não aplica migrations, provisiona usuários nem inicia agendamento.
Os comandos administrativos são explícitos. O runner atende somente instalações
administradas, uma vez por chamada, em lotes de até dez monitores, usando
`SKIP LOCKED` e até quatro execuções HTTP simultâneas.

A demo é manual, separada por visitante e válida por 24 horas fixas. Limites e
quotas persistem no banco; iniciar outra geração preserva a identidade usada nos
limites. Não há cálculo de disponibilidade de 24 horas a partir de amostras manuais.

## Verificação

Os testes de integração exigem role e banco `sonda_test` em loopback e criam
schemas próprios. A concorrência é observada entre processos distintos, com
`pg_blocking_pids` e controle negativo sem proteção. Testes de rede usam servidores
HTTP/TLS reais e conferem os endereços efetivamente entregues ao conector.

Playwright percorre a aplicação com FastAPI, PostgreSQL e fixtures HTTP reais.
Essas evidências locais não estabelecem funcionamento em produção: deploy exige
verificação própria de HTTPS, cookies, permissões e persistência após nova versão.
