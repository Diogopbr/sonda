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

Passaram 25 testes locais. Os testes de integração usam o banco `sonda_test`
e schemas temporários próprios.
Um processo HTTP separado verifica prontidão 503 antes das migrations e 200 depois,
sem reiniciar o servidor. Testes também verificam configuração de produção,
isolamento da seleção de schema e tratamento explícito de headers de proxy.

Sessões, verificações HTTP, incidentes e interface ainda não estão implementados.
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
