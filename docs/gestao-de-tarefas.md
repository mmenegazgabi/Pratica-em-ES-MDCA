# Gestão de tarefas — GitHub Projects

O board **"Backlog — Módulo Financeiro MDCA"** no GitHub Projects é a fonte única
de verdade sobre o andamento das tarefas. Ele espelha os épicos do backlog
(Sprint 0, Orçamento, Lançamentos, Relatórios, Acesso e Auditoria).

## Visualização em board

Um projeto criado pela CLI abre como **tabela**. Para ver as colunas: **New view → Board**,
com **Column by: Status**. Renomeie essa visualização para "Board" e deixe-a como a primeira aba.

## Colunas (campo Status)

| Coluna | Quando usar |
|---|---|
| Backlog | Tarefa ainda não iniciada |
| Em andamento | Alguém pegou a tarefa (issue com responsável) |
| Em revisão | PR aberto, aguardando revisão |
| Concluído | PR com merge ou issue fechada |

## Labels

Cada user story tem sua label. Toda issue de tarefa deve ter **uma label de US**
e **uma label de domínio**.

| Label | User story |
|---|---|
| `US-01` | Cadastro de orçamento do projeto |
| `US-02` | Acompanhamento de saldo com alertas (80% / 100%) |
| `US-03` | Registro de lançamento com comprovante |
| `US-04` | Aprovação/rejeição de lançamentos |
| `US-05` | Conciliação com o extrato |
| `US-06` | Relatório de prestação de contas (PDF/XLSX) |
| `US-07` | Dashboard executivo |
| `US-08` | Controle de acesso e auditoria |
| `sprint-0` | Setup do projeto |
| `financeiro` / `gestao` | Domínio dono da tarefa (tarefas compartilhadas levam as duas) |

## Automações (Workflows do board)

Em **Project → ⋯ → Workflows**, deixar ativos:

- **Auto-add to project** — repositório `Pratica-em-ES-MDCA`, filtro `is:issue,pr is:open`
  → Status **Backlog**. Toda issue nova entra no board sozinha.
- **Item reopened** → Status **Em andamento**
- **Pull request linked to issue** → Status **Em revisão**
- **Item closed** → Status **Concluído**
- **Pull request merged** → Status **Concluído**

## Convenções

- Título da issue: `T-XX · [US-YY] descrição` (igual ao card do backlog).
- No PR, usar `Closes #<nº da issue>` para a issue fechar e ir para Concluído no merge.
- Ao começar uma tarefa: atribua-se na issue e mova-a para **Em andamento**.
