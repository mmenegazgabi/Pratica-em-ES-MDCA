// Aplicação inteira no jsdom: menu lateral do protótipo, aviso de demonstração,
// Programas pela API, troca de módulo e menu por perfil.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");
// Console silenciado: o jsdom não implementa window.scrollTo, que o app chama a cada navegação.
const dom = new JSDOM(html, { url: "http://localhost/Gestao/#/inicio", virtualConsole: new VirtualConsole() });
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
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  return new Response(JSON.stringify([{ id: "p-1", nome: "Semear" }]), { status: 200 });
};
localStorage.setItem("mdca.financeiro.token", "token-de-teste");

await import("../app.js");

const $ = (s) => document.querySelector(s);
const esperar = () => new Promise((r) => setTimeout(r, 20));
const menu = () => [...document.querySelectorAll(".sidebar .nav a")].map((a) => a.textContent);
async function irPara(hash) {
  window.location.hash = hash;
  await esperar();
}

test("abre na Visão geral com o menu lateral do protótipo e o aviso de demonstração", () => {
  assert.equal($("#main h1").textContent.startsWith("Bom dia"), true);
  assert.deepEqual(
    [...document.querySelectorAll(".sidebar .nav-label")].map((g) => g.textContent),
    ["Programas e público", "Execução e atendimento", "Resultados", "Auditoria e implantação"],
  );
  assert.ok($(".demo-banner"));
  assert.equal(chamadas.length, 0);
});

test("Programas carrega pela API, sem o aviso de demonstração", async () => {
  await irPara("#/programas");

  assert.equal(chamadas.at(-1).url.endsWith("/gestao/programas"), true);
  assert.equal(chamadas.at(-1).headers.Authorization, "Bearer token-de-teste");
  assert.equal($("#tela-api tbody td").textContent, "Semear");
  assert.equal($(".demo-banner"), null);
  assert.equal($(".sidebar .nav a.active").textContent, "Programas e turmas");
});

test("detalhe de programa continua na demonstração", async () => {
  await irPara("#/programas/p1");

  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("seletor de módulo leva ao Financeiro e o logo ao menu inicial", () => {
  const financas = [...document.querySelectorAll(".seg a")].find((a) => a.textContent === "Finanças");

  assert.equal(financas.getAttribute("href"), "../Financeiro/");
  assert.equal($(".sidebar .brand").getAttribute("href"), "../");
});

test("trocar de perfil muda o menu e fica salvo neste aparelho", async () => {
  await irPara("#/inicio");
  assert.equal(menu().includes("Pessoas e famílias"), true);

  $('[data-action="persona:director"]').click();
  await esperar();

  assert.equal(localStorage.getItem("mdca.gestao.papel"), "director");
  assert.equal(menu().includes("Pessoas e famílias"), false);
  assert.equal(menu().includes("Visão integrada"), true);
});

test("rota fora do perfil mostra acesso restrito", async () => {
  await irPara("#/pessoas");

  assert.equal($("#main h1").textContent, "Acesso restrito");
});
