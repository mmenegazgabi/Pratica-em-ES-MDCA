// Conciliação, Relatórios, Auditoria e categorias com limite: regras sem DOM.
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import { aprovadosEmAberto, diasEmAberto, extratoEmAberto, mesmoValor, valoresDiferentes } from "../telas/conciliacao-dados.js";
import { lancamentosDoPeriodo, montarCsv, resumoDoPeriodo, validarPeriodo } from "../telas/relatorios-dados.js";
import { filtrarAuditoria } from "../telas/auditoria-dados.js";
import { categoriasDoOrcamento } from "../telas/projetos-dados.js";

const AGORA = new Date("2026-10-27T15:00:00Z");

describe("conciliação", () => {
  const extrato = [
    { referencia: "E1", valor: 180, descricao: "PIX PAPELARIA" },
    { referencia: "E2", valor: 0.3, descricao: "TARIFA" },
  ];
  const lancamentos = [
    { id: "a", status: "aprovado", conciliado: false, valor: 180, aprovado_em: "2026-10-26T10:00:00Z" },
    { id: "b", status: "aprovado", conciliado: false, valor: 0.1 + 0.2, aprovado_em: "2026-10-10T10:00:00Z" },
    { id: "c", status: "aprovado", conciliado: true, referencia_extrato: "E9", valor: 50, aprovado_em: "2026-10-01T10:00:00Z" },
    { id: "d", status: "pendente", conciliado: false, valor: 180 },
  ];

  test("extrato em aberto tira as referências já conciliadas", () => {
    assert.deepEqual(extratoEmAberto([...extrato, { referencia: "E9", valor: 50 }], lancamentos).map((i) => i.referencia), ["E1", "E2"]);
  });

  test("aprovados em aberto: só aprovados não conciliados, mais antigos primeiro", () => {
    assert.deepEqual(aprovadosEmAberto(lancamentos).map((l) => l.id), ["b", "a"]);
  });

  test("mesmo valor compara em centavos", () => {
    const abertos = aprovadosEmAberto(lancamentos);
    assert.deepEqual(mesmoValor(extrato[0], abertos), ["a"]);
    assert.deepEqual(mesmoValor(extrato[1], abertos), ["b"]);
    assert.deepEqual(mesmoValor(null, abertos), []);
  });

  test("dias em aberto só aparece depois de 7 dias", () => {
    assert.equal(diasEmAberto(lancamentos[1], AGORA), 17);
    assert.equal(diasEmAberto(lancamentos[0], AGORA), null);
    assert.equal(diasEmAberto({ aprovado_em: null }, AGORA), null);
  });

  test("valores diferentes", () => {
    assert.equal(valoresDiferentes(extrato[0], lancamentos[0]), false);
    assert.equal(valoresDiferentes(extrato[0], lancamentos[1]), true);
  });
});

describe("relatórios", () => {
  const orcamento = { projeto_nome: "Esporte; Base", valor_total: 10000, saldo: 1500 };
  const lancamentos = [
    { status: "aprovado", data_despesa: "2026-09-02", categoria: "Transporte", descricao: "Van", valor: 650, conciliado: true },
    { status: "aprovado", data_despesa: "2026-07-03", categoria: "Uniformes", descricao: 'Camisetas "sub-12"', valor: 1240.1, conciliado: false },
    { status: "pendente", data_despesa: "2026-08-01", categoria: "Lanche", descricao: "x", valor: 10, conciliado: false },
    { status: "aprovado", data_despesa: "2026-10-01", categoria: "Lanche", descricao: "fora", valor: 99, conciliado: false },
  ];

  test("período: só aprovados entre as datas, em ordem", () => {
    const doPeriodo = lancamentosDoPeriodo(lancamentos, "2026-07-01", "2026-09-30");
    assert.deepEqual(doPeriodo.map((l) => l.descricao), ['Camisetas "sub-12"', "Van"]);
    assert.deepEqual(resumoDoPeriodo(orcamento, doPeriodo), { orcado: 10000, executado: 1890.1, saldo: 1500, naoConciliados: 1 });
  });

  test("validar período", () => {
    assert.equal(validarPeriodo("", "2026-01-01"), "Informe o início e o fim do período.");
    assert.equal(validarPeriodo("2026-02-01", "2026-01-01"), "O fim do período não pode ser antes do início.");
    assert.equal(validarPeriodo("2026-01-01", "2026-01-01"), null);
  });

  test("CSV com ponto e vírgula, vírgula decimal e aspas escapadas", () => {
    const csv = montarCsv(orcamento, lancamentosDoPeriodo(lancamentos, "2026-07-01", "2026-09-30"), "2026-07-01", "2026-09-30");
    const linhas = csv.trim().split("\r\n");
    assert.equal(linhas[0], 'Prestação de contas;"Esporte; Base"');
    assert.equal(linhas[3], "Executado no período;1890,10");
    assert.equal(linhas[6], "Data;Categoria;Descrição;Valor;Conciliado");
    assert.equal(linhas[7], '2026-07-03;Uniformes;"Camisetas ""sub-12""";1240,10;não');
  });
});

describe("auditoria", () => {
  test("filtrar auditoria por texto", () => {
    const registros = [{ quem: "Luana", acao: "Aprovou despesa", alvo: "Leitura" }, { quem: "Lucas", acao: "Conciliou", alvo: "EXT-1" }];
    assert.equal(filtrarAuditoria(registros, "  ").length, 2);
    assert.deepEqual(filtrarAuditoria(registros, "concil").map((r) => r.quem), ["Lucas"]);
    assert.deepEqual(filtrarAuditoria(registros, "LEITURA").map((r) => r.quem), ["Luana"]);
  });
});

describe("categorias do orçamento", () => {
  test("com valor por categoria (US-01) usa limite, percentual e alerta do backend", () => {
    const orcamento = {
      categorias_despesa: ["Uniformes", "Lanche"],
      categorias: [
        { nome: "Uniformes", valor_orcado: 4000, realizado: 3840, percentual_consumido: 96, nivel_alerta: "atencao" },
        { nome: "Lanche", valor_orcado: null, realizado: 0, percentual_consumido: null, nivel_alerta: null },
      ],
    };
    assert.deepEqual(categoriasDoOrcamento(orcamento, []), [
      { categoria: "Uniformes", gasto: 3840, limite: 4000, percentual: 96, nivel: "atencao" },
      { categoria: "Lanche", gasto: 0, limite: null, percentual: null, nivel: null },
    ]);
  });

  test("sem categorias detalhadas, cai no gasto dos aprovados", () => {
    const orcamento = { id: "o1", categorias_despesa: ["A"] };
    const lancamentos = [{ orcamento_id: "o1", status: "aprovado", categoria: "A", valor: 10 }];
    assert.deepEqual(categoriasDoOrcamento(orcamento, lancamentos), [{ categoria: "A", gasto: 10, limite: null, percentual: null, nivel: null }]);
  });
});
