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
  assert.match(container().textContent, /Nenhum projeto cadastrado ainda\./);
  assert.equal(container().querySelector("table"), null);
});

test("falha da API mostra mensagem em vez de quebrar", async () => {
  globalThis.fetch = async () => { throw new Error("offline"); };
  await mostrar(container(), { parametros: {}, sessao: { papel: "coordenacao", nome: "Luana" }, navegar() {} });
  assert.match(container().querySelector("[role=alert]").textContent, /Não foi possível carregar/);
});

test("direção vê orçado, realizado e saldo por projeto do painel (GET /dashboard/projetos)", async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    const u = String(url).replace(/^https?:\/\/[^/]+/, "");
    urls.push(u);
    if (u.startsWith("/dashboard/projetos"))
      return resposta(200, [
        { projeto_id: "p2", nome: "Horta <i>", status: "encerrado", orcado: 500, realizado: 500, saldo: 0 },
        { projeto_id: "p1", nome: "Esporte", status: "ativo", orcado: 10000, realizado: 8500, saldo: 1500 },
      ]);
    return resposta(200, []);
  };
  await mostrar(container(), { parametros: {}, sessao: { papel: "direcao", nome: "Jane Almeida" }, navegar() {} });
  assert.ok(urls.includes("/dashboard/projetos"));
  assert.match(container().textContent, /Nada pendente/);
  const linhas = [...container().querySelectorAll("tbody tr")].map((tr) => tr.textContent);
  assert.equal(linhas.length, 3);
  assert.match(linhas[0], /Esporte.*R\$\s10\.000,00.*R\$\s8\.500,00.*R\$\s1\.500,00/);
  assert.match(linhas[1], /Horta <i>.*Encerrado/);
  assert.match(linhas[2], /Total.*R\$\s10\.500,00.*R\$\s9\.000,00.*R\$\s1\.500,00/);
});

test("direção: falha do painel aparece sem esconder as pendências", async () => {
  globalThis.fetch = async (url) =>
    String(url).includes("/dashboard/projetos")
      ? resposta(503, {})
      : resposta(200, [{ id: "o1", projeto_id: "p1", projeto_nome: "Esporte", saldo: 1500, realizado: 8500, percentual_consumido: 85, nivel_alerta: "atencao", data_fim: "2099-12-31" }]);
  await mostrar(container(), { parametros: {}, sessao: { papel: "direcao", nome: "Jane" }, navegar() {} });
  assert.match(container().textContent, /Esporte passou de 80%/);
  assert.match(container().querySelector("[role=alert]").textContent, /Não foi possível carregar o resumo dos projetos/);
});

test("outros papéis não chamam o painel da direção", async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return resposta(200, []);
  };
  await mostrar(container(), { parametros: {}, sessao: { papel: "coordenacao", nome: "Luana" }, navegar() {} });
  await mostrar(container(), { parametros: {}, sessao: { papel: "voluntario_financeiro", nome: "Lucas" }, navegar() {} });
  assert.equal(urls.some((u) => u.includes("/dashboard")), false);
});
