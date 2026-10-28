import test from "node:test";
import assert from "node:assert/strict";
import { gastoPorCategoria, orcamentoDoProjeto, totaisGerais, validarEdicao } from "../telas/projetos-dados.js";

test("totaisGerais soma em centavos", () => {
  const orcamentos = [
    { valor_total: 0.1, realizado: 0.1, saldo: 0 },
    { valor_total: 0.2, realizado: 0.2, saldo: 0 },
  ];
  const pendentes = [{ valor: 0.1 }, { valor: 0.2 }];
  const t = totaisGerais(orcamentos, pendentes);
  assert.equal(t.orcado, 0.3);
  assert.equal(t.gasto, 0.3);
  assert.equal(t.aguardando, 0.3);
  assert.equal(t.disponivel, 0);
});

test("totaisGerais sem dados fica zerado", () => {
  assert.deepEqual(totaisGerais([], []), { orcado: 0, gasto: 0, disponivel: 0, aguardando: 0 });
});

test("gastoPorCategoria lista todas as categorias e só conta aprovados", () => {
  const o = { id: "o1", categorias_despesa: ["Uniformes", "Transporte", "Materiais"] };
  const l = [
    { orcamento_id: "o1", categoria: "Uniformes", valor: 10.1, status: "aprovado" },
    { orcamento_id: "o1", categoria: "Uniformes", valor: 0.2, status: "aprovado" },
    { orcamento_id: "o1", categoria: "Transporte", valor: 50, status: "pendente" },
    { orcamento_id: "o1", categoria: "Materiais", valor: 70, status: "rejeitado" },
    { orcamento_id: "o2", categoria: "Materiais", valor: 90, status: "aprovado" },
  ];
  assert.deepEqual(gastoPorCategoria(o, l), [
    { categoria: "Uniformes", gasto: 10.3 },
    { categoria: "Transporte", gasto: 0 },
    { categoria: "Materiais", gasto: 0 },
  ]);
});

test("validarEdicao aceita dados corretos", () => {
  assert.deepEqual(validarEdicao({ valor_total: 100, data_inicio: "2026-01-01", data_fim: "2026-12-31", categorias: ["A"] }), {});
});

test("validarEdicao aponta cada campo", () => {
  const e = validarEdicao({ valor_total: 0, data_inicio: "2026-12-31", data_fim: "2026-01-01", categorias: [] });
  assert.ok(e.valor_total);
  assert.ok(e.data_fim);
  assert.ok(e.categorias);
  const f = validarEdicao({ valor_total: "", data_inicio: "", data_fim: "", categorias: ["A"] });
  assert.ok(f.valor_total && f.data_inicio && f.data_fim);
});

test("orcamentoDoProjeto prefere o vigente hoje, senão o mais recente", () => {
  const a = { id: "a", projeto_id: "p", data_inicio: "2025-01-01", data_fim: "2025-12-31" };
  const b = { id: "b", projeto_id: "p", data_inicio: "2026-01-01", data_fim: "2026-12-31" };
  const c = { id: "c", projeto_id: "p", data_inicio: "2027-01-01", data_fim: "2027-12-31" };
  const outro = { id: "x", projeto_id: "q", data_inicio: "2026-01-01", data_fim: "2026-12-31" };
  assert.equal(orcamentoDoProjeto("p", [a, c, b, outro], "2026-10-27").id, "b");
  assert.equal(orcamentoDoProjeto("p", [a, c], "2026-10-27").id, "c");
  assert.equal(orcamentoDoProjeto("z", [a], "2026-10-27"), null);
});
