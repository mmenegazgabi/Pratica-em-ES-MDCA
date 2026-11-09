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
const RESPOSTAS = [
  [/\/equipe(\?|$)/, [{ id: "v-1", usuario_id: "ana", nome: "Ana Martins", papel_id: "coordenacao", papel: "Coordenação", data_entrada: "2025-01-10", data_saida: null, ativo: true }]],
  [/\/espacos$/, []],
  [/\/gestao\/usuarios$/, [{ id: "ana", nome: "Ana Martins", email: null, ativo: true, papeis: [], vinculos: [] }]],
  [/\/gestao\/programas$/, [{ id: "p-1", nome: "Semear" }]],
  [/\/gestao\/pessoas$/, [{ id: "pe-lara", nome: "Lara Oliveira", data_nascimento: "2013-05-12", programa_id: "p-1", programa: "Semear", nucleo_familiar: { id: "f-1", nome: "Oliveira" }, responsaveis: [], situacao: "ativo", autorizacao_imagem: "vigente" }]],
];
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  const corpo = RESPOSTAS.find(([padrao]) => padrao.test(url))?.[1] ?? [];
  return new Response(JSON.stringify(corpo), { status: 200 });
};
localStorage.setItem("mdca.financeiro.token", "token-de-teste");
localStorage.setItem("mdca.gestao.usuario", "ana");

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

test("Equipe e espaços de um programa do cadastro carrega pela API, com o usuário salvo", async () => {
  chamadas.length = 0;
  await irPara("#/programas/p-1/equipe");

  const urls = chamadas.map((c) => c.url.replace(/^https?:\/\/[^/]+/, ""));
  assert.ok(urls.includes("/gestao/programas/p-1/equipe?incluir_desligados=true"));
  assert.ok(urls.includes("/gestao/programas/p-1/espacos"));
  assert.ok(chamadas.every((c) => c.headers["X-Usuario-Id"] === "ana"));
  assert.equal($("#tela-api tbody strong").textContent, "Ana Martins");
  assert.equal($("#main .subtitle").textContent, "Semear");
  assert.equal($(".demo-banner"), null);
});

test("o menu do usuário mostra o usuário usado na API", () => {
  assert.match($(".api-user").textContent, /Usuário na API: ana/);
});

test("detalhe de programa continua na demonstração", async () => {
  await irPara("#/programas/p1");

  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("Pessoas e famílias carrega pela API; pessoas fictícias do protótipo seguem na demonstração", async () => {
  chamadas.length = 0;
  await irPara("#/pessoas");

  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/pessoas")));
  assert.equal($("#tela-api tbody a").textContent, "Lara Oliveira");
  assert.equal($(".demo-banner"), null);

  await irPara("#/pessoas/u1");
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

test("Usuários e acessos fica restrito fora da administração, sem chamar a API", async () => {
  chamadas.length = 0;
  await irPara("#/usuarios");

  assert.equal($("#main h1").textContent, "Acesso restrito");
  assert.equal(chamadas.length, 0);
});

test("na administração, Usuários e acessos carrega pela API, sem o aviso de demonstração", async () => {
  await irPara("#/inicio");
  $('[data-action="persona:admin"]').click();
  await esperar();
  chamadas.length = 0;
  await irPara("#/usuarios");

  assert.equal(chamadas.at(-1).url.endsWith("/gestao/usuarios"), true);
  assert.equal($("#tela-api tbody strong").textContent, "Ana Martins");
  assert.equal($(".demo-banner"), null);
});
