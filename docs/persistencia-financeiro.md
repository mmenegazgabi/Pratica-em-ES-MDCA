# Persistência do Financeiro e integração com a Gestão

Até aqui o Financeiro guardava projetos, orçamentos, lançamentos, notificações e
rascunhos em listas na memória da API: reiniciar o Cloud Run apagava tudo, cada
instância tinha os seus dados e a Visão integrada da Gestão não enxergava o mesmo
cadastro de programas. Agora, com `DATABASE_URL`, tudo vai para o PostgreSQL
compartilhado com a Gestão.

## Onde cada coisa fica

| Dado do Financeiro | Tabela |
|---|---|
| Projetos | `projetos` — o cadastro canônico de programas, **o mesmo da Gestão** |
| Orçamentos | `orcamentos` (valor, vigência, lista de categorias) |
| Valor orçado por categoria | `orcamento_categorias` |
| Lançamentos (despesas) | `lancamentos` |
| Notificações in-app | `notificacoes` (nova) |
| Rascunhos de despesa | `rascunhos_despesa` (nova) |

O saldo não é gravado: é recalculado a partir dos lançamentos aprovados toda vez que o
orçamento é lido, como já era.

Código: `Backend/Financeiro/persistencia.py`. As regras de negócio continuam nos mesmos
lugares (`orcamento.py`, `projetos.py`...); as rotas recebem o repositório por
`Depends(obter_repositorio)` e fazem o commit antes de responder. Alterações num
orçamento (aprovar, rejeitar, reenviar, conciliar, editar) leem o orçamento com
`SELECT ... FOR UPDATE`, então duas aprovações simultâneas não debitam duas vezes, mesmo
com várias instâncias da API.

## Integração com a Gestão

- `GET /projetos` do Financeiro lista os programas cadastrados na Gestão. O orçamento é
  criado direto no programa (`projeto_id` = id do programa), sem recadastro.
- `POST /projetos` com o nome de um programa que já existe responde 409.
- A Visão integrada da Gestão (`/gestao/programas/{id}/visao-integrada`) lê orçamentos e
  lançamentos do banco pela mesma conexão e casa o programa **pelo id**. O casamento pelo
  nome só acontece quando os orçamentos estão num projeto separado com o mesmo nome.

## Produção: aplicar a migration

A migration `c2d8e4f6a1b3` (em `Backend/Shared/migrations/versions/`) só **adiciona**
colunas em `lancamentos` (`criado_em`, `aprovado_em`, `motivos_rejeicao_anteriores`) e as
tabelas `notificacoes` e `rascunhos_despesa`. Por ser só adição, pode ser aplicada
**antes do merge**, com o código antigo ainda no ar — é o caminho mais seguro, porque o
deploy na `main` é automático e o código novo precisa dessas colunas:

```bash
cd Backend/Shared
# DATABASE_URL da produção no ambiente ou em Backend/.env
alembic current        # conferir em que revisão o banco está
alembic upgrade head   # aplica o que faltar, incluindo c2d8e4f6a1b3
```

Os dados que estavam em memória no Cloud Run não são migrados (não há de onde
lê-los); orçamentos de teste precisam ser cadastrados de novo.

Rollback: `alembic downgrade 4e3a59521428` remove só o que esta migration criou (e
apaga as notificações e rascunhos gravados).

## Rodar local

- **Sem banco** (sem `DATABASE_URL`): o Financeiro usa a memória, como antes, e avisa
  no log. Os testes do Financeiro sempre rodam assim.
- **Com banco**: exporte `DATABASE_URL` apontando para um banco **de desenvolvimento**
  e rode `alembic upgrade head` em `Backend/Shared`.
- `FINANCEIRO_ARMAZENAMENTO=memoria` força a memória mesmo com `DATABASE_URL`.

## Testes

- `Backend/Financeiro/tests/` — todos os testes de rotas, em memória.
- `Backend/Financeiro/tests/test_persistencia_banco.py` — o fluxo pela API contra um
  PostgreSQL descartável (`TEST_DATABASE_URL`), conferindo no banco e depois de esvaziar
  a memória do processo. Sem `TEST_DATABASE_URL` eles são pulados; no CI rodam no job
  "Infraestrutura integrada".
- `Backend/Gestao/tests/test_gestao_visao_integrada*.py` — a Visão integrada lendo o
  Financeiro do banco.
