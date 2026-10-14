# Executor HTTP

O transporte realiza chamadas HTTP reais e grava resultados e transições de
incidente pelo serviço integrado. Não há verificação em
background na demonstração.

## Destinos

Alvos normais precisam de HTTPS na porta 443 e hostname explicitamente incluído
em `SONDA_ALLOWED_HOSTS`, separado por vírgula. Os nomes são normalizados em
minúsculas/IDNA; não existem wildcards. IPs literais, credenciais na URL, query,
fragmento, controles, localhost e domínios locais não são destinos normais.
Não existe configuração de alvo por visitantes.

As fixtures são exclusivamente `/probe/{uuid}` na origem de `APP_URL`. Em produção
essa origem também precisa de HTTPS e hostname. Fora de produção, a exceção local
permite somente a origem exata configurada em loopback/localhost e esse percurso.
Ela não autoriza chamadas para outras portas, caminhos administrativos ou hosts.

O fetcher valida novamente o alvo recebido. Flags de um objeto construído pelo
chamador não podem transformá-lo em fixture ou permitir endereço privado.

## DNS, conexão e TLS

O resolver rejeita o conjunto inteiro quando qualquer endereço não é global,
incluindo privados, link-local, multicast, reservados, IPv4 mapeado em IPv6 e
endereços com scope id. Ele devolve ao conector apenas IPs numéricos já validados,
preservando o hostname original. Não há segunda resolução entre validação e
conexão, cache DNS compartilhado ou conexão reutilizada entre verificações.

O certificado e o hostname são verificados. O hostname da URL permanece no Host
e SNI. A confiança usa certifi; não há opção de ambiente para desabilitar TLS.
Contextos TLS injetados em testes também precisam de CERT_REQUIRED e hostname.
O [contrato de resolver do aiohttp](https://docs.aiohttp.org/en/stable/abc.html#abstract-resolver)
define os resultados usados pelo conector.

## Limites e resultado

Até quatro chamadas concorrentes por instância do fetcher. O limite total é de
cinco segundos, incluindo DNS e espera por headers; conexão tem limite de dois.
O relógio de latência é monotônico. Não se carrega o corpo completo nem se gravam
headers ou corpo remoto. A resposta é fechada após os headers.

Redirecionamentos não são seguidos, cookies remotos não são retidos e proxies de
ambiente não são utilizados. O segredo `X-Sonda-Probe` só acompanha fixtures da
origem exata; nunca entra em URL, redirecionamento ou alvo externo. As opções de
timeout, TLS e proxy seguem a [API de cliente do aiohttp](https://docs.aiohttp.org/en/stable/client_reference.html).

Resultados usam `{status_code,duration_ms,error_code}`. Status 2xx é saudável.
Os códigos são `TARGET_REJECTED`, `DNS_REJECTED`, `DNS_ERROR`, `CONNECT_ERROR`,
`TLS_ERROR`, `TIMEOUT`, `REDIRECT_NOT_ALLOWED` e `HTTP_STATUS`. Exceções não
expõem URL, credencial, stack, endereço privado ou resposta remota.

## Evidência local e seus limites

Testes TCP reais verificam 200, 503, redirecionamento sem segunda chamada,
retorno antes de um corpo retido e timeout com headers retidos. Certificados
temporários gerados por OpenSSL verificam confiança, hostname incorreto e SNI.
Nenhuma chave privada é incluída no repositório.

A prova de pinagem observa os endereços passados ao conector, altera a fonte DNS
depois da resolução e confirma uma única consulta. A rejeição de DNS misto tem
controle negativo: remover deliberadamente o guard permite o endereço privado
alcançar o conector. Esse teste interrompe a conexão antes da rede.

Um processo HTTP separado executa o Sonda real; o fetcher acessa sua fixture e
observa a mudança 200 para 503 persistida no PostgreSQL. Isso comprova o transporte
local. DNS público e TLS no runtime hospedado ainda serão verificados no deploy.
