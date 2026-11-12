# Relatório de prestação de contas (T-28 · US-06)

Estrutura do relatório de prestação de contas que a Coordenação gera para
financiadores e conselho, em **PDF** ou **planilha (XLSX)**. Este documento é a
referência para quem for implementar ou alterar o gerador: cada campo do
relatório aponta para a tabela e a coluna de onde vem.

As tabelas citadas são as das migrations em `Backend/Shared/migrations/versions/`.
A API do Financeiro lê essas tabelas por `Backend/Financeiro/persistencia.py`
(veja `docs/persistencia-financeiro.md`).

## Parâmetros de geração

O relatório é pedido na tela **Relatórios** (tela 6 do
[redesign do Financeiro](superpowers/specs/2026-10-27-redesign-financeiro-design.md)).
Esses valores vêm da tela, não do banco:

| Parâmetro | Exemplo | Uso |
|---|---|---|
| Projeto | `Esporte` | Escolhe o projeto (`projetos.id`) |
| Período (início e fim) | `01/07/2026` a `30/09/2026` | Filtra `lancamentos.data` |
| Formato | `PDF` ou `Planilha` | Define a saída (PDF ou XLSX) |

O orçamento usado é o do projeto cuja vigência (`orcamentos.periodo_inicio` a
`orcamentos.periodo_fim`) contém o período pedido. Um projeto pode ter vários
orçamentos (`lancamentos.orcamento_id`). Se o período pegar mais de um, o
relatório traz uma seção por orçamento.

## Regras de seleção

- Entram **só lançamentos aprovados**: `lancamentos.status = 'aprovado'`.
  Pendentes e rejeitados ficam de fora.
- Um lançamento está **no período** quando `lancamentos.data` está entre o
  início e o fim pedidos, com as duas datas incluídas.
- Valores são `Numeric(14, 2)` no banco e aparecem em reais (`R$ 1.240,00`).
  As somas são feitas em centavos, como em `Backend/Financeiro/moeda.py`, para não
  acumular erro de ponto flutuante.

## Campos do relatório

### 1. Cabeçalho

| Campo | Origem |
|---|---|
| Título ("Prestação de contas — Projeto X") | `projetos.nome` |
| Período do relatório | Parâmetro de geração |
| Vigência do orçamento | `orcamentos.periodo_inicio`, `orcamentos.periodo_fim` |
| Identificador do orçamento | `orcamentos.id` |
| Data de geração | Calculada na hora da geração (não fica salva) |

### 2. Resumo

| Campo | Origem |
|---|---|
| Orçado | `orcamentos.valor_total` |
| Executado no período | `SUM(lancamentos.valor)` dos aprovados do orçamento com `data` dentro do período |
| Executado acumulado | `SUM(lancamentos.valor)` dos aprovados do orçamento com `data` até o fim do período |
| Saldo | `orcamentos.valor_total` − executado acumulado |
| % usado | executado acumulado ÷ `orcamentos.valor_total` (mesmos limites de 80% / 100% de `alerta_saldo.py`) |

O saldo considera tudo o que já foi gasto no orçamento, inclusive antes do
período. Por isso, em geral, Orçado − Executado no período ≠ Saldo.

### 3. Execução por categoria

Uma linha por categoria do orçamento.

| Campo | Origem |
|---|---|
| Categoria | `orcamento_categorias.nome` (lista em `orcamentos.categorias`) |
| Orçado na categoria | `orcamento_categorias.valor_orcado`; "Sem limite" quando a categoria não tem linha em `orcamento_categorias` |
| Executado no período | `SUM(lancamentos.valor)` dos aprovados com `lancamentos.categoria` = categoria, dentro do período |
| Executado acumulado | Mesma soma, com `data` até o fim do período |
| Saldo da categoria | `valor_orcado` − executado acumulado (vazio quando não há limite) |

### 4. Lançamentos do período

Uma linha por lançamento aprovado no período, ordenada por `data` (e por
`id` para desempatar).

| Coluna | Origem |
|---|---|
| Data | `lancamentos.data` |
| Categoria | `lancamentos.categoria` |
| Descrição | `lancamentos.descricao` |
| Valor | `lancamentos.valor` |
| Comprovante | "Sim" quando `lancamentos.comprovante_url` está preenchido, senão "Não" |
| Conciliado | `lancamentos.conciliado` ("Sim" / "Não") |
| Ref. do extrato | `lancamentos.item_extrato_ref` (vazio se não conciliado) |

A URL do comprovante **não** vai no relatório: ela só abre pela API com
autenticação (ver [armazenamento-comprovantes.md](armazenamento-comprovantes.md)),
então não serve para quem recebe o arquivo.

### 5. Aviso de conciliação

| Campo | Origem |
|---|---|
| Lançamentos não conciliados no período | `COUNT(*)` dos aprovados no período com `lancamentos.conciliado = false` |

O mesmo aviso aparece na tela antes de gerar e no rodapé do relatório.

### Campos que não entram

| Coluna | Motivo |
|---|---|
| `lancamentos.autor_id` | Dado pessoal de quem lançou; não interessa ao financiador |
| `lancamentos.motivo_rejeicao` | Rejeitados não entram no relatório |
| `lancamentos.status` | Sempre `aprovado` no relatório |
| `lancamentos.comprovante_url` | Só vira "Sim"/"Não" (ver acima) |

## Formatos de saída

**PDF:** uma página A4 com as seções na ordem acima: cabeçalho, três números
do resumo (Orçado, Executado no período, Saldo), tabela por categoria, tabela de
lançamentos e aviso de conciliação no rodapé.

**Planilha (XLSX):** uma aba por seção, para quem precisa refazer contas:

| Aba | Conteúdo |
|---|---|
| `Resumo` | Cabeçalho e resumo, um campo por linha (rótulo na coluna A, valor na B) |
| `Categorias` | Tabela da seção 3 |
| `Lançamentos` | Tabela da seção 4 |

Na planilha, valores ficam como número com formato de moeda (não texto) e datas
como data, para que somas e filtros funcionem.

## Exemplo (dados fictícios)

Projeto **Esporte**, orçamento com vigência de 01/01/2026 a 31/12/2026,
relatório de 01/07/2026 a 30/09/2026. Antes de julho já tinham sido gastos
R$ 5.290,00.

### Cabeçalho e resumo

```
Prestação de contas — Projeto Esporte                                  MDCA
Período: 01/07/2026 a 30/09/2026 · Vigência do orçamento: 01/01/2026 a 31/12/2026
Gerado em 03/11/2026

Orçado            Executado no período    Saldo
R$ 10.000,00      R$ 3.210,00             R$ 1.500,00   (85% usado)
```

### Execução por categoria

| Categoria | Orçado | Executado no período | Executado acumulado | Saldo |
|---|---:|---:|---:|---:|
| Uniformes | R$ 3.000,00 | R$ 1.240,00 | R$ 2.840,00 | R$ 160,00 |
| Alimentação | R$ 2.500,00 | R$ 860,00 | R$ 2.300,00 | R$ 200,00 |
| Transporte | R$ 2.500,00 | R$ 650,00 | R$ 1.850,00 | R$ 650,00 |
| Materiais | R$ 2.000,00 | R$ 460,00 | R$ 1.510,00 | R$ 490,00 |
| **Total** | **R$ 10.000,00** | **R$ 3.210,00** | **R$ 8.500,00** | **R$ 1.500,00** |

### Lançamentos do período

| Data | Categoria | Descrição | Valor | Comprovante | Conciliado | Ref. do extrato |
|---|---|---|---:|---|---|---|
| 03/07/2026 | Uniformes | Camisetas do time sub-12 | R$ 1.240,00 | Sim | Sim | EXT-2026-07-014 |
| 15/08/2026 | Alimentação | Lanches dos treinos de agosto | R$ 860,00 | Sim | Sim | EXT-2026-08-031 |
| 02/09/2026 | Transporte | Van para o torneio regional | R$ 650,00 | Sim | Não | |
| 20/09/2026 | Materiais | Bolas e coletes | R$ 460,00 | Não | Não | |

> **Atenção:** 2 lançamentos do período ainda não foram conciliados com o extrato.

### Consulta de referência

Para conferir os números do exemplo direto no banco (PostgreSQL):

```sql
-- Lançamentos do período
SELECT data, categoria, descricao, valor,
       comprovante_url IS NOT NULL AS tem_comprovante,
       conciliado, item_extrato_ref
FROM lancamentos
WHERE orcamento_id = :orcamento_id
  AND status = 'aprovado'
  AND data BETWEEN :inicio AND :fim
ORDER BY data, id;

-- Executado por categoria (no período e acumulado)
SELECT c.nome,
       c.valor_orcado,
       COALESCE(SUM(l.valor) FILTER (WHERE l.data BETWEEN :inicio AND :fim), 0) AS executado_periodo,
       COALESCE(SUM(l.valor) FILTER (WHERE l.data <= :fim), 0)                  AS executado_acumulado
FROM orcamento_categorias c
LEFT JOIN lancamentos l
       ON l.orcamento_id = c.orcamento_id
      AND l.categoria = c.nome
      AND l.status = 'aprovado'
WHERE c.orcamento_id = :orcamento_id
GROUP BY c.nome, c.valor_orcado
ORDER BY c.nome;
```

## Ao mudar o relatório

- Campo novo ou removido: atualize as tabelas de campos e o exemplo deste
  documento no mesmo PR.
- Coluna nova no banco: crie a migration em `Backend/Shared/migrations/versions/`
  e cite aqui a tabela e a coluna.
