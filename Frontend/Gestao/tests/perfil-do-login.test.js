// Com o login (T-35), o perfil da Gestão vem dos papéis da pessoa: o menu do usuário
// mostra o nome dela e só os perfis que ela tem, sem os perfis de teste do protótipo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");
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
globalThis.fetch = async () => new Response("[]", { status: 200 });

const amanha = new Date(Date.now() + 86400000).toISOString();
localStorage.setItem(
  "mdca.sessao",
  JSON.stringify({
    token: "token-da-sessao",
    expira_em: amanha,
    usuario: {
      id: "luana",
      nome: "Luana Ferraz",
      email: "luana@mdca.org.br",
      papeis: [
        { id: "direcao", nome: "Direção" },
        { id: "coordenacao", nome: "Coordenação" },
        { id: "voluntario_financeiro", nome: "Voluntário(a) financeiro" },
      ],
    },
  }),
);
// Um perfil de teste salvo antes do login não vale: a Luana não é administradora.
localStorage.setItem("mdca.gestao.papel", "admin");

await import("../app.js");

const $ = (s) => document.querySelector(s);
const esperar = () => new Promise((r) => setTimeout(r, 20));
const botoes = () => [...document.querySelectorAll(".persona-buttons button")];
// Nome e papel ficam no rodapé da barra lateral: "Luana Ferraz<small>Coordenação</small>".
const nome = () => $(".lateral__nome").firstChild.textContent;
const papel = () => $(".lateral__nome small").textContent;

test("entra com o perfil mais amplo que a pessoa tem e mostra o nome dela", () => {
  assert.equal(nome(), "Luana Ferraz");
  assert.equal(papel(), "Coordenação");
  assert.equal($(".lateral__avatar").textContent, "LF");
});

test("o menu do usuário não tem os perfis de teste, só os da pessoa", () => {
  const menu = $(".user-menu").textContent;
  assert.doesNotMatch(menu, /provisório|Perfil de teste/);
  assert.match(menu, /Entrar como/);
  assert.deepEqual(
    botoes().map((b) => b.textContent),
    ["Coordenação", "Consulta institucional"],
  );
  assert.equal($('[data-action="persona:admin"]'), null);
  assert.equal($('[data-action="persona:educator"]'), null);
});

test("troca entre os próprios perfis e ignora um perfil que não é dela", async () => {
  $('[data-action="persona:director"]').click();
  await esperar();
  assert.equal(papel(), "Consulta institucional");

  // Um botão forjado com outro perfil não muda nada.
  const forjado = document.createElement("button");
  forjado.dataset.action = "persona:admin";
  document.body.append(forjado);
  forjado.click();
  await esperar();
  assert.equal(papel(), "Consulta institucional");
});

test("a tela de entrada do protótipo não aparece para quem está logado", async () => {
  window.location.hash = "#/login";
  await esperar();
  await esperar();
  assert.equal(window.location.hash, "#/inicio");
  assert.equal($("#login-form"), null);
});
