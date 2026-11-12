// Login único (T-35) na Gestão: sem sessão da plataforma, o app não abre e manda para a
// página inicial (como o Financeiro); não existe mais tela de código de acesso.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");

async function abrir(endereco) {
  const navegacoes = [];
  const console = new VirtualConsole();
  // O jsdom não navega de verdade: a tentativa vira um aviso "Not implemented: navigation".
  console.on("jsdomError", (erro) => {
    if (/navigation/i.test(erro.message)) navegacoes.push(erro.message);
  });
  const dom = new JSDOM(html, { url: endereco, virtualConsole: console });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    location: dom.window.location,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    DOMParser: dom.window.DOMParser,
  });
  globalThis.fetch = async () => new Response("[]", { status: 200 });
  await import(`../app.js?${Math.random()}`);
  return { navegacoes, app: dom.window.document.getElementById("app") };
}

test("sem sessão, a Gestão manda para a página inicial da plataforma e não desenha nada", async () => {
  const { navegacoes, app } = await abrir("http://localhost/Gestao/#/pessoas");

  assert.equal(navegacoes.length, 1);
  assert.equal(app.innerHTML, "");
});

test("as prévias do mapa de telas (dados fictícios) abrem sem login", async () => {
  const { navegacoes, app } = await abrir("http://localhost/Gestao/#/inicio?mini=1&perfil=coord");

  assert.deepEqual(navegacoes, []);
  assert.ok(app.querySelector("h1"));
});

test("não existe mais formulário de código de acesso nem de usuário digitado", () => {
  const codigo = ["base/estados.js", "base/api.js", "app.js"].map((f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8")).join("\n");

  assert.doesNotMatch(codigo, /f-codigo-acesso|Código de acesso|salvarAcesso|salvarUsuario|mdca\.financeiro\.token|mdca\.gestao\.usuario/);
});
