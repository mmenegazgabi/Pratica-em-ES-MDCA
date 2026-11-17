// Quem só tem papel na Gestão (psicólogo) continua com o menu da Gestão, em grupos,
// e sem o seletor de módulo (ele não teria para onde ir).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");
const dom = new JSDOM(html, { url: "http://localhost/Gestao/#/turmas", virtualConsole: new VirtualConsole() });
const { window } = dom;
Object.assign(globalThis, {
  window,
  document: window.document,
  location: window.location,
  localStorage: window.localStorage,
  sessionStorage: window.sessionStorage,
  DOMParser: window.DOMParser,
});
globalThis.fetch = async () => new Response("[]", { status: 200 });

const amanha = new Date(Date.now() + 86400000).toISOString();
localStorage.setItem(
  "mdca.sessao",
  JSON.stringify({
    token: "token-da-sessao",
    expira_em: amanha,
    usuario: { id: "rafael", nome: "Rafael Nunes", email: "rafael@mdca.org.br", papeis: [{ id: "psicologo", nome: "Psicólogo" }] },
  }),
);

await import("../app.js");

test("o menu continua em grupos e sem abas do Financeiro", () => {
  assert.ok(document.querySelectorAll(".lateral__grupo").length > 0);
  assert.equal(document.querySelector('.lateral__menu a[href*="Financeiro"]'), null);
});

test("não tem o seletor Gestão | Finanças", () => {
  assert.equal(document.querySelector(".lateral__modulos"), null);
});

test("não grava papel do Financeiro", () => {
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);
});
