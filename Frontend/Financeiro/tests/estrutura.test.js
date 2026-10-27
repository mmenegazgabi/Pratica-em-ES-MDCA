// Estrutura do computador: menu por papel, tela Entrar e tela ausente (jsdom).
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="app"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { iniciar, definirContador } = await import("../app.js");
const { salvarAcesso } = await import("../base/api.js");

const raiz = document.getElementById("app");
const esperar = () => new Promise((r) => setTimeout(r, 20));
const redirecionamentos = [];
iniciar(raiz, { redirecionar: (d) => redirecionamentos.push(d) });
await esperar();

function entrarComo(papel, nome = "Luana Ferraz") {
  localStorage.setItem("mdca.financeiro.sessao", JSON.stringify({ papel, nome }));
  salvarAcesso("token-de-teste");
}
async function irPara(hash) {
  window.location.hash = hash;
  await esperar();
}
const rotulos = () => [...raiz.querySelectorAll(".lateral__item")].map((a) => a.textContent.replace(/\d+$/, ""));

test("sem sessão mostra Entrar com os três papéis do computador", () => {
  assert.equal(window.location.hash, "#/entrar");
  const opcoes = [...raiz.querySelectorAll("#campo-papel option")].map((o) => o.value);
  assert.deepEqual(opcoes, ["coordenacao", "direcao", "voluntario_financeiro"]);
  assert.ok(raiz.querySelector("#campo-token"));
});

test("Entrar sem nome ou código mostra o erro e não cria sessão", async () => {
  raiz.querySelector("#form-entrar").dispatchEvent(new window.Event("submit", { cancelable: true }));
  assert.equal(raiz.querySelector("#erro-acesso").textContent, "Informe seu nome.");
  assert.equal(localStorage.getItem("mdca.financeiro.sessao"), null);
});

test("Entrar preenchido abre o menu do papel e a tela ausente vira aviso", async () => {
  raiz.querySelector("#campo-nome").value = "Jane";
  raiz.querySelector("#campo-papel").value = "direcao";
  raiz.querySelector("#campo-token").value = "abc";
  raiz.querySelector("#form-entrar").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.deepEqual(rotulos(), ["Início", "Projetos"]);
  assert.match(raiz.querySelector(".principal").textContent, /ainda não está disponível/);
  assert.match(raiz.querySelector(".lateral__usuario").textContent, /Jane/);
  assert.match(raiz.querySelector(".lateral__usuario").textContent, /Diretoria/);
});

test("rota fora do menu volta ao Início", async () => {
  await irPara("#/lancamentos");
  assert.equal(window.location.hash, "#/inicio");
  assert.equal(raiz.querySelector('[aria-current="page"]').textContent.replace(/\d+$/, ""), "Início");
});

test("detalhe do projeto marca Projetos como ativo", async () => {
  await irPara("#/projetos/o1");
  assert.equal(raiz.querySelector('[aria-current="page"]').textContent, "Projetos");
});

test("contador aparece no Início e some em zero", async () => {
  await irPara("#/inicio");
  const selo = raiz.querySelector("[data-contador]");
  assert.equal(selo.hidden, true);
  definirContador(4);
  assert.equal(selo.textContent, "4");
  assert.equal(selo.hidden, false);
  definirContador(0);
  assert.equal(selo.hidden, true);
});

test("Trocar perfil volta ao Entrar e esquece o acesso", async () => {
  raiz.querySelector(".lateral__trocar").click();
  await esperar();
  assert.equal(window.location.hash, "#/entrar");
  assert.equal(localStorage.getItem("mdca.financeiro.sessao"), null);
});

test("educador é encaminhado ao app do celular", async () => {
  entrarComo("educador", "Marcos");
  await irPara("#/inicio");
  await irPara("#/projetos");
  assert.ok(redirecionamentos.includes("../lancamento/"));
});
