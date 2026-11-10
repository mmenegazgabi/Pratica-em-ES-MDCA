// Tela de administração (Frontend/Admin/admin.js): pessoas e papéis.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const API = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";
const AMANHA = new Date(Date.now() + 86400000).toISOString();

const base = new JSDOM("<!DOCTYPE html><body><div id='app'></div></body>", { url: "http://localhost/" });
Object.assign(globalThis, {
  window: base.window,
  document: base.window.document,
  localStorage: base.window.localStorage,
  sessionStorage: base.window.sessionStorage,
});
const { iniciar } = await import("../../Admin/admin.js");

let chamadas = [];
let respostas = [];
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  const proxima = respostas.shift();
  if (!proxima) throw new TypeError("Failed to fetch");
  const [status, corpo] = proxima;
  return new Response(corpo === undefined ? null : JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
};

const PAPEIS = [
  { id: "administracao", nome: "Administração" },
  { id: "coordenacao", nome: "Coordenação" },
  { id: "voluntario_financeiro", nome: "Voluntário financeiro" },
];
const PESSOAS = [
  { id: "u1", nome: "Ana Admin", email: "ana@mdca.org.br", ativo: true, papeis: [PAPEIS[0], PAPEIS[1]], situacao: "ativo" },
  { id: "u2", nome: "Beto Novo", email: "beto@mdca.org.br", ativo: true, papeis: [PAPEIS[2]], situacao: "aguardando_primeiro_acesso" },
  { id: "u3", nome: "Cris Fora", email: "cris@mdca.org.br", ativo: false, papeis: [PAPEIS[1]], situacao: "desativado" },
];

function sessaoDe(papeis) {
  localStorage.setItem(
    "mdca.sessao",
    JSON.stringify({ token: "tok", expira_em: AMANHA, usuario: { id: "u1", nome: "Ana Admin", email: "ana@mdca.org.br", papeis } }),
  );
}
const ADMIN = [{ id: "administracao", nome: "Administração" }];

let raiz;
let destino;
// Ao abrir, a tela confere a pessoa em /auth/eu; por padrão o servidor devolve a mesma da sessão.
function euDaSessao() {
  const guardada = localStorage.getItem("mdca.sessao");
  return guardada ? [[200, JSON.parse(guardada).usuario]] : [];
}
async function abrir({ lista = PESSOAS } = {}) {
  respostas = [...euDaSessao(), [200, lista], [200, PAPEIS]];
  document.body.replaceChildren();
  raiz = document.createElement("div");
  document.body.append(raiz);
  destino = null;
  iniciar(raiz, { redirecionar: (d) => (destino = d) });
  await esperar(20);
}
const esperar = (ms = 10) => new Promise((ok) => setTimeout(ok, ms));
const botao = (texto, onde = document) => [...onde.querySelectorAll("button")].find((b) => b.textContent.trim() === texto);
const linhas = () => [...raiz.querySelectorAll("tbody tr")];
function enviar(form) {
  form.dispatchEvent(new window.Event("submit", { cancelable: true }));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  chamadas = [];
  respostas = [];
});

test("sem sessão redireciona para ../ sem chamar a API", async () => {
  await abrir();
  assert.equal(destino, "../");
  assert.equal(chamadas.length, 0);
});

test("sessão sem administração mostra o aviso com link para o início", async () => {
  sessaoDe([{ id: "coordenacao", nome: "Coordenação" }]);
  await abrir();
  assert.match(raiz.textContent, /Esta área é só da administração\./);
  assert.equal(raiz.querySelector('a[href="../"]').textContent.trim().length > 0, true);
  assert.deepEqual(chamadas.map((c) => c.url), [`${API}/auth/eu`], "só confere a pessoa");
  assert.equal(destino, null);
});

test("lista as pessoas com situação traduzida, papéis e ações", async () => {
  sessaoDe(ADMIN);
  await abrir();
  assert.equal(chamadas[0].url, `${API}/auth/eu`);
  assert.equal(chamadas[1].url, `${API}/admin/usuarios`);
  assert.equal(chamadas[1].headers.Authorization, "Bearer tok");
  assert.equal(chamadas[2].url, `${API}/gestao/papeis`);
  assert.deepEqual(
    [...raiz.querySelectorAll("thead th")].map((th) => th.textContent).slice(0, 4),
    ["Nome", "E-mail", "Papéis", "Situação"],
  );
  const l = linhas();
  assert.equal(l.length, 3);
  assert.match(l[0].textContent, /Ana Admin/);
  assert.match(l[0].textContent, /Administração, Coordenação/);
  assert.match(l[0].textContent, /Ativo/);
  assert.match(l[1].textContent, /Aguardando primeiro acesso/);
  assert.match(l[2].textContent, /Desativado/);
  assert.ok(botao("Editar", l[2]));
  assert.ok(!botao("Gerar código", l[2]));
  assert.ok(botao("Gerar código", l[1]));
});

test("nome vindo da API entra como texto, nunca como HTML", async () => {
  sessaoDe(ADMIN);
  await abrir({ lista: [{ ...PESSOAS[0], nome: "<img src=x onerror=alert(1)>" }] });
  assert.equal(raiz.querySelector("tbody img"), null);
  assert.match(linhas()[0].textContent, /<img src=x/);
});

test("401 apaga a sessão e redireciona", async () => {
  sessaoDe(ADMIN);
  respostas = [[401, { detail: "Sessão inválida." }], [401, { detail: "x" }]];
  raiz = document.createElement("div");
  destino = null;
  iniciar(raiz, { redirecionar: (d) => (destino = d) });
  await esperar(20);
  assert.equal(destino, "../");
  assert.equal(localStorage.getItem("mdca.sessao"), null);
});

test("403 mostra o aviso da administração", async () => {
  sessaoDe(ADMIN);
  respostas = [...euDaSessao(), [403, { detail: "x" }], [200, PAPEIS]];
  raiz = document.createElement("div");
  iniciar(raiz, { redirecionar() {} });
  await esperar(20);
  assert.match(raiz.textContent, /Esta área é só da administração\./);
});

test("cadastrar envia nome, e-mail e papéis e mostra o código", async () => {
  sessaoDe(ADMIN);
  await abrir();
  botao("Cadastrar pessoa").click();
  const dlg = raiz.querySelector("dialog");
  dlg.querySelector('input[name="nome"]').value = "Dora Nova";
  dlg.querySelector('input[name="email"]').value = "dora@mdca.org.br";
  dlg.querySelector('input[type="checkbox"][value="coordenacao"]').checked = true;
  respostas = [
    [201, { usuario: { ...PESSOAS[1], id: "u4", nome: "Dora Nova" }, codigo: "ABCD-1234", codigo_expira_em: "2026-11-07T15:05:00Z" }],
    [200, PESSOAS],
  ];
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].url, `${API}/admin/usuarios`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer tok");
  assert.deepEqual(JSON.parse(chamadas[0].body), { nome: "Dora Nova", email: "dora@mdca.org.br", papeis: ["coordenacao"] });
  const texto = raiz.querySelector("dialog").textContent;
  assert.match(texto, /ABCD-1234/);
  assert.match(texto, /\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/);
  assert.match(texto, /Este código não aparece de novo\. Entregue à pessoa: ela entra em Primeiro acesso, informa o e-mail e o código e cria a senha\./);
  let copiado = null;
  Object.defineProperty(navigator, "clipboard", { value: { writeText: async (t) => (copiado = t) }, configurable: true });
  botao("Copiar", raiz.querySelector("dialog")).click();
  await esperar();
  assert.equal(copiado, "ABCD-1234");
});

test("cadastrar com e-mail repetido mostra o erro do backend no diálogo", async () => {
  sessaoDe(ADMIN);
  await abrir();
  botao("Cadastrar pessoa").click();
  const dlg = raiz.querySelector("dialog");
  dlg.querySelector('input[name="nome"]').value = "Ana";
  dlg.querySelector('input[name="email"]').value = "ana@mdca.org.br";
  dlg.querySelector('input[type="checkbox"]').checked = true;
  respostas = [[409, { detail: "Já existe uma pessoa com este e-mail." }]];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.match(raiz.querySelector("dialog").textContent, /Já existe uma pessoa com este e-mail\./);
});

test("Gerar código chama a rota e mostra o código novo", async () => {
  sessaoDe(ADMIN);
  await abrir();
  respostas = [[200, { codigo: "ZZZZ-9999", codigo_expira_em: "2026-11-07T15:05:00Z" }]];
  chamadas = [];
  botao("Gerar código", linhas()[1]).click();
  await esperar(20);
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].url, `${API}/admin/usuarios/u2/codigo`);
  assert.match(raiz.querySelector("dialog").textContent, /ZZZZ-9999/);
});

test("Editar envia só os campos alterados", async () => {
  sessaoDe(ADMIN);
  await abrir();
  botao("Editar", linhas()[1]).click();
  const dlg = raiz.querySelector("dialog");
  assert.equal(dlg.querySelector('input[name="nome"]').value, "Beto Novo");
  assert.equal(dlg.querySelector('input[value="voluntario_financeiro"]').checked, true);
  dlg.querySelector('input[name="nome"]').value = "Beto Silva";
  respostas = [[200, { ...PESSOAS[1], nome: "Beto Silva" }], [200, PESSOAS]];
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.equal(chamadas[0].method, "PATCH");
  assert.equal(chamadas[0].url, `${API}/admin/usuarios/u2`);
  assert.deepEqual(JSON.parse(chamadas[0].body), { nome: "Beto Silva" });
  assert.equal(raiz.querySelector("dialog"), null);
});

test("Editar: desativar envia ativo=false e erro do backend aparece no diálogo", async () => {
  sessaoDe(ADMIN);
  await abrir();
  botao("Editar", linhas()[0]).click();
  const dlg = raiz.querySelector("dialog");
  dlg.querySelector('input[name="ativo"]').checked = false;
  respostas = [[400, { detail: "Você não pode desativar a própria conta." }]];
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.deepEqual(JSON.parse(chamadas[0].body), { ativo: false });
  assert.match(raiz.querySelector("dialog").textContent, /Você não pode desativar a própria conta\./);
});

test("a lateral tem Voltar ao início e Sair", async () => {
  sessaoDe(ADMIN);
  await abrir();
  assert.equal(raiz.querySelector('.lateral a[href="../"]').textContent.includes("Voltar ao início"), true);
  respostas = [[204]];
  botao("Sair").click();
  await esperar(20);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(destino, "../");
});

// — papéis atualizados ao abrir (/auth/eu) —

test("papel de administração dado depois do login já abre a lista", async () => {
  sessaoDe([{ id: "coordenacao", nome: "Coordenação" }]);
  respostas = [
    [200, { id: "u1", nome: "Ana Admin", email: "ana@mdca.org.br", papeis: [...ADMIN, { id: "coordenacao", nome: "Coordenação" }] }],
    [200, PESSOAS],
    [200, PAPEIS],
  ];
  raiz = document.createElement("div");
  iniciar(raiz, { redirecionar() {} });
  await esperar(20);
  assert.equal(linhas().length, 3);
  assert.equal(JSON.parse(localStorage.getItem("mdca.sessao")).usuario.papeis.length, 2);
});

test("papel de administração tirado depois do login mostra o aviso sem chamar a lista", async () => {
  sessaoDe(ADMIN);
  respostas = [[200, { id: "u1", nome: "Ana Admin", email: "ana@mdca.org.br", papeis: [{ id: "coordenacao", nome: "Coordenação" }] }]];
  raiz = document.createElement("div");
  iniciar(raiz, { redirecionar() {} });
  await esperar(20);
  assert.match(raiz.textContent, /Esta área é só da administração\./);
  assert.equal(chamadas.length, 1);
});

test("/auth/eu sem rede segue com a sessão guardada", async () => {
  sessaoDe(ADMIN);
  respostas = [];
  raiz = document.createElement("div");
  destino = null;
  const pronto = iniciar(raiz, { redirecionar: (d) => (destino = d) });
  respostas.push([200, PESSOAS], [200, PAPEIS]); // a primeira chamada (/auth/eu) já falhou sem rede
  await pronto;
  await esperar(20);
  assert.equal(destino, null);
  assert.equal(linhas().length, 3);
});

// — e-mail na edição (pessoas cadastradas antes do login podem não ter) —

test("Editar mostra o e-mail e só o envia quando muda", async () => {
  sessaoDe(ADMIN);
  const comDuda = [...PESSOAS, { id: "u4", nome: "Duda Antiga", email: null, ativo: true, papeis: [PAPEIS[1]], situacao: "aguardando_primeiro_acesso" }];
  await abrir({ lista: comDuda });
  botao("Editar", linhas()[1]).click();
  let dlg = raiz.querySelector("dialog");
  assert.equal(dlg.querySelector('input[name="email"]').value, "beto@mdca.org.br");
  dlg.querySelector('input[name="nome"]').value = "Beto Silva";
  respostas = [[200, { ...PESSOAS[1], nome: "Beto Silva" }], [200, comDuda], [200, PAPEIS]];
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.deepEqual(JSON.parse(chamadas[0].body), { nome: "Beto Silva" });

  botao("Editar", linhas()[3]).click();
  dlg = raiz.querySelector("dialog");
  assert.equal(dlg.querySelector('input[name="email"]').value, "");
  dlg.querySelector('input[name="email"]').value = "  duda@mdca.org.br ";
  respostas = [[409, { detail: "Já existe uma pessoa com este e-mail." }]];
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar(20);
  assert.equal(chamadas[0].url, `${API}/admin/usuarios/u4`);
  assert.deepEqual(JSON.parse(chamadas[0].body), { email: "duda@mdca.org.br" });
  assert.match(raiz.querySelector("dialog").textContent, /Já existe uma pessoa com este e-mail\./);
});

test("Editar não aceita e-mail apagado", async () => {
  sessaoDe(ADMIN);
  await abrir();
  botao("Editar", linhas()[1]).click();
  const dlg = raiz.querySelector("dialog");
  dlg.querySelector('input[name="email"]').value = " ";
  chamadas = [];
  enviar(dlg.querySelector("form"));
  await esperar();
  assert.equal(chamadas.length, 0);
  assert.match(dlg.textContent, /Informe o e-mail\./);
});

// — Gerar código: um pedido por vez e sem diálogo de erro no 401 —

test("Gerar código fica desabilitado durante o pedido", async () => {
  sessaoDe(ADMIN);
  await abrir();
  let liberar;
  const antes = globalThis.fetch;
  globalThis.fetch = (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    return new Promise((ok) => (liberar = () => ok(new Response(JSON.stringify({ codigo: "QQQQ-1111", codigo_expira_em: "2026-11-07T15:05:00Z" }), { status: 200 }))));
  };
  try {
    chamadas = [];
    const b = botao("Gerar código", linhas()[1]);
    b.click();
    assert.equal(b.disabled, true);
    b.click();
    await esperar();
    assert.equal(chamadas.length, 1, "segundo clique não gera outro código");
    globalThis.fetch = antes;
    respostas = [[200, PESSOAS], [200, PAPEIS]];
    liberar();
    await esperar(20);
    assert.match(raiz.querySelector("dialog").textContent, /QQQQ-1111/);
  } finally {
    globalThis.fetch = antes;
  }
});

test("Gerar código com sessão vencida (401) redireciona sem abrir diálogo de erro", async () => {
  sessaoDe(ADMIN);
  await abrir();
  respostas = [[401, { detail: "Autenticação obrigatória." }]];
  botao("Gerar código", linhas()[1]).click();
  await esperar(20);
  assert.equal(destino, "../");
  assert.equal(raiz.querySelector("dialog"), null);
});
