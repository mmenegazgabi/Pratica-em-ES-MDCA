// Contador do Início preenchido mesmo quando a primeira tela aberta é outra (jsdom).
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="app-teste"></div></body>', { url: "http://localhost/Financeiro/#/projetos" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });

const PENDENTES = [
  { id: "l1", orcamento_id: "o1", projeto_id: "p1", valor: 10, categoria: "Materiais", status: "pendente", autor_id: "ana", criado_em: "2026-10-26T10:00:00Z" },
  { id: "l2", orcamento_id: "o1", projeto_id: "p1", valor: 20, categoria: "Transporte", status: "pendente", autor_id: "ana", criado_em: "2026-10-27T10:00:00Z" },
];

globalThis.fetch = async (url) => {
  const caminho = new URL(url).pathname;
  const corpo = caminho === "/lancamentos" ? PENDENTES : [];
  return { status: 200, json: async () => corpo };
};

const { sessaoDeTeste } = await import("./ajuda-sessao.js");
sessaoDeTeste({ papeis: ["coordenacao"], nome: "Luana Ferraz" });
const { iniciar } = await import("../app.js");

test("abrindo direto em Projetos, o contador do Início mostra as pendências", async () => {
  const raiz = document.getElementById("app-teste");
  iniciar(raiz, { redirecionar: () => {} });
  await new Promise((r) => setTimeout(r, 50));
  const selo = raiz.querySelector("[data-contador]");
  assert.equal(selo.hidden, false);
  assert.equal(selo.textContent, "2");
});
