// Início: a tela montada (jsdom) com a API simulada.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><span data-contador hidden>0</span><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrar, saudacao } = await import("../telas/inicio.js");

const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo, text: async () => JSON.stringify(corpo) });
const container = () => document.getElementById("c");

test("saudação por hora", () => {
  assert.deepEqual([saudacao(8), saudacao(14), saudacao(20)], ["Bom dia", "Boa tarde", "Boa noite"]);
});

test("coordenação vê pendências, ação navega e contador é atualizado", async () => {
  globalThis.fetch = async (url) =>
    String(url).includes("/orcamentos")
      ? resposta(200, [{ id: "o1", projeto_id: "p1", projeto_nome: "Esporte", saldo: 1500, percentual_consumido: 85, nivel_alerta: "atencao", data_fim: "2026-12-31" }])
      : resposta(200, [{ id: "l1", orcamento_id: "o1", projeto_id: "p1", valor: 10, categoria: "Materiais", status: "pendente", conciliado: false, criado_em: new Date().toISOString() }]);
  const destinos = [];
  await mostrar(container(), { parametros: {}, sessao: { papel: "coordenacao", nome: "Luana Ferraz" }, navegar: (h) => destinos.push(h) });
  assert.match(container().querySelector("h1").textContent, /^(Bom dia|Boa tarde|Boa noite), Luana$/);
  assert.match(container().textContent, /2 itens precisam de você/);
  assert.equal(document.querySelector("[data-contador]").textContent, "2");
  container().querySelector("button").click();
  assert.equal(destinos[0], "#/lancamentos?status=pendente&abrir=l1");
});

test("sem pendências mostra 'Nada pendente'", async () => {
  globalThis.fetch = async () => resposta(200, []);
  await mostrar(container(), { parametros: {}, sessao: { papel: "direcao", nome: "Jane Almeida" }, navegar() {} });
  assert.match(container().textContent, /Nada pendente/);
  assert.equal(container().querySelector("table"), null);
});

test("falha da API mostra mensagem em vez de quebrar", async () => {
  globalThis.fetch = async () => { throw new Error("offline"); };
  await mostrar(container(), { parametros: {}, sessao: { papel: "coordenacao", nome: "Luana" }, navegar() {} });
  assert.match(container().querySelector("[role=alert]").textContent, /Não foi possível carregar/);
});
