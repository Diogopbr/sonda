# Implantação

O projeto usa o framework FastAPI da Vercel, com entrypoint `sonda.main:app` e
função em `gru1`. Python é limitado a 3.13. O `uv.lock` mantém as mesmas versões
de runtime verificadas em `requirements.txt`, incluindo marcadores de plataforma.
O build instala o frontend pelo lockfile e gera `web_dist/`; não aplica migrations.

O HTML precisa permanecer no pacote Python para atender as rotas conhecidas.
O empacotador exclui diretórios `public/` da função, por isso o build usa um
diretório próprio. Somente os subdiretórios públicos são montados e promovidos
ao CDN; o diretório inteiro da aplicação não é exposto.

As pastas `assets/` e `fonts/` são públicas. Apenas rotas HTML conhecidas entregam
o documento da aplicação. Nenhum diretório de código, configuração privada ou
testes é montado. A promoção dos assets para o CDN é explícita; headers de
segurança também são configurados na plataforma, pois o CDN não executa middleware.

## Banco e segredos

O PostgreSQL hospedado é um recurso Neon Free próprio, na região São Paulo.
Migrations são aplicadas explicitamente com a credencial administrativa e
conexão direta. A aplicação conecta com outra role, usando TLS `verify-full`
e certificados de confiança do certifi. A role não é superusuária, não cria
bancos, roles ou schemas. Metadados de migrations são somente leitura; eventos
permitem apenas `SELECT` e `INSERT`. O restante das tabelas permite as operações
necessárias aos serviços e à coleta de gerações.

`DATABASE_URL`, `SESSION_SECRET` e `PROBE_SECRET` são segredos de ambiente.
As variáveis administrativas da integração ficam desconectadas da aplicação.
`APP_URL` precisa coincidir com a origem pública canônica, usada para CSRF e para
os alvos internos. Segredos de sessão e de probe são distintos e permanecem
estáveis entre versões. Produção exige HTTPS, TLS do banco e booleanos explícitos.

## Evidência já obtida

No recurso próprio foram aplicadas quatro migrations com TLS verificado.
Uma execução pela role limitada gravou claims, resultados, incidente e evento.
Operações reais de `UPDATE` e `DELETE` em eventos e `CREATE SCHEMA` foram recusadas.
Reescrever um resultado finalizado também foi recusado. A remoção do ambiente
exclusivo dessa verificação coletou suas evidências por cascade, sem tocar dados
de outros ambientes.

Build remoto, CI, navegação HTTPS, cookies, fluxo completo e persistência após
redeploy ainda precisam de verificação própria antes de declarar a demo publicada.

Referências: [FastAPI na Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
e [runtime Python](https://vercel.com/docs/functions/runtimes/python).
