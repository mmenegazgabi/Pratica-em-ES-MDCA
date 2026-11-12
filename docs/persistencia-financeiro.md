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
| Extrato bancário importado | `extrato_itens` (nova, `e4b8c1d7f2a9`) |
| Arquivos dos comprovantes | bucket R2 (sem mudança) |

- `orcamentos.categorias` **continua necessária**: guarda todas as categorias do
  orçamento e a ordem delas. `orcamento_categorias` só tem as que têm valor orçado.
- O saldo não é gravado: é recalculado a partir dos lançamentos aprovados toda vez que o
  orçamento é lido, em centavos.
- `lancamentos.comprovante_chave` guarda a chave do arquivo no R2;
  `comprovante_url` continua com o caminho que a API mostra (`/` + chave).
- `extrato_itens` guarda cada linha do CSV importado (`POST /extrato`): `data`,
  `descricao`, `valor` (`numeric(14,2)`, negativo é saída), `importado_em` e
  `conciliado_com` (o lançamento ligado na conciliação, FK para `lancamentos.id`). Um
  índice único parcial em `conciliado_com` garante no máximo um item por lançamento;
  `ordem` só mantém a ordem de importação na mesma data. A leitura do CSV e as regras
  (1 MB, erro com o número da linha, repetidos por multiconjunto) ficam em
  `Financeiro/extrato.py` e valem para a memória e o banco. Duas importações ao mesmo
  tempo esperam uma pela outra (trava até o fim da transação).
- Conciliar com o `id` de um item do extrato lê o item com `SELECT ... FOR UPDATE` e
  liga os dois lados **na mesma transação** do lançamento: se a ligação falha, o
  lançamento não fica conciliado. Item já ligado a outro lançamento responde 400.

## Como o código está organizado

- `Backend/Shared/banco.py` — a conexão com o banco, uma só para Gestão, Financeiro e
  login único (um pool por processo). `Gestao/banco.py` reexporta daqui, com os mesmos
  nomes de antes, e o login (`Backend/Acesso/`) usa o mesmo pool.
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

## Produção

**Situação:** a head agora é a `e4b8c1d7f2a9` (extrato bancário), que vem depois da
`e4a6c8b0d2f1` (coordenação só na conta, T-87) e só **cria** a tabela `extrato_itens` e
seus índices: o código anterior continua funcionando com ela, então pode ser aplicada
antes do deploy (`alembic upgrade head`, que também aplica a `e4a6c8b0d2f1` se a
produção ainda não estiver nela). Rollback: `alembic downgrade e4a6c8b0d2f1` (apaga os
itens do extrato importados; os lançamentos, inclusive a referência `item_extrato_ref`,
ficam).

A migration `c2d8e4f6a1b3` vem **depois** da `6bd565cae094` (alertas da Gestão, T-59) e
só **adiciona**:

- em `lancamentos`: `criado_em`, `aprovado_em`, `rejeitado_em`, `conciliado_em`,
  `motivos_rejeicao_anteriores` e `comprovante_chave` (preenchida a partir de
  `comprovante_url` nas linhas que já existem);
- as tabelas `notificacoes` e `rascunhos_lancamento`.

Ela foi aplicada na produção em 10/11/2026, antes do merge, porque o código novo precisa
dessas colunas e o código anterior funciona com elas. O login (T-35) criou outra linha de
migrations a partir da `6bd565cae094` (`b7d4e2a9c1f0`); a `d9f1a7c3b5e2` junta as duas,
sem operações. O histórico completo está em [login.md](login.md#estado-da-produção-10112026).

Para conferir:

```bash
cd Backend/Shared
# DATABASE_URL da produção no ambiente ou em Backend/.env
alembic current        # depois do upgrade: e4b8c1d7f2a9 (head)
```

Os dados que estavam em memória no Cloud Run não são migrados (não há de onde lê-los).
Orçamentos e lançamentos de demonstração precisam ser cadastrados de novo.

Rollback, mantendo o login: `alembic downgrade b7d4e2a9c1f0` (desfaz a junção) e depois
`alembic downgrade c2d8e4f6a1b3@-1` (remove só o que a `c2d8e4f6a1b3` criou e apaga as
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
| `Shared/tests/test_migration_extrato_itens.py` | `extrato_itens`: colunas, FK, um item por lançamento, downgrade | Postgres |
| `Financeiro/tests/test_extrato.py` | importação, listagem, conciliação com item e auditoria, cada teste na memória **e** no banco; importações e conciliações simultâneas | memória e Postgres |
| `Gestao/tests/test_gestao_visao_integrada*.py` | a Visão integrada lendo o Financeiro do banco, só pelo id | Postgres |
| `Financeiro/tests/test_acesso_por_papel.py` | T-36: papel vindo do login, educador restrito ao vínculo, Coordenação vê tudo, voluntário não aprova | Postgres |
| `Financeiro/tests/test_auditoria_financeiro.py` | T-34: cada ação na trilha, mesma transação, acesso negado, quem lê a trilha | Postgres |

Os testes de banco usam um PostgreSQL descartável em `TEST_DATABASE_URL`. Sem ele são
pulados localmente; no CI a falta do banco é erro. Os jobs `backend-financeiro`,
`backend-gestao` e `backend-infra` sobem um Postgres próprio.

`MDCA_SEMENTES_PARIDADE=300` roda 300 cenários de paridade em vez dos 8 do CI.
