# Sonda

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.13/FastAPI e PostgreSQL 17 no backend; Svelte e TypeScript na interface.
Dependências de backend já estão fixadas; a interface está planejada.

## Users

O produto foi escolhido para demonstrar desenvolvimento full stack a recrutadores.
O cenário de uso proposto é uma equipe pequena que precisa investigar falhas de
serviços HTTP. Esse cenário orienta o desenho; não representa um cliente existente.

## Product Purpose

Verificar um serviço HTTP, registrar o resultado e acompanhar a abertura,
reconhecimento e recuperação de um incidente. O avaliador deve conseguir percorrer
esse ciclo e explicar por que cada mudança aconteceu.

## Positioning

O mecanismo central combina requisição de rede limitada, resultados persistentes,
transições de incidente e execução concorrente protegida pelo PostgreSQL.
A interface apresenta os registros que sustentam cada estado.

## Operating Context

A demonstração pública terá ambientes separados por visitante, com alvos fictícios
controlados pelo próprio projeto e chamadas HTTP reais. Falhas são provocadas
explicitamente para permitir experimentar o ciclo completo.
Uma instalação administrada poderá verificar alvos previamente autorizados.

## Capabilities and Constraints

Sem cadastro de URLs arbitrárias por visitantes, notificações externas, cobrança,
monitoramento de redes privadas, scripts de usuário ou promessa de operação24h.
A versão pública oferece verificações manuais; um runner explícito atenderá
verificações programadas na instalação administrada. Deploy visual na Vercel,
banco gratuito separado, documentação útil e dados fictícios identificados.

## Evidence on Hand

O conceito foi aprovado na coleção. A pasta4 estava vazia na inspeção inicial.
Backend e banco local próprios implementados, com 147 testes locais: acesso,
transporte HTTP, leases, incidentes, eventos e runner. O ciclo real de falha e
recuperação passou por HTTP. Interface Svelte implementada: 19 testes e cinco
percursos de navegador com API, PostgreSQL e chamadas HTTP reais. Desktop e
celular foram inspecionados; revisão independente, CI e runtime hospedado pendentes.

## Product Principles

- Mostrar o último resultado e sua idade antes de declarar o serviço disponível.
- Distinguir uma falha observada de uma execução perdida ou interrompida.
- Registrar reconhecimento humano e recuperação automática como ações diferentes.
- Preservar resultados e comentários quando duas telas disputarem uma alteração.
- Não aceitar um destino de rede apenas porque sua URL parece pública.

## Accessibility & Inclusion

Português brasileiro, operação por teclado, foco visível, status textual,
registros legíveis no celular e movimento reduzido. Gráficos precisam de registros
equivalentes em texto; cor não pode carregar sozinha o significado de uma falha.
