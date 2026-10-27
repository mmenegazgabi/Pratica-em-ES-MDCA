// Lançamentos: contagens, saldo após aprovar e validação do motivo (sem DOM).
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import { contarPorStatus, saldoAposAprovar, validarMotivo, ordenarParaAba } from "../telas/lancamentos-dados.js";

describe("contarPorStatus", () => {
  test("conta cada status e o total", () => {
    const lista = [{ status: "pendente" }, { status: "pendente" }, { status: "aprovado" }, { status: "rejeitado" }, { status: "aprovado" }, { status: "aprovado" }];
    assert.deepEqual(contarPorStatus(lista), { pendente: 2, aprovado: 3, rejeitado: 1, todos: 6 });
  });
  test("lista vazia", () => {
    assert.deepEqual(contarPorStatus([]), { pendente: 0, aprovado: 0, rejeitado: 0, todos: 0 });
  });
});

describe("saldoAposAprovar", () => {
  test("desconta o valor do saldo", () => {
    assert.equal(saldoAposAprovar({ saldo: 1000 }, { valor: 180 }), 820);
  });
  test("sem erro de ponto flutuante", () => {
    assert.equal(saldoAposAprovar({ saldo: 0.3 }, { valor: 0.1 }), 0.2);
  });
  test("pode ficar negativo", () => {
    assert.equal(saldoAposAprovar({ saldo: 50 }, { valor: 80 }), -30);
  });
});

describe("validarMotivo", () => {
  test("vazio e só espaços", () => {
    assert.equal(validarMotivo(""), "Informe o motivo da rejeição.");
    assert.equal(validarMotivo("   \n "), "Informe o motivo da rejeição.");
    assert.equal(validarMotivo(undefined), "Informe o motivo da rejeição.");
  });
  test("501 caracteres", () => {
    assert.equal(validarMotivo("a".repeat(501)), "Use no máximo 500 caracteres.");
  });
  test("500 caracteres e texto comum são aceitos", () => {
    assert.equal(validarMotivo("a".repeat(500)), null);
    assert.equal(validarMotivo("Foto ilegível"), null);
  });
});

describe("ordenarParaAba", () => {
  const l = [
    { id: "a", criado_em: "2026-10-01T10:00:00Z" },
    { id: "b", criado_em: "2026-10-03T10:00:00Z" },
    { id: "c", criado_em: "2026-10-02T10:00:00Z" },
  ];
  test("aguardando: mais antigas primeiro", () => {
    assert.deepEqual(ordenarParaAba(l, "pendente").map((x) => x.id), ["a", "c", "b"]);
  });
  test("demais abas: mais novas primeiro, sem alterar a entrada", () => {
    assert.deepEqual(ordenarParaAba(l, "aprovado").map((x) => x.id), ["b", "c", "a"]);
    assert.equal(l[0].id, "a");
  });
});
