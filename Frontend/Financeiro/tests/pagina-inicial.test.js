// Página inicial (Frontend/index.html + Shared/pagina-inicial.js): Entrar, Primeiro acesso,
// Esqueci minha senha, escolha de módulo e Sair. jsdom não roda <script type="module">,
// então carregamos o HTML e chamamos o mesmo iniciar(document) que o script da página chama.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

const HTML = await readFile(new URL("../../index.html", import.meta.url), "utf8");
const API = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";
const AMANHA = new Date(Date.now() + 86400000).toISOString();

const base = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/" });
Object.assign(globalThis, {
  window: base.window,
  localStorage: base.window.localStorage,
  sessionStorage: base.window.sessionStorage,
});
const { iniciar } = await import("../../Shared/pagina-inicial.js");

let chamadas = [];
let respostas = [];
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  const proxima = respostas.shift();
  if (!proxima) throw new TypeError("Failed to fetch");
  const [status, corpo] = proxima;
  return new Response(corpo === undefined ? null : JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
};

function usuario(nome, papeis) {
  return { id: "u1", nome, email: "pessoa@mdca.org.br", papeis: papeis.map((id) => ({ id, nome: id })) };
}

let doc;
function abrir() {
  const dom = new JSDOM(HTML, { url: "http://localhost/" }); // sem runScripts: o HTML só é lido
  doc = dom.window.document;
  iniciar(doc);
  return doc;
}
const $ = (id) => doc.getElementById(id);
const esperar = (ms = 10) => new Promise((ok) => setTimeout(ok, ms));
function enviar(id) {
  $(id).dispatchEvent(new doc.defaultView.Event("submit", { cancelable: true }));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  chamadas = [];
  respostas = [];
});

test("o script da página importa pagina-inicial.js e chama iniciar(document)", () => {
  assert.match(HTML, /<script type="module">\s*import \{ iniciar \} from "\.\/Shared\/pagina-inicial\.js";\s*iniciar\(document\);/);
  assert.doesNotMatch(HTML, /mdca\.plataforma\.entrada/);
});

test("sem sessão mostra Entrar; Primeiro acesso, Esqueci e a escolha de módulos ficam escondidos", () => {
  abrir();
  assert.equal($("login").hidden, false);
  assert.equal($("app").hidden, true);
  assert.equal($("formEntrar").hidden, false);
  assert.equal($("formPrimeiro").hidden, true);
  assert.equal($("esqueci").hidden, true);
  assert.equal(doc.title, "Entrar · Sistema MDCA");
  assert.equal(doc.querySelector("details.login-avancado summary").textContent, "Servidor (avançado)");
  assert.equal($("apiEndereco").value, API);
});

test("envio certo chama /auth/entrar e mostra os módulos com o nome da pessoa", async () => {
  abrir();
  respostas.push([200, { token: "tok", expira_em: AMANHA, usuario: usuario("Luana <b>Ferraz</b>", ["coordenacao"]) }]);
  $("loginEmail").value = " luana@mdca.org.br ";
  $("loginSenha").value = "segredo123";
  $("loginLembrar").checked = false;
  enviar("formEntrar");
  assert.equal($("entrarBotao").disabled, true, "botão desabilitado durante a requisição");
  await esperar();
  assert.equal($("entrarBotao").disabled, false);
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0].url, `${API}/auth/entrar`);
  assert.equal(chamadas[0].method, "POST");
  assert.deepEqual(JSON.parse(chamadas[0].body), { email: "luana@mdca.org.br", senha: "segredo123", lembrar: false });
  assert.equal($("login").hidden, true);
  assert.equal($("app").hidden, false);
  assert.equal($("saudacao").textContent, "Olá, Luana <b>Ferraz</b>");
  assert.equal($("saudacao").querySelector("b"), null, "nome entra como texto");
  assert.equal($("loginSenha").value, "");
  assert.equal($("cartaoAdmin").hidden, true);
  assert.equal($("navAdmin").hidden, true);
  assert.ok(sessionStorage.getItem("mdca.sessao"));
});

test("erro da API aparece na caixa vermelha e continua no login", async () => {
  abrir();
  respostas.push([401, { detail: "E-mail ou senha incorretos." }]);
  $("loginEmail").value = "luana@mdca.org.br";
  $("loginSenha").value = "errada";
  enviar("formEntrar");
  await esperar();
  assert.equal($("loginErro").hidden, false);
  assert.equal($("loginErro").textContent, "E-mail ou senha incorretos.");
  assert.equal($("app").hidden, true);
});

test("e-mail inválido não chama a API", () => {
  abrir();
  $("loginEmail").value = "luana";
  $("loginSenha").value = "x";
  enviar("formEntrar");
  assert.equal(chamadas.length, 0);
  assert.equal($("loginErro").textContent, "Informe um e-mail válido.");
});

test("cartão e item de menu Administração só aparecem para administracao", () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "t", expira_em: AMANHA, usuario: usuario("Ana", ["administracao"]) }));
  abrir();
  assert.equal($("app").hidden, false);
  assert.equal($("saudacao").textContent, "Olá, Ana");
  assert.equal($("cartaoAdmin").hidden, false);
  assert.equal($("navAdmin").hidden, false);
  assert.equal($("cartaoAdmin").getAttribute("href"), "Admin/");
  assert.equal($("navAdmin").getAttribute("href"), "Admin/");
  assert.equal($("cartaoAdmin").textContent.includes("Administração"), true);
});

test("Sair chama /auth/sair com o token e volta para o login", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "tok-sair", expira_em: AMANHA, usuario: usuario("Ana", ["coordenacao"]) }));
  localStorage.setItem("mdca.financeiro.papel", "coordenacao");
  abrir();
  respostas.push([204]);
  $("sair").click();
  await esperar();
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0].url, `${API}/auth/sair`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer tok-sair");
  assert.equal($("app").hidden, true);
  assert.equal($("login").hidden, false);
  assert.equal($("formEntrar").hidden, false);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);
});

test("primeiro acesso com senhas diferentes não chama a API", () => {
  abrir();
  $("irPrimeiro").click();
  assert.equal($("formPrimeiro").hidden, false);
  assert.equal($("formEntrar").hidden, true);
  $("primeiroEmail").value = "luana@mdca.org.br";
  $("primeiroCodigo").value = "ABCD1234";
  $("primeiroSenha").value = "novasenha1";
  $("primeiroRepetir").value = "outrasenha";
  enviar("formPrimeiro");
  assert.equal(chamadas.length, 0);
  assert.equal($("primeiroErro").hidden, false);
  assert.equal($("primeiroErro").textContent, "As senhas não conferem.");
});

test("primeiro acesso certo chama /auth/primeiro-acesso e entra", async () => {
  abrir();
  $("irPrimeiro").click();
  respostas.push([200, { token: "tok-p", expira_em: AMANHA, usuario: usuario("Bia", []) }]);
  $("primeiroEmail").value = "bia@mdca.org.br";
  $("primeiroCodigo").value = " ABCD1234 ";
  $("primeiroSenha").value = "novasenha1";
  $("primeiroRepetir").value = "novasenha1";
  enviar("formPrimeiro");
  assert.equal($("primeiroBotao").disabled, true);
  await esperar();
  assert.equal(chamadas[0].url, `${API}/auth/primeiro-acesso`);
  assert.deepEqual(JSON.parse(chamadas[0].body), { email: "bia@mdca.org.br", codigo: "ABCD1234", senha: "novasenha1", lembrar: true });
  assert.equal($("app").hidden, false);
  assert.equal($("saudacao").textContent, "Olá, Bia");
  assert.ok(localStorage.getItem("mdca.sessao"));
});

test("primeiro acesso com código vencido mostra a mensagem do backend", async () => {
  abrir();
  $("irPrimeiro").click();
  respostas.push([400, { detail: "Código inválido ou vencido." }]);
  $("primeiroEmail").value = "bia@mdca.org.br";
  $("primeiroCodigo").value = "X";
  $("primeiroSenha").value = "novasenha1";
  $("primeiroRepetir").value = "novasenha1";
  enviar("formPrimeiro");
  await esperar();
  assert.equal($("primeiroErro").textContent, "Código inválido ou vencido.");
  assert.equal($("app").hidden, true);
});

test("Esqueci minha senha mostra a orientação e leva ao Primeiro acesso", () => {
  abrir();
  $("irEsqueci").click();
  assert.equal($("esqueci").hidden, false);
  assert.equal($("formEntrar").hidden, true);
  assert.equal(
    $("esqueci").querySelector(".login-texto").textContent,
    "Peça à administração um novo código de acesso e use Primeiro acesso.",
  );
  $("esqueciIrPrimeiro").click();
  assert.equal($("esqueci").hidden, true);
  assert.equal($("formPrimeiro").hidden, false);
});

test("Servidor (avançado): o endereço digitado vale para o login", async () => {
  abrir();
  $("apiEndereco").value = "http://localhost:8000/";
  respostas.push([401, { detail: "E-mail ou senha incorretos." }]);
  $("loginEmail").value = "luana@mdca.org.br";
  $("loginSenha").value = "x";
  enviar("formEntrar");
  await esperar();
  assert.equal(chamadas[0].url, "http://localhost:8000/auth/entrar");
  assert.equal(localStorage.getItem("mdca.api"), "http://localhost:8000");
});

test("botão de menu do celular abre e fecha a barra lateral", () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "t", expira_em: AMANHA, usuario: usuario("Ana", []) }));
  abrir();
  $("navToggle").click();
  assert.equal($("sidebar").classList.contains("is-open"), true);
  assert.equal($("navToggle").getAttribute("aria-expanded"), "true");
  $("navToggle").click();
  assert.equal($("sidebar").classList.contains("is-open"), false);
});
