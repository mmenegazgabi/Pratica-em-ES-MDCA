import test from "node:test";
import assert from "node:assert/strict";
import { lerRota, rotaPermitida } from "../base/rotas.js";

test("vazio e #/ levam ao início", () => {
  assert.deepEqual(lerRota(""), { tela: "inicio", parametros: {} });
  assert.deepEqual(lerRota("#/"), { tela: "inicio", parametros: {} });
  assert.deepEqual(lerRota("#/inicio"), { tela: "inicio", parametros: {} });
});

test("lançamentos lê os filtros da consulta", () => {
  assert.deepEqual(lerRota("#/lancamentos?status=aprovado&orcamento=o1"), {
    tela: "lancamentos",
    parametros: { status: "aprovado", orcamento: "o1" },
  });
});

test("projetos e detalhe do projeto", () => {
  assert.deepEqual(lerRota("#/projetos"), { tela: "projetos", parametros: {} });
  assert.deepEqual(lerRota("#/projetos/o1"), { tela: "projeto", parametros: { id: "o1" } });
  assert.deepEqual(lerRota("#/projetos/a%20b"), { tela: "projeto", parametros: { id: "a b" } });
});

test("entrar e rota desconhecida", () => {
  assert.equal(lerRota("#/entrar").tela, "entrar");
  assert.deepEqual(lerRota("#/qualquer-coisa"), { tela: "inicio", parametros: {} });
});

test("direção não abre lançamentos; coordenação abre o projeto", () => {
  assert.equal(rotaPermitida("lancamentos", "direcao"), false);
  assert.equal(rotaPermitida("projetos", "direcao"), true);
  assert.equal(rotaPermitida("projeto", "direcao"), true);
  assert.equal(rotaPermitida("projeto", "coordenacao"), true);
  assert.equal(rotaPermitida("projeto", "voluntario_financeiro"), false);
  assert.equal(rotaPermitida("lancamentos", "voluntario_financeiro"), true);
  assert.equal(rotaPermitida("inicio", "educador"), false);
  assert.equal(rotaPermitida("entrar", "educador"), true);
});
