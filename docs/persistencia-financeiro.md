# Persistência do Financeiro e integração com a Gestão

Trabalhos 1 e 2 do plano de integração Gestão + Financeiro (10/11/2026).

Até aqui o Financeiro guardava projetos, orçamentos, lançamentos, notificações e
rascunhos em listas na memória da API: reiniciar o Cloud Run apagava tudo, cada
instância tinha os seus dados e a Visão integrada da Gestão procurava o projeto pelo nome.
Agora, com `DATABASE_URL`, tudo vai para o PostgreSQL compartilhado com a Gestão, e o
Financeiro usa o mesmo cadastro de programas.

## Onde cada coisa fica

| Dado do Financeiro | Tabela |
|---|---|
| Projetos | `projetos` — o cadastro canônico de programas, **o mesmo da Gestão** |
| Orçamentos | `orcamentos` (valor, vigência e a lista ordenada de categorias) |
| Valor orçado por categoria | `orcamento_categorias` (só as categorias com limite) |
| Lançamentos (despesas) | `lancamentos` |
| Notificações in-app | `notificacoes` (nova) |
| Rascunhos de lançamento | `rascunhos_lancamento` (nova) |
| Arquivos dos comprovantes | bucket R2 (sem mudança) |

- `orcamentos.categorias` **continua necessária**: guarda todas as categorias do
  orçamento e a ordem delas. `orcamento_categorias` só tem as que têm valor orçado.
- O saldo não é gravado: é recalculado a partir dos lançamentos aprovados toda vez que o
  orçamento é lido, em centavos.
- `lancamentos.comprovante_chave` guarda a chave do arquivo no R2;
  `comprovante_url` continua com o caminho que a API mostra (`/` + chave).

## Como o código está organizado

- `Backend/Shared/banco.py` — a conexão com o banco, uma só para Gestão, Financeiro e
  login único (um pool por processo). `Gestao/banco.py` e `Shared/sessao.py` reexportam
  daqui, com os mesmos nomes de antes.
- `Backend/Financeiro/persistencia.py` — o repositório: lê e grava as tabelas acima. As
  regras de negócio continuam onde estavam (`orcamento.py`, `projetos.py`,
  `alerta_saldo.py`).
- As rotas recebem o repositório por `Depends(obter_repositorio)` e fazem o commit antes
  de responder. Se algo falhar no meio, nada é gravado.
- **Concorrência:** aprovar, rejeitar, reenviar, conciliar e editar leem o orçamento com
  `SELECT ... FOR UPDATE`. Duas aprovações ao mesmo tempo esperam uma pela outra, mesmo
  em instâncias diferentes do Cloud Run: o lançamento é aprovado uma vez só e o saldo cai
  uma vez só. Listar e consultar não travam.
- **Sem `DATABASE_URL`** (testes, execução local sem banco) o Financeiro usa a memória,
  como antes, e avisa no log. `FINANCEIRO_ARMAZENAMENTO=memoria` força a memória mesmo
  com `DATABASE_URL`.

## Integração com a Gestão

- `GET /projetos` do Financeiro lista os programas cadastrados na Gestão, com o status
  (ativo ou encerrado) usado pelo dashboard. O orçamento é criado direto no programa
  (`projeto_id` = id do programa), sem recadastro.
- `POST /projetos` continua existindo e grava na mesma tabela. Com o nome de um programa
  que já existe (sem diferenciar maiúsculas e acentos), responde 409. Se ele sai ou vira
  um atalho para o cadastro da Gestão é decisão do time (Riscos, no plano).
- A Visão integrada da Gestão (`/gestao/programas/{id}/visao-integrada`) lê os orçamentos
  do programa pela mesma conexão e liga **só pelo id**: `vinculo` é `id` quando o programa
  tem orçamento e `nenhum` quando ainda não tem. A busca pelo nome saiu.

## Rotas removidas

`POST /orcamentos/{id}/lancamentos/{id}/aprovar` e
`POST /orcamentos/{id}/lancamentos/{id}/reverter-aprovacao` (T-07) não pediam login e
nenhuma tela as usava. A aprovação é `PATCH /lancamentos/{id}/aprovar`, que exige o papel
de Coordenação ou Direção.

## Produção: aplicar a migration antes do merge

**Situação:** aplicada na produção em 10/11/2026 (`6bd565cae094` → `c2d8e4f6a1b3`).

A migration `c2d8e4f6a1b3` vem **depois** da `6bd565cae094` (alertas da Gestão, T-59) e
só **adiciona**:

- em `lancamentos`: `criado_em`, `aprovado_em`, `rejeitado_em`, `conciliado_em`,
  `motivos_rejeicao_anteriores` e `comprovante_chave` (preenchida a partir de
  `comprovante_url` nas linhas que já existem);
- as tabelas `notificacoes` e `rascunhos_lancamento`.

O código que está no ar hoje continua funcionando com o banco migrado (testado), então a
migration pode e deve ser aplicada **antes do merge**. O deploy da `main` é automático e o
código novo precisa dessas colunas.

```bash
cd Backend/Shared
# DATABASE_URL da produção no ambiente ou em Backend/.env
alembic current        # conferir em que revisão o banco está
alembic upgrade head   # aplica o que faltar, incluindo 6bd565cae094 e c2d8e4f6a1b3
alembic current        # deve mostrar c2d8e4f6a1b3 (head)
```

Os dados que estavam em memória no Cloud Run não são migrados (não há de onde lê-los).
Orçamentos e lançamentos de demonstração precisam ser cadastrados de novo.

Rollback: `alembic downgrade 6bd565cae094` remove só o que esta migration criou (e apaga as
notificações e os rascunhos gravados). Os lançamentos continuam lá.

## Dados de demonstração

`scripts/carga-demonstracao.py` cria as contas da apresentação (Coordenação, Direção,
voluntário financeiro e um educador com vínculo), os programas Divertidamente e Adolescer
(reaproveita se já existirem), um orçamento de 2026 em cada um e lançamentos em todos os
estados. Tudo com id `demo-`; pode rodar de novo sem duplicar, e `--remover` desfaz.
Pede a senha das contas no terminal e confirmação (`SIM`) antes de gravar.

## Rodar local

- **Sem banco:** não defina `DATABASE_URL`. O Financeiro usa a memória.
- **Com banco:** exporte `DATABASE_URL` apontando para um banco **de desenvolvimento**
  (nunca o de produção) e rode `alembic upgrade head` em `Backend/Shared`.

## Testes

| Arquivo | O que cobre | Banco |
|---|---|---|
| `Backend/Financeiro/tests/*` | regras e rotas do Financeiro | memória |
| `Financeiro/tests/test_persistencia_banco.py` | fluxo pela API conferido por SQL, "reinício" (memória esvaziada), trava entre conexões, 503 sem banco | Postgres |
| `Financeiro/tests/test_paridade_memoria_banco.py` | sequências aleatórias de chamadas (sementes fixas) com respostas idênticas na memória e no banco, e iguais depois do reinício | Postgres |
| `Shared/tests/test_migration_persistencia_financeiro.py` | um único head e histórico em linha (sem banco); colunas, regras, preenchimento e downgrade da migration | Postgres |
| `Gestao/tests/test_gestao_visao_integrada*.py` | a Visão integrada lendo o Financeiro do banco, só pelo id | Postgres |
| `Financeiro/tests/test_acesso_por_papel.py` | T-36: papel vindo do login, educador restrito ao vínculo, Coordenação vê tudo, voluntário não aprova | Postgres |
| `Financeiro/tests/test_auditoria_financeiro.py` | T-34: cada ação na trilha, mesma transação, acesso negado, quem lê a trilha | Postgres |

Os testes de banco usam um PostgreSQL descartável em `TEST_DATABASE_URL`. Sem ele são
pulados localmente; no CI a falta do banco é erro. Os jobs `backend-financeiro`,
`backend-gestao` e `backend-infra` sobem um Postgres próprio.

`MDCA_SEMENTES_PARIDADE=300` roda 300 cenários de paridade em vez dos 8 do CI.
