// Computador: ao abrir, o Financeiro confere a pessoa em /auth/eu e usa os papéis de agora (jsdom).
// A raiz não se chama "app" para o app.js não se montar sozinho ao ser importado.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { sessaoDeTeste } from "./ajuda-sessao.js";

const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: "http://localhost/Financeiro/#/inicio" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  localStorage: dom.window.localStorage,
  sessionStorage: dom.window.sessionStorage,
});
const { iniciar } = await import("../app.js");

let eu; // resposta de /auth/eu: [status, corpo] ou null (sem rede)
let chamadasEu = 0;
globalThis.fetch = async (url) => {
  if (new URL(url).pathname === "/auth/eu") {
    chamadasEu += 1;
    if (!eu) throw new TypeError("Failed to fetch");
    return new Response(JSON.stringify(eu[1]), { status: eu[0], headers: { "Content-Type": "application/json" } });
  }
  return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
};

const esperar = () => new Promise((r) => setTimeout(r, 30));
const pessoa = (papeis) => ({ id: "u-luana", nome: "Luana Ferraz", email: "luana@mdca.org.br", papeis: papeis.map((id) => ({ id, nome: id })) });
const rotulos = (raiz) => [...raiz.querySelectorAll(".lateral__item")].map((a) => a.textContent.replace(/\d+$/, ""));

let raiz;
let destinos;
async function abrir() {
  raiz = document.createElement("div");
  document.body.replaceChildren(raiz);
  destinos = [];
  iniciar(raiz, { redirecionar: (d) => destinos.push(d) });
  await esperar();
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  eu = null;
  chamadasEu = 0;
});

test("papel dado depois do login aparece: com dois papéis, pede para escolher", async () => {
  sessaoDeTeste({ papeis: ["direcao"] });
  eu = [200, pessoa(["direcao", "coordenacao"])];
  await abrir();
  assert.equal(chamadasEu, 1);
  assert.equal(raiz.querySelector("h1")?.textContent, "Entrar como");
  assert.deepEqual(destinos, []);
});

test("papel tirado depois do login some do menu", async () => {
  sessaoDeTeste({ papeis: ["direcao", "coordenacao"], papel: "coordenacao" });
  eu = [200, pessoa(["direcao"])];
  await abrir();
  assert.deepEqual(rotulos(raiz), ["Início", "Projetos", "Relatórios", "Auditoria"]);
  assert.match(raiz.querySelector(".lateral__usuario").textContent, /Diretoria/);
});

test("/auth/eu com 401 apaga a sessão e volta para a página inicial", async () => {
  sessaoDeTeste({ papeis: ["coordenacao"] });
  eu = [401, { detail: "Sessão inválida ou vencida." }];
  await abrir();
  assert.deepEqual(destinos, ["../"]);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
});

test("sem rede segue com a sessão guardada", async () => {
  sessaoDeTeste({ papeis: ["coordenacao"] });
  await abrir();
  assert.equal(chamadasEu, 1);
  assert.deepEqual(destinos, []);
  assert.deepEqual(rotulos(raiz), ["Início", "Lançamentos", "Projetos", "Relatórios", "Auditoria"]);
  assert.notEqual(localStorage.getItem("mdca.sessao"), null);
});

test("educador com outro papel, vindo do celular em #/papel, escolhe o papel em vez de voltar ao celular", async () => {
  sessaoDeTeste({ papeis: ["educador", "coordenacao"], papel: "educador" });
  eu = [200, pessoa(["educador", "coordenacao"])];
  window.location.hash = "#/papel";
  await esperar();
  await abrir();
  assert.equal(raiz.querySelector("h1")?.textContent, "Entrar como");
  assert.deepEqual(destinos, []);
  window.location.hash = "#/inicio";
  await esperar();
});
