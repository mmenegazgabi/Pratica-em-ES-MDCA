// Estrutura do computador: sessão da plataforma, escolha de papel, menu por papel e tela ausente (jsdom).
// A raiz não se chama "app" para o app.js não se montar sozinho ao ser importado.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { sessaoDeTeste } from "./ajuda-sessao.js";

const dom = new JSDOM('<!DOCTYPE html><body><div id="app-teste"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  localStorage: dom.window.localStorage,
  sessionStorage: dom.window.sessionStorage,
});
const { iniciar, definirContador } = await import("../app.js");

const chamadas = [];
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  if (String(url).endsWith("/auth/sair")) return new Response(null, { status: 204 });
  throw new Error("sem rede nos testes");
};
const raiz = document.getElementById("app-teste");
const esperar = () => new Promise((r) => setTimeout(r, 20));
const redirecionamentos = [];
iniciar(raiz, { redirecionar: (d) => redirecionamentos.push(d) });
await esperar();

async function irPara(hash) {
  if (window.location.hash === hash) window.dispatchEvent(new window.HashChangeEvent("hashchange"));
  else window.location.hash = hash;
  await esperar();
}
const rotulos = () => [...raiz.querySelectorAll(".lateral__item")].map((a) => a.textContent.replace(/\d+$/, ""));
const botoes = () => [...raiz.querySelectorAll("button")].map((b) => b.textContent);
const botao = (texto) => [...raiz.querySelectorAll("button")].find((b) => b.textContent === texto);

test("sem sessão da plataforma vai para a página inicial", () => {
  assert.deepEqual(redirecionamentos, ["../"]);
  assert.equal(raiz.querySelector(".lateral"), null);
});

test("papel único entra direto no Início, com o nome do banco e o papel", async () => {
  sessaoDeTeste({ papeis: ["direcao"], nome: "Jane Almeida" });
  await irPara("#/inicio");
  assert.deepEqual(rotulos(), ["Início", "Painel", "Projetos", "Relatórios", "Auditoria"]);
  assert.equal(raiz.querySelector('[aria-current="page"]').textContent.replace(/\d+$/, ""), "Início");
  const usuario = raiz.querySelector(".lateral__usuario").textContent;
  assert.match(usuario, /Jane Almeida/);
  assert.match(usuario, /Diretoria/);
  assert.equal(botao("Trocar papel"), undefined);
  assert.ok(botao("Sair"));
  assert.equal(botao("Trocar perfil"), undefined);
});

test("Projetos carrega a tela", async () => {
  await irPara("#/projetos");
  assert.match(raiz.querySelector(".principal").textContent, /Projetos/);
});

test("rota fora do menu volta ao Início", async () => {
  await irPara("#/lancamentos");
  assert.equal(window.location.hash, "#/inicio");
  assert.equal(raiz.querySelector('[aria-current="page"]').textContent.replace(/\d+$/, ""), "Início");
});

test("a barra lateral traz o logo do MDCA", () => {
  assert.ok(raiz.querySelector(".lateral__marca svg.logo"));
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

test("dois papéis mostram 'Entrar como' e a escolha persiste", async () => {
  sessaoDeTeste({ papeis: ["voluntario_financeiro", "coordenacao"], nome: "Luana Ferraz" });
  await irPara("#/inicio");
  assert.equal(raiz.querySelector("h1").textContent, "Entrar como");
  assert.equal(raiz.querySelector(".lateral"), null);
  assert.deepEqual(botoes(), ["Coordenação", "Voluntário financeiro"]);
  botao("Voluntário financeiro").click();
  await esperar();
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "voluntario_financeiro");
  assert.deepEqual(rotulos(), ["Início", "Lançamentos", "Conciliação"]);
  await irPara("#/conciliacao");
  assert.deepEqual(rotulos(), ["Início", "Lançamentos", "Conciliação"]);
});

test("Trocar papel abre 'Entrar como' e a nova escolha vale", async () => {
  botao("Trocar papel").click();
  await esperar();
  assert.equal(window.location.hash, "#/papel");
  assert.equal(raiz.querySelector("h1").textContent, "Entrar como");
  botao("Coordenação").click();
  await esperar();
  assert.equal(window.location.hash, "#/inicio");
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "coordenacao");
  assert.deepEqual(rotulos(), ["Início", "Lançamentos", "Projetos", "Relatórios", "Auditoria"]);
});

test("papel salvo que a pessoa perdeu é ignorado", async () => {
  sessaoDeTeste({ papeis: ["direcao", "voluntario_financeiro"], papel: "coordenacao" });
  await irPara("#/inicio");
  assert.equal(raiz.querySelector("h1").textContent, "Entrar como");
  assert.deepEqual(botoes(), ["Diretoria", "Voluntário financeiro"]);
});

test("sem papel do Financeiro mostra o aviso sem redirecionar", async () => {
  sessaoDeTeste({ papeis: ["administracao"] });
  redirecionamentos.length = 0;
  await irPara("#/inicio");
  assert.match(raiz.textContent, /Seu perfil não tem acesso ao Financeiro\./);
  const link = [...raiz.querySelectorAll("a")].find((a) => a.textContent === "Voltar ao início");
  assert.equal(link.getAttribute("href"), "../");
  assert.deepEqual(redirecionamentos, []);
  assert.equal(raiz.querySelector(".lateral"), null);
});

test("educador é encaminhado ao app do celular", async () => {
  sessaoDeTeste({ papeis: ["educador"], nome: "Marcos Vieira" });
  redirecionamentos.length = 0;
  await irPara("#/projetos");
  assert.deepEqual(redirecionamentos, ["lancamento/"]);
});

test("escolher Educador em 'Entrar como' leva ao app do celular", async () => {
  sessaoDeTeste({ papeis: ["coordenacao", "educador"], nome: "Marcos Vieira" });
  redirecionamentos.length = 0;
  await irPara("#/inicio");
  botao("Educador").click();
  await esperar();
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "educador");
  assert.deepEqual(redirecionamentos, ["lancamento/"]);
});

test("Sair chama /auth/sair, apaga a sessão e volta à página inicial", async () => {
  sessaoDeTeste({ papeis: ["coordenacao", "direcao"], papel: "direcao", token: "tok-sair" });
  await irPara("#/inicio");
  redirecionamentos.length = 0;
  chamadas.length = 0;
  botao("Sair").click();
  await esperar();
  const saida = chamadas.find((c) => String(c.url).endsWith("/auth/sair"));
  assert.ok(saida);
  assert.equal(saida.method, "POST");
  assert.equal(saida.headers.Authorization, "Bearer tok-sair");
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);
  assert.deepEqual(redirecionamentos, ["../"]);
});
