// Menu único: a coordenação vê as abas da Gestão e do Financeiro juntas na barra lateral,
// sem o seletor de módulo; a aba do Financeiro leva direto para ele com o mesmo papel.
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
    usuario: { id: "luana", nome: "Luana Ferraz", email: "luana@mdca.org.br", papeis: [{ id: "coordenacao", nome: "Coordenação" }] },
  }),
);

await import("../app.js");

const itens = () => [...document.querySelectorAll(".lateral__menu .lateral__item")];

test("a barra lateral tem as abas dos dois módulos numa lista só, sem grupos", () => {
  const rotulos = itens().map((a) => a.textContent.replace(/\d+$/, ""));
  assert.ok(rotulos.includes("Visão geral"));
  assert.ok(rotulos.includes("Resumo financeiro"));
  assert.ok(rotulos.includes("Prestação de contas"));
  assert.equal(document.querySelectorAll(".lateral__grupo").length, 0);
});

test("não tem mais o seletor Gestão | Finanças", () => {
  assert.equal(document.querySelector(".lateral__modulos"), null);
});

test("as abas do Financeiro levam ao Financeiro e a aba aberta fica marcada", () => {
  const projetos = itens().find((a) => a.textContent === "Projetos");
  assert.equal(projetos.getAttribute("href"), "../Financeiro/#/projetos");
  assert.deepEqual(
    itens().filter((a) => a.getAttribute("aria-current") === "page").map((a) => a.textContent),
    ["Programas e turmas"],
  );
});

test("o papel em uso na Gestão vale no Financeiro", () => {
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "coordenacao");
});

test("embaixo do logo não aparece mais o nome do módulo", () => {
  assert.equal(document.querySelector(".lateral__marca span"), null);
  assert.ok(document.querySelector(".lateral__marca svg"));
});
