# Backend/Gestao

Backend do Módulo de Gestão.

Dono: time de Gestão.

## Estrutura

```
Gestao/
  banco.py        # conexão com o PostgreSQL (DATABASE_URL), via Depends(obter_conexao)
  programas.py    # programas, convênios e vagas (regras e consultas, um arquivo por assunto)
  plano_de_acao.py  # objetivos, ações, metas, registros do realizado e painel
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

## Rotas

Programas e plano de ação (US-02), sobre o cadastro canônico de Programas/Projetos
(tabela `projetos`, ARQ-02, a mesma que o Financeiro usa em orçamentos e lançamentos):

| Rota | O que faz |
|---|---|
| `GET /gestao/programas` | Lista os programas (id e nome) |
| `POST /gestao/programas` | Cadastra um programa: `nome`, `identificador`, `publico`, `responsavel`, `vigencia_inicio`, `vigencia_fim` e `descricao` opcional |
| `GET /gestao/programas/{id}` | Dados completos do programa |
| `GET`/`POST …/{id}/convenios` | Convênios e parcerias: `nome`, `concedente` e vigência opcionais |
| `GET`/`POST …/{id}/vagas` | Vagas ofertadas: `descricao` e `quantidade` |
| `GET`/`POST …/{id}/objetivos` | Objetivos do plano de ação: `descricao` |
| `GET`/`POST …/{id}/acoes` | Ações de um objetivo: `objetivo_id`, `descricao`, `periodo_inicio`, `periodo_fim`, `resultado_esperado` e `periodicidade` |
| `GET`/`POST …/{id}/metas` | Metas de uma ação: `acao_id`, `descricao`, `valor_planejado` e `unidade` opcional |
| `GET`/`POST …/{id}/metas/{meta_id}/registros` | O que foi realizado: `data`, `valor_realizado` e `observacao` opcional |
| `GET …/{id}/painel` | Planejado, realizado (soma dos registros) e percentual de cada meta |

Regras:

- Campo obrigatório ausente ou em branco responde **400** com a lista do que falta
  (ex.: `Programa sem público e responsável.`). Tipo errado, como uma data mal
  formatada, continua **422**.
- O período de cada ação precisa caber na vigência do programa.
- `periodicidade`: `semanal`, `quinzenal`, `mensal`, `bimestral`, `trimestral`,
  `semestral` ou `anual`.
- Identificador repetido (sem diferenciar maiúsculas) e vagas com a mesma descrição no
  programa respondem **409**. Programa ou meta inexistente: **404**.

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
