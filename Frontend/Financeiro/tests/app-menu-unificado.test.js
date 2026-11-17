// Menu único no Financeiro: a coordenação vê as abas da Gestão junto com as do
// Financeiro; o voluntário financeiro, que só tem o Financeiro, continua com o menu dele.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { sessaoDeTeste } from "./ajuda-sessao.js";

const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: "http://localhost/Financeiro/#/projetos" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  localStorage: dom.window.localStorage,
  sessionStorage: dom.window.sessionStorage,
});
const { iniciar } = await import("../app.js");
globalThis.fetch = async () => {
  throw new TypeError("Failed to fetch");
};

const esperar = () => new Promise((r) => setTimeout(r, 30));
const itens = (raiz) => [...raiz.querySelectorAll(".lateral__item")];
const rotulos = (raiz) => itens(raiz).map((a) => a.textContent.replace(/\d+$/, ""));

async function abrir() {
  const raiz = document.createElement("div");
  document.body.replaceChildren(raiz);
  iniciar(raiz, { redirecionar: () => {} });
  await esperar();
  return raiz;
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

test("coordenação vê as abas da Gestão e do Financeiro numa lista só", async () => {
  sessaoDeTeste({ papeis: ["coordenacao"] });
  const raiz = await abrir();
  const lista = rotulos(raiz);
  assert.equal(lista[0], "Visão geral");
  assert.ok(lista.includes("Resumo financeiro"));
  assert.ok(lista.includes("Auditoria da gestão"));
  assert.equal(itens(raiz).find((a) => a.textContent === "Visão geral").getAttribute("href"), "../Gestao/#/inicio");
  assert.deepEqual(
    itens(raiz).filter((a) => a.getAttribute("aria-current") === "page").map((a) => a.textContent),
    ["Projetos"],
  );
});

test("com o menu único a barra lateral usa a largura da Gestão, para não pular ao trocar de módulo", async () => {
  sessaoDeTeste({ papeis: ["coordenacao"] });
  const raiz = await abrir();
  assert.ok(raiz.querySelector(".lateral").classList.contains("lateral--unica"));
});

test("o papel em uso no Financeiro vale na Gestão", async () => {
  sessaoDeTeste({ papeis: ["coordenacao", "direcao"], papel: "direcao" });
  await abrir();
  assert.equal(localStorage.getItem("mdca.gestao.papel"), "director");
});

test("voluntário financeiro continua só com o menu do Financeiro", async () => {
  sessaoDeTeste({ papeis: ["voluntario_financeiro"] });
  const raiz = await abrir();
  assert.deepEqual(rotulos(raiz), ["Início", "Lançamentos", "Conciliação"]);
  assert.ok(!raiz.querySelector(".lateral").classList.contains("lateral--unica"));
  assert.equal(localStorage.getItem("mdca.gestao.papel"), null);
});

test("embaixo do logo não aparece mais o nome do módulo", async () => {
  sessaoDeTeste({ papeis: ["coordenacao"] });
  const raiz = await abrir();
  assert.equal(raiz.querySelector(".lateral__marca span"), null);
  assert.ok(raiz.querySelector(".lateral__marca svg.logo"));
});
