// Sessão compartilhada (Frontend/Shared/plataforma.js): login, primeiro acesso, sair,
// sessão vencida e endereço da API. Navegador simulado (jsdom) e fetch simulado.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/" });
Object.assign(globalThis, {
  window: dom.window,
  localStorage: dom.window.localStorage,
  sessionStorage: dom.window.sessionStorage,
});
const plataforma = await import("../../Shared/plataforma.js");
const { API_PADRAO, entrar, primeiroAcesso, sair, lerSessao, urlDaApi, salvarUrlDaApi, temPapel, encerrarSessaoLocal } = plataforma;

const AMANHA = new Date(Date.now() + 86400000).toISOString();
const ONTEM = new Date(Date.now() - 86400000).toISOString();
const USUARIO = { id: "u1", nome: "Luana Ferraz", email: "luana@mdca.org.br", papeis: [{ id: "coordenacao", nome: "Coordenação" }] };

let chamadas = [];
function responder(status, corpo) {
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    return new Response(corpo === undefined ? null : JSON.stringify(corpo), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  chamadas = [];
});

test("entrar com 'lembrar' grava a sessão em localStorage e manda e-mail, senha e lembrar", async () => {
  responder(200, { token: "tok-1", expira_em: AMANHA, usuario: USUARIO });
  const r = await entrar({ email: "luana@mdca.org.br", senha: "segredo123", lembrar: true });
  assert.equal(r.ok, true);
  assert.equal(r.sessao.token, "tok-1");
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0].url, `${API_PADRAO}/auth/entrar`);
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(chamadas[0].body), { email: "luana@mdca.org.br", senha: "segredo123", lembrar: true });
  assert.equal(JSON.parse(localStorage.getItem("mdca.sessao")).token, "tok-1");
  assert.equal(sessionStorage.getItem("mdca.sessao"), null);
  assert.deepEqual(lerSessao(), { token: "tok-1", expira_em: AMANHA, usuario: USUARIO });
});

test("entrar sem 'lembrar' grava a sessão só em sessionStorage", async () => {
  responder(200, { token: "tok-2", expira_em: AMANHA, usuario: USUARIO });
  const r = await entrar({ email: "luana@mdca.org.br", senha: "segredo123", lembrar: false });
  assert.equal(r.ok, true);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(JSON.parse(sessionStorage.getItem("mdca.sessao")).token, "tok-2");
  assert.equal(lerSessao().token, "tok-2");
});

test("erro 401 devolve a mensagem do backend e não cria sessão", async () => {
  responder(401, { detail: "E-mail ou senha incorretos." });
  const r = await entrar({ email: "luana@mdca.org.br", senha: "errada", lembrar: true });
  assert.deepEqual(r, { ok: false, mensagem: "E-mail ou senha incorretos." });
  assert.equal(lerSessao(), null);
});

test("erro 429 devolve a mensagem do backend", async () => {
  responder(429, { detail: "Muitas tentativas. Tente de novo em alguns minutos." });
  const r = await entrar({ email: "luana@mdca.org.br", senha: "errada", lembrar: true });
  assert.equal(r.mensagem, "Muitas tentativas. Tente de novo em alguns minutos.");
});

test("rede caída devolve a mensagem de conexão", async () => {
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  const r = await entrar({ email: "luana@mdca.org.br", senha: "x", lembrar: true });
  assert.deepEqual(r, { ok: false, mensagem: "Sem conexão com o servidor. Tente de novo." });
});

test("primeiro acesso manda e-mail, código, senha e lembrar e guarda a sessão", async () => {
  responder(200, { token: "tok-3", expira_em: AMANHA, usuario: USUARIO });
  const r = await primeiroAcesso({ email: "luana@mdca.org.br", codigo: "ABCD-1234", senha: "novasenha1", lembrar: false });
  assert.equal(r.ok, true);
  assert.equal(chamadas[0].url, `${API_PADRAO}/auth/primeiro-acesso`);
  assert.deepEqual(JSON.parse(chamadas[0].body), { email: "luana@mdca.org.br", codigo: "ABCD-1234", senha: "novasenha1", lembrar: false });
  assert.equal(JSON.parse(sessionStorage.getItem("mdca.sessao")).token, "tok-3");
});

test("primeiro acesso com código vencido devolve a mensagem do backend", async () => {
  responder(400, { detail: "Código inválido ou vencido." });
  const r = await primeiroAcesso({ email: "a@b.co", codigo: "X", senha: "novasenha1", lembrar: true });
  assert.deepEqual(r, { ok: false, mensagem: "Código inválido ou vencido." });
});

test("sessão vencida é apagada e lerSessao devolve null", () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "velho", expira_em: ONTEM, usuario: USUARIO }));
  sessionStorage.setItem("mdca.sessao", JSON.stringify({ token: "velho2", expira_em: ONTEM, usuario: USUARIO }));
  assert.equal(lerSessao(), null);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(sessionStorage.getItem("mdca.sessao"), null);
});

test("sessão estragada é apagada", () => {
  localStorage.setItem("mdca.sessao", "{não é json");
  assert.equal(lerSessao(), null);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
});

test("sair chama /auth/sair com o token e apaga a sessão e o papel do Financeiro", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "tok-4", expira_em: AMANHA, usuario: USUARIO }));
  localStorage.setItem("mdca.financeiro.papel", "coordenacao");
  responder(204);
  await sair();
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0].url, `${API_PADRAO}/auth/sair`);
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].headers.Authorization, "Bearer tok-4");
  assert.equal(lerSessao(), null);
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);
});

test("sair sem rede apaga a sessão mesmo assim", async () => {
  sessionStorage.setItem("mdca.sessao", JSON.stringify({ token: "tok-5", expira_em: AMANHA, usuario: USUARIO }));
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await sair();
  assert.equal(lerSessao(), null);
});

test("encerrarSessaoLocal apaga sem chamar a API", () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "t", expira_em: AMANHA, usuario: USUARIO }));
  globalThis.fetch = async () => { throw new Error("não deveria chamar"); };
  encerrarSessaoLocal();
  assert.equal(lerSessao(), null);
});

test("urlDaApi: padrão, chave antiga do Financeiro, chave nova e sem barra final", () => {
  assert.equal(urlDaApi(), API_PADRAO);
  localStorage.setItem("mdca.financeiro.api", "http://localhost:8000/");
  assert.equal(urlDaApi(), "http://localhost:8000");
  localStorage.setItem("mdca.api", "http://127.0.0.1:9000//");
  assert.equal(urlDaApi(), "http://127.0.0.1:9000");
});

test("salvarUrlDaApi guarda o endereço; vazio ou o padrão voltam ao padrão", async () => {
  salvarUrlDaApi(" http://localhost:8000/ ");
  assert.equal(localStorage.getItem("mdca.api"), "http://localhost:8000");
  responder(401, { detail: "E-mail ou senha incorretos." });
  await entrar({ email: "a@b.co", senha: "x", lembrar: true });
  assert.equal(chamadas[0].url, "http://localhost:8000/auth/entrar");
  localStorage.setItem("mdca.financeiro.api", "http://antigo:1");
  salvarUrlDaApi(API_PADRAO);
  assert.equal(urlDaApi(), API_PADRAO);
  salvarUrlDaApi("");
  assert.equal(localStorage.getItem("mdca.api"), null);
});

test("temPapel confere o id do papel", () => {
  const sessao = { usuario: { papeis: [{ id: "administracao", nome: "Administração do sistema" }] } };
  assert.equal(temPapel(sessao, "administracao"), true);
  assert.equal(temPapel(sessao, "coordenacao"), false);
  assert.equal(temPapel(null, "administracao"), false);
});
