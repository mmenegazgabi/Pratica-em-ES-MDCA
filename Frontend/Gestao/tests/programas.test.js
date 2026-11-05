// Tela de Programas: estados de carregando, lista, vazio, erro e acesso restrito (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { API_PADRAO, ERROS, ErroApi, urlDaApi } = await import("../base/api.js");
const { mostrarProgramas } = await import("../telas/programas.js");

let container;
const texto = () => container.textContent.replace(/\s+/g, " ").trim();
const enviar = (form) => form.dispatchEvent(new window.Event("submit", { cancelable: true }));
const esperar = () => new Promise((r) => setTimeout(r, 0));

function adiado() {
  let resolver, rejeitar;
  const promessa = new Promise((ok, falha) => ((resolver = ok), (rejeitar = falha)));
  return { promessa, resolver, rejeitar };
}

beforeEach(() => {
  localStorage.clear();
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
});

test("mostra Carregando enquanto a API não responde", async () => {
  const resposta = adiado();
  const pronto = mostrarProgramas(container, { buscar: () => resposta.promessa });

  assert.ok(container.querySelector('[role="status"]'));
  assert.match(texto(), /Carregando/);

  resposta.resolver([]);
  await pronto;
  assert.equal(container.querySelector('[role="status"]'), null);
});

test("lista os programas na ordem da API, com nome e identificador", async () => {
  await mostrarProgramas(container, {
    buscar: async () => [
      { id: "p-2", nome: "Casa de Convivência" },
      { id: "p-1", nome: "Semear" },
    ],
  });

  const linhas = [...container.querySelectorAll("tbody tr")].map((tr) => [...tr.cells].map((c) => c.textContent));
  assert.deepEqual(linhas, [
    ["Casa de Convivência", "p-2", "Equipe e espaços"],
    ["Semear", "p-1", "Equipe e espaços"],
  ]);
});

test("cada programa leva à sua Equipe e espaços, com o id codificado", async () => {
  await mostrarProgramas(container, { buscar: async () => [{ id: "p 1/x", nome: "Semear" }] });

  assert.equal(container.querySelector("tbody a").getAttribute("href"), "#/programas/p%201%2Fx/equipe");
});

test("sem usuário identificado (400) pede o usuário e mantém o código salvo", async () => {
  localStorage.setItem("mdca.financeiro.token", "token-salvo");
  let chamadas = 0;
  const buscar = async () => {
    chamadas += 1;
    if (chamadas === 1) throw new ErroApi(ERROS.SEM_USUARIO, 400, "Identificação do usuário obrigatória.");
    return [];
  };
  await mostrarProgramas(container, { buscar });
  assert.match(texto(), /Informe seu usuário/);

  const form = container.querySelector("form");
  enviar(form);
  assert.equal(chamadas, 1);
  assert.match(container.querySelector('[role="alert"]:not([hidden])').textContent, /Informe seu usuário/);

  container.querySelector("#f-usuario").value = " jessica ";
  enviar(form);
  await esperar();

  assert.equal(chamadas, 2);
  assert.equal(localStorage.getItem("mdca.gestao.usuario"), "jessica");
  assert.equal(localStorage.getItem("mdca.financeiro.token"), "token-salvo");
});

test("nome vindo da API entra como texto, nunca como HTML", async () => {
  await mostrarProgramas(container, { buscar: async () => [{ id: "p-1", nome: '<img src=x onerror="alert(1)">' }] });

  assert.equal(container.querySelector("img"), null);
  assert.equal(container.querySelector("tbody td").textContent, '<img src=x onerror="alert(1)">');
});

test("sem programas mostra o estado vazio", async () => {
  await mostrarProgramas(container, { buscar: async () => [] });

  assert.match(texto(), /Nenhum programa cadastrado/);
  assert.equal(container.querySelector("table"), null);
});

test("sem código de acesso (401) pede o código e carrega depois de informado", async () => {
  let chamadas = 0;
  const buscar = async () => {
    chamadas += 1;
    if (chamadas === 1) throw new ErroApi(ERROS.NAO_AUTENTICADO, 401);
    return [{ id: "p-1", nome: "Semear" }];
  };
  await mostrarProgramas(container, { buscar });
  assert.match(texto(), /Acesso restrito/);

  const form = container.querySelector("form");
  enviar(form);
  assert.equal(chamadas, 1);
  assert.match(container.querySelector('[role="alert"]:not([hidden])').textContent, /Informe o código de acesso/);

  container.querySelector("#f-codigo-acesso").value = "token-de-teste";
  enviar(form);
  await esperar();

  assert.equal(chamadas, 2);
  assert.equal(localStorage.getItem("mdca.financeiro.token"), "token-de-teste");
  assert.equal(container.querySelector("tbody td").textContent, "Semear");
});

test("perfil sem permissão (403) mostra acesso restrito sem pedir código", async () => {
  await mostrarProgramas(container, { buscar: async () => Promise.reject(new ErroApi(ERROS.SEM_PERMISSAO, 403)) });

  assert.match(texto(), /Acesso restrito/);
  assert.match(texto(), /Seu perfil não tem acesso/);
  assert.equal(container.querySelector("form"), null);
});

test("erro do servidor mostra a mensagem e o detalhe, e tenta de novo", async () => {
  let chamadas = 0;
  const buscar = async () => {
    chamadas += 1;
    if (chamadas === 1) throw new ErroApi(ERROS.INDISPONIVEL, 503, "Banco de dados indisponível");
    return [];
  };
  await mostrarProgramas(container, { buscar });

  assert.match(texto(), /Não foi possível carregar/);
  assert.match(texto(), /Banco de dados indisponível/);

  container.querySelector("button").click();
  await esperar();

  assert.equal(chamadas, 2);
  assert.match(texto(), /Nenhum programa cadastrado/);
});

test("rota ainda não publicada (404) não mostra o 'Not Found' do servidor", async () => {
  await mostrarProgramas(container, { buscar: async () => Promise.reject(new ErroApi(ERROS.NAO_ENCONTRADO, 404, "Not Found")) });

  assert.match(texto(), /ainda não está disponível/);
  assert.doesNotMatch(texto(), /Not Found/);
});

test("na tela de erro, o servidor avançado fica fechado quando é o padrão", async () => {
  await mostrarProgramas(container, { buscar: async () => Promise.reject(new ErroApi(ERROS.REDE)) });

  assert.equal(container.querySelector("details").open, false);
  assert.equal(container.querySelector("#f-servidor-api").value, API_PADRAO);
});

test("na tela de erro, dá para voltar do servidor local para a API publicada", async () => {
  localStorage.setItem("mdca.financeiro.api", "http://localhost:8000");
  let chamadas = 0;
  const buscar = async () => {
    chamadas += 1;
    if (chamadas === 1) throw new ErroApi(ERROS.NAO_ENCONTRADO, 404, "Not Found");
    return [];
  };
  await mostrarProgramas(container, { buscar });

  assert.equal(container.querySelector("details").open, true);
  const servidor = container.querySelector("#f-servidor-api");
  assert.equal(servidor.value, "http://localhost:8000");

  servidor.value = "";
  enviar(container.querySelector("form"));
  await esperar();

  assert.equal(chamadas, 2);
  assert.equal(localStorage.getItem("mdca.financeiro.api"), null);
  assert.equal(urlDaApi(), API_PADRAO);
  assert.match(texto(), /Nenhum programa cadastrado/);
});

test("falha inesperada vira o erro genérico", async () => {
  await mostrarProgramas(container, { buscar: async () => Promise.reject(new TypeError("quebrou")) });

  assert.match(texto(), /Não foi possível carregar/);
  assert.doesNotMatch(texto(), /quebrou/);
});

test("resposta que chega depois de sair da tela não mexe em nada", async () => {
  const resposta = adiado();
  const pronto = mostrarProgramas(container, { buscar: () => resposta.promessa });
  container.remove();

  resposta.resolver([{ id: "p-1", nome: "Semear" }]);
  await pronto;

  assert.equal(container.querySelector("table"), null);
});
