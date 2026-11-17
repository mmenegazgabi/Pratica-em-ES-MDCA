// Sem a tela de escolha de módulo, a administração chega à página de Administração
// (cadastro de contas e papéis) pelo item "Usuários e acessos" do menu da Gestão.
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
    usuario: { id: "ana", nome: "Ana Admin", email: "ana@mdca.org.br", papeis: [{ id: "administracao", nome: "Administração" }] },
  }),
);

await import("../app.js");

test("Usuários e acessos leva à página de Administração", () => {
  const item = [...document.querySelectorAll(".lateral__item")].find((a) => a.textContent === "Usuários e acessos");
  assert.equal(item?.getAttribute("href"), "../Admin/");
});
