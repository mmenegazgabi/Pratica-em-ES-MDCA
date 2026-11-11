// Login sem papel na Gestão (ex.: voluntário financeiro): em vez do menu do protótipo,
// uma página curta que leva ao Financeiro, sem chamar a API da Gestão.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");
const dom = new JSDOM(html, { url: "http://localhost/Gestao/#/programas", virtualConsole: new VirtualConsole() });
const { window } = dom;
Object.assign(globalThis, {
  window,
  document: window.document,
  location: window.location,
  localStorage: window.localStorage,
  sessionStorage: window.sessionStorage,
  DOMParser: window.DOMParser,
});
const chamadas = [];
globalThis.fetch = async (url) => {
  chamadas.push(url);
  return new Response("[]", { status: 200 });
};
localStorage.setItem(
  "mdca.sessao",
  JSON.stringify({
    token: "token-da-sessao",
    expira_em: new Date(Date.now() + 86400000).toISOString(),
    usuario: { id: "lucas", nome: "Lucas Prado", email: null, papeis: [{ id: "voluntario_financeiro", nome: "Voluntário(a) financeiro" }] },
  }),
);

await import("../app.js");
const $ = (s) => document.querySelector(s);

test("mostra que o acesso é ao Financeiro, sem menu e sem chamar a Gestão", async () => {
  await new Promise((r) => setTimeout(r, 20));
  assert.equal($("#main h1").textContent, "Seu acesso é ao Financeiro");
  assert.equal($(".sidebar"), null);
  assert.equal($('#main a[href="../Financeiro/"]').textContent, "Ir para o Financeiro");
  assert.ok($('#main [data-action="sair"]'));
  assert.equal(chamadas.filter((u) => String(u).includes("/gestao/")).length, 0);
});
