# Backend/Gestao

Backend do Módulo de Gestão.

Dono: time de Gestão.

## Estrutura

```
Gestao/
  banco.py        # conexão com o PostgreSQL (DATABASE_URL), via Depends(obter_conexao)
  programas.py    # regras e consultas do domínio (uma por assunto)
  routers/        # rotas FastAPI, todas com prefixo /gestao
  tests/          # testes do módulo, rodados pelo job backend-gestao do CI
```

- A API não tem entrada própria: os routers são registrados em
  [`Backend/main.py`](../main.py), a entrada única publicada no Cloud Run.
  Toda rota nova precisa de um `app.include_router(...)` lá.
- As tabelas são criadas pelas migrations do Alembic em
  [`Backend/Shared/migrations`](../Shared/migrations) (head único, compartilhado com
  o Financeiro). O código de Gestão só lê e grava.
- Sem `DATABASE_URL` configurada ou com o banco fora do ar, as rotas respondem 503.
- Autenticação provisória: o mesmo token de serviço do Financeiro
  (`FINANCEIRO_API_TOKEN`), até o login único (T-35) e o RBAC (T-33).

Rota de exemplo: `GET /gestao/programas` lista o cadastro canônico de
Programas/Projetos (tabela `projetos`, ARQ-02).

## Testes

```bash
cd Backend/Gestao
pip install -r requirements.txt
pytest
```

Os testes que leem do banco precisam de um PostgreSQL descartável em
`TEST_DATABASE_URL` (o nome do banco deve conter `test`; as fixtures apagam dados e
aplicam as migrations). Sem a variável, eles são pulados localmente; no CI a falta
do banco faz o job falhar. Um jeito rápido de subir um banco local:

```bash
docker run --rm -d --name mdca-test -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=mdca_test -p 5432:5432 postgres:16
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/mdca_test pytest
```
