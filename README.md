# Sonda

Monitoramento HTTP e registro de incidentes com Python/FastAPI, TypeScript e
PostgreSQL. Projeto de portfólio de Diogo Pereira, em implementação.

O percurso definido verifica um serviço, abre um incidente após duas falhas
consecutivas, registra o reconhecimento de um operador e confirma a recuperação
após duas respostas saudáveis. A demonstração usará alvos fictícios controlados
pelo projeto, com chamadas HTTP reais e ambientes separados por visitante.

## Estado atual

A fundação implementa configuração estrita, conexões PostgreSQL com TLS verificado
em produção, migrations transacionais com checksum e `/health/ready`.
Não aplica migrations nem cria usuários durante o startup.

Passaram 112 testes locais. Os testes de integração usam o banco `sonda_test`
e schemas temporários próprios.
Um processo HTTP separado verifica prontidão 503 antes das migrations e 200 depois,
sem reiniciar o servidor. Testes também verificam configuração de produção,
isolamento da seleção de schema e tratamento explícito de headers de proxy.

O acesso implementa sessões persistentes, demos com duração fixa de 24 horas,
quatro monitores inicialmente desconhecidos e isolamento entre visitantes.
Dois processos HTTP separados recuperam a mesma sessão pelo PostgreSQL.
Escritas exigem origem exata e CSRF; comandos de uma geração antiga são recusados.
Reset troca a geração e invalida o acesso anterior.

Instalações administradas usam scrypt salgado, login limitado por IP e sessões
regeneradas. Alterar a senha revoga o acesso anterior, inclusive quando uma
verificação da senha antiga ainda está em andamento. A coleta usa lotes limitados
e pula ambientes com operações em andamento.

O transporte HTTP já verifica destinos autorizados, rejeita DNS privado, fixa
os IPs validados no conector e verifica TLS. Chamadas reais às fixtures devolvem
200 ou 503 conforme o cenário no banco. Redirecionamentos, timeout e certificados
foram testados em servidores locais. [Regras e evidências de rede](docs/network.md).

Persistência de verificações, incidentes e interface ainda não estão implementados.
Não há demonstração publicada ou resultado comercial a alegar.

## Executar a fundação

Requisitos: Python 3.13 e PostgreSQL 17. Crie um ambiente virtual e instale as
dependências fixadas:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Configure no ambiente as variáveis listadas em `.env.example`, usando banco e
credenciais próprios. O arquivo de exemplo não é carregado automaticamente.
`SESSION_SECRET` e `PROBE_SECRET` devem ser diferentes, com pelo menos 32 caracteres.
Produção exige `SONDA_ENV=production`, HTTPS e `DB_TLS=true`.

```powershell
./.venv/Scripts/python.exe -m scripts.migrate
./.venv/Scripts/python.exe -m scripts.dev
```

O servidor local usa `127.0.0.1:5095`. A factory de loop local é compatível com
psycopg no Windows; não altera a instalação global do Python.

## Acesso administrado e coleta

Após aplicar as migrations, `python -m scripts.install_user` recebe exclusivamente
um objeto JSON por stdin com `email`, `name` e `password`. Não passe credenciais em
argumentos de terminal. O nome tem 3 a 80 caracteres e a senha, 12 a 128, sem
caracteres de controle. Não existe senha padrão ou cadastro público.
Reexecutar o comando para o mesmo email atualiza a senha e revoga suas sessões.
Habilite `SONDA_LOGIN_ENABLED=true` para oferecer login HTTP.

`python -m scripts.cleanup --batch 10` executa uma coleta, com máximo de 1.000
registros por categoria. Só remove ambientes demo expirados ou revogados,
sessões vencidas e contadores vencidos. A identidade do visitante permanece para
os limites entre gerações. Iniciar uma demo também tenta uma coleta de até 10
registros por categoria, no máximo uma vez por minuto pelo relógio do banco.

[Contrato de acesso HTTP](docs/contracts/http.md).

Para testar, configure `SONDA_TEST_DATABASE_URL` com uma role e banco separados
`sonda_test` em localhost, além das demais variáveis de teste. No ambiente local
da coleção, `scripts/bootstrap.ps1` prepara somente os bancos do Sonda;
`scripts/local-env.ps1 -Test` carrega a configuração privada já criada.

```powershell
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check sonda scripts tests
./.venv/Scripts/python.exe -m mypy
```

As verificações acima são locais. CI e hospedagem serão comprovadas na etapa de
publicação. [Regras do produto](docs/superpowers/specs/2026-10-13-sonda-design.md).
