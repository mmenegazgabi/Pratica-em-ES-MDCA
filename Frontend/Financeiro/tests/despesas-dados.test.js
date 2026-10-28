// Redesign Financeiro · celular — como a tela "Minhas despesas" agrupa os dados.

import { test } from "node:test";
import assert from "node:assert/strict";

import { agruparDespesas, nomeDoProjeto, quandoFoiTirada, rotuloDoStatus, ultimoProjetoUsado } from "../lancamento/despesas-dados.js";

function lancamento(id, status, criado_em, extra = {}) {
  return { id, status, criado_em, orcamento_id: `orc-${id}`, valor: 10, ...extra };
}

test("rejeitadas vão para ajuste, rascunhos para a completar, o resto para enviadas", () => {
  const lancamentos = [
    lancamento("a", "pendente", "2026-10-20T10:00:00Z"),
    lancamento("b", "rejeitado", "2026-10-21T10:00:00Z"),
    lancamento("c", "aprovado", "2026-10-22T10:00:00Z"),
  ];
  const rascunhos = [{ id: "r2" }, { id: "r1" }];

  const grupos = agruparDespesas(lancamentos, rascunhos);

  assert.deepEqual(grupos.ajuste.map((l) => l.id), ["b"]);
  assert.deepEqual(grupos.aCompletar.map((r) => r.id), ["r2", "r1"]);
  assert.deepEqual(grupos.enviadas.map((l) => l.id), ["c", "a"]);
});

test("enviadas mostra no máximo 5, mais recentes primeiro", () => {
  // A API devolve dos mais antigos para os mais novos.
  const lancamentos = [1, 2, 3, 4, 5, 6, 7].map((n) => lancamento(`l${n}`, "pendente", `2026-10-0${n}T10:00:00Z`));

  const { enviadas } = agruparDespesas(lancamentos, []);

  assert.deepEqual(enviadas.map((l) => l.id), ["l7", "l6", "l5", "l4", "l3"]);
});

test("'Ver todas' pede todas as enviadas, sem limite", () => {
  const lancamentos = [1, 2, 3, 4, 5, 6, 7].map((n) => lancamento(`l${n}`, "aprovado", `2026-10-0${n}T10:00:00Z`));
  assert.equal(agruparDespesas(lancamentos, [], { limiteEnviadas: Infinity }).enviadas.length, 7);
});

test("ultimoProjetoUsado pega o orçamento da despesa mais recente; lista vazia → null", () => {
  const lancamentos = [
    lancamento("a", "aprovado", "2026-10-20T10:00:00Z", { orcamento_id: "orc-leitura" }),
    lancamento("b", "pendente", "2026-10-25T10:00:00Z", { orcamento_id: "orc-esporte" }),
    lancamento("c", "rejeitado", "2026-10-22T10:00:00Z", { orcamento_id: "orc-arte" }),
  ];
  assert.equal(ultimoProjetoUsado(lancamentos), "orc-esporte");
  assert.equal(ultimoProjetoUsado([]), null);
});

test("status aparece no tom do educador", () => {
  assert.deepEqual(rotuloDoStatus("pendente"), { texto: "Em análise", classe: "etiqueta--pendente" });
  assert.deepEqual(rotuloDoStatus("aprovado"), { texto: "Aprovada", classe: "etiqueta--aprovado" });
  assert.deepEqual(rotuloDoStatus("rejeitado"), { texto: "Rejeitada", classe: "etiqueta--rejeitado" });
});

test("nome do projeto vem do orçamento; sem nome, usa o projeto_id", () => {
  const orcamentos = [
    { id: "o1", projeto_id: "p1", projeto_nome: "Leitura" },
    { id: "o2", projeto_id: "p2", projeto_nome: null },
  ];
  assert.equal(nomeDoProjeto("o1", orcamentos), "Leitura");
  assert.equal(nomeDoProjeto("o2", orcamentos), "p2");
  assert.equal(nomeDoProjeto("o3", orcamentos, "p3"), "p3");
});

test("horário da foto: 'Hoje, 10:42' no dia, senão a data curta", () => {
  const agora = new Date(2026, 9, 27, 15, 0);
  assert.equal(quandoFoiTirada(new Date(2026, 9, 27, 10, 42).toISOString(), agora), "Hoje, 10:42");
  assert.equal(quandoFoiTirada(new Date(2026, 9, 26, 9, 5).toISOString(), agora), "26/10, 09:05");
});
