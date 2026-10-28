// Redesign Financeiro · celular do educador — testes da TELA de verdade.
//
// Carrega Frontend/Financeiro/lancamento/index.html + lancamento.js num
// navegador simulado (jsdom), com a API simulada em memória, e percorre o
// fluxo "fotografa agora, completa depois" como o educador faria.
//
// Rodar em Frontend/Financeiro:  npm install  (uma vez)  e  node --test

import { afterEach, describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { esquecerAcesso } from "../base/api.js";

let JSDOM = null;
try {
  ({ JSDOM } = await import("jsdom"));
} catch {
  /* sem jsdom: os testes abaixo são pulados com aviso */
}
const SEM_JSDOM = JSDOM ? false : "jsdom não instalado — rode `npm install` em Frontend/Financeiro";

const HTML = await readFile(new URL("../lancamento/index.html", import.meta.url), "utf8");
const API = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";
const SESSAO_EDUCADOR = JSON.stringify({ papel: "educador", nome: "Marcos Vieira" });

function orcamento(id, projeto_nome, categorias = ["Materiais", "Alimentação", "Transporte"]) {
  return { id, projeto_id: `p-${id}`, projeto_nome, data_inicio: "2026-01-01", data_fim: "2026-12-31", categorias_despesa: categorias };
}

function dadosIniciais() {
  return {
    orcamentos: [orcamento("orc-leitura", "Leitura"), orcamento("orc-esporte", "Esporte")],
    lancamentos: [
      { id: "l1", orcamento_id: "orc-leitura", projeto_id: "p-orc-leitura", valor: 180, descricao: "Livros", categoria: "Materiais", data_despesa: "2026-10-22", status: "aprovado", motivo_rejeicao: null, comprovante_url: "/comprovantes/2026/10/a.jpg", criado_em: "2026-10-22T12:00:00Z" },
      { id: "l2", orcamento_id: "orc-esporte", projeto_id: "p-orc-esporte", valor: 64, descricao: "Lanche do treino", categoria: "Alimentação", data_despesa: "2026-10-23", status: "rejeitado", motivo_rejeicao: "A nota está cortada.", comprovante_url: "/comprovantes/2026/10/b.jpg", criado_em: "2026-10-23T12:00:00Z" },
      { id: "l3", orcamento_id: "orc-leitura", projeto_id: "p-orc-leitura", valor: 45, descricao: "Ônibus", categoria: "Transporte", data_despesa: "2026-10-24", status: "pendente", motivo_rejeicao: null, comprovante_url: "/comprovantes/2026/10/c.jpg", criado_em: "2026-10-24T12:00:00Z" },
    ],
    rascunhos: [
      { id: "r1", criado_em: "2026-10-20T13:42:00Z", comprovante_url: "/comprovantes/2026/10/r1.jpg", nome_original: "r1.jpg", content_type: "image/jpeg", tamanho: 10 },
    ],
    notificacoes: [
      { id: "n1", lancamento_id: "l2", tipo: "lancamento_rejeitado", mensagem: "Lançamento de R$ 64,00 foi rejeitado. Motivo: A nota está cortada.", motivo: "A nota está cortada.", lida: false, criada_em: "2026-10-25T12:00:00Z" },
    ],
  };
}

let versao = 0;
let janelaAberta = null;

afterEach(() => {
  janelaAberta?.close(); // encerra os temporizadores da página
  janelaAberta = null;
});

async function esperar(condicao, descricao = "condição", limiteMs = 2000) {
  const inicio = Date.now();
  while (!condicao()) {
    if (Date.now() - inicio > limiteMs) throw new Error(`Tempo esgotado esperando: ${descricao}`);
    await new Promise((ok) => setTimeout(ok, 5));
  }
}

const json = (corpo, status = 200) => new Response(JSON.stringify(corpo), { status });

/** Abre a página com a API simulada. `responder(metodo, caminho)` pode sobrepor uma rota. */
async function abrirTela({ sessao = SESSAO_EDUCADOR, token = "token-de-teste", hash = "", dados = dadosIniciais(), responder } = {}) {
  esquecerAcesso();
  const dom = new JSDOM(HTML, { url: `https://mdca-sistema.pages.dev/Financeiro/lancamento/${hash}` });
  const { window } = dom;
  janelaAberta = window;
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.scrollTo = () => {};
  if (token) window.localStorage.setItem("mdca.financeiro.token", token);
  if (sessao) window.localStorage.setItem("mdca.financeiro.sessao.celular", sessao);

  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.localStorage = window.localStorage;

  const chamadas = [];
  globalThis.fetch = async (url, opcoes = {}) => {
    const metodo = opcoes.method || "GET";
    const caminho = url.replace(API, "").split("?")[0];
    chamadas.push({ url, caminho, metodo, headers: opcoes.headers || {}, corpo: opcoes.body });
    const sobreposta = await responder?.(metodo, caminho);
    if (sobreposta) return json(sobreposta.corpo, sobreposta.status);

    if (metodo === "GET" && caminho === "/orcamentos") return json(dados.orcamentos);
    if (metodo === "GET" && caminho === "/lancamentos") return json(dados.lancamentos);
    if (metodo === "GET" && caminho === "/rascunhos") return json(dados.rascunhos);
    if (metodo === "GET" && caminho === "/notificacoes") return json(dados.notificacoes);
    if (metodo === "GET" && caminho.startsWith("/comprovantes/")) {
      return new Response(new Blob([new Uint8Array(4)], { type: "image/jpeg" }), { status: 200 });
    }
    if (metodo === "POST" && caminho === "/rascunhos") {
      const novo = { id: "r-novo", criado_em: new Date().toISOString(), comprovante_url: "/comprovantes/2026/10/novo.jpg", content_type: "image/jpeg" };
      dados.rascunhos = [novo, ...dados.rascunhos];
      return json(novo, 201);
    }
    let achado = caminho.match(/^\/rascunhos\/([^/]+)\/completar$/);
    if (metodo === "POST" && achado) {
      dados.rascunhos = dados.rascunhos.filter((r) => r.id !== achado[1]);
      return json({ id: "l-novo", status: "pendente" }, 201);
    }
    achado = caminho.match(/^\/lancamentos\/([^/]+)$/);
    if (metodo === "GET" && achado) {
      const l = dados.lancamentos.find((x) => x.id === achado[1]);
      return l ? json({ ...l, motivos_rejeicao_anteriores: [] }) : json({ detail: "Lançamento não encontrado" }, 404);
    }
    achado = caminho.match(/^\/lancamentos\/([^/]+)\/reenviar$/);
    if (metodo === "PATCH" && achado) {
      const l = dados.lancamentos.find((x) => x.id === achado[1]);
      l.status = "pendente";
      return json({ ...l, motivos_rejeicao_anteriores: ["A nota está cortada."] });
    }
    if (metodo === "PATCH" && /^\/notificacoes\/[^/]+\/lida$/.test(caminho)) return json({});
    return json({ detail: "rota não simulada" }, 404);
  };

  versao += 1;
  await import(`../lancamento/lancamento.js?tela=${versao}`);

  const $ = (id) => window.document.getElementById(id);
  const texto = () => window.document.getElementById("tela").textContent;
  return { window, $, texto, chamadas, dados, de: (metodo, caminho) => chamadas.filter((c) => c.metodo === metodo && c.caminho === caminho) };
}

async function irPara(tela, hash) {
  tela.window.location.hash = hash;
  await new Promise((ok) => setTimeout(ok, 0));
}

function digitar(tela, id, valor) {
  const campo = tela.$(id);
  campo.value = valor;
  campo.dispatchEvent(new tela.window.Event("input", { bubbles: true }));
}

function botaoComTexto(tela, texto) {
  return [...tela.window.document.querySelectorAll("button")].find((b) => b.textContent === texto);
}

async function enviarFormulario(tela, id) {
  tela.$(id).dispatchEvent(new tela.window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((ok) => setTimeout(ok, 20));
}

// --- Primeiro acesso ---------------------------------------------------------

describe("primeiro acesso", { skip: SEM_JSDOM }, () => {
  test("sem sessão: pede nome e código, salva como educador e abre Minhas despesas", async () => {
    const tela = await abrirTela({ sessao: null, token: null });
    await esperar(() => tela.$("form-acesso"), "tela de primeiro acesso");
    assert.equal(tela.$("abas").hidden, true);
    assert.equal(tela.de("GET", "/lancamentos").length, 0);

    digitar(tela, "campo-nome", " Marcos Vieira ");
    digitar(tela, "campo-token", "codigo-secreto");
    await enviarFormulario(tela, "form-acesso");
    await esperar(() => tela.$("secao-enviadas"), "Minhas despesas");

    assert.deepEqual(JSON.parse(tela.window.localStorage.getItem("mdca.financeiro.sessao.celular")), { papel: "educador", nome: "Marcos Vieira" });
    const [chamada] = tela.de("GET", "/lancamentos");
    assert.equal(chamada.headers.Authorization, "Bearer codigo-secreto");
    assert.equal(chamada.headers["X-Papel-Usuario"], "educador");
    assert.equal(chamada.headers["X-Usuario-Id"], "marcos-vieira");
  });

  test("sem nome não entra", async () => {
    const tela = await abrirTela({ sessao: null, token: null });
    await esperar(() => tela.$("form-acesso"), "tela de primeiro acesso");
    digitar(tela, "campo-token", "codigo");
    await enviarFormulario(tela, "form-acesso");
    assert.equal(tela.$("erro-acesso").textContent, "Informe seu nome.");
    assert.equal(tela.window.localStorage.getItem("mdca.financeiro.sessao.celular"), null);
  });

  test("sessão de outro papel (coordenação) também cai no primeiro acesso", async () => {
    const tela = await abrirTela({ sessao: JSON.stringify({ papel: "coordenacao", nome: "Luana" }) });
    await esperar(() => tela.$("form-acesso"), "tela de primeiro acesso");
    assert.equal(tela.$("campo-nome").value, "");
  });

  test("código recusado pela API volta ao primeiro acesso com o nome preenchido", async () => {
    const tela = await abrirTela({ responder: () => ({ status: 401, corpo: { detail: "Autenticação obrigatória." } }) });
    await esperar(() => tela.$("form-acesso"), "tela de primeiro acesso");
    assert.match(tela.$("erro-acesso").textContent, /inválido/);
    assert.equal(tela.$("campo-nome").value, "Marcos Vieira");
  });
});

// --- Minhas despesas ---------------------------------------------------------

describe("Minhas despesas", { skip: SEM_JSDOM }, () => {
  test("ajuste no topo, depois a completar, depois enviadas (mais recentes primeiro)", async () => {
    const tela = await abrirTela();
    await esperar(() => tela.$("secao-enviadas"), "Minhas despesas");

    const secoes = [...tela.window.document.querySelectorAll("section")].map((s) => s.id);
    assert.deepEqual(secoes, ["secao-ajuste", "secao-completar", "secao-enviadas"]);
    assert.match(tela.$("secao-ajuste").textContent, /Precisa de ajuste \(1\)/);
    assert.match(tela.$("secao-ajuste").textContent, /Alimentação.*Esporte · 23\/10.*R\$\s?64,00.*Rejeitada/);
    assert.match(tela.$("secao-completar").textContent, /A completar \(1\)/);
    const enviadas = [...tela.$("secao-enviadas").querySelectorAll(".item")].map((a) => a.textContent);
    assert.match(enviadas[0], /Transporte.*Leitura · 24\/10.*Em análise/);
    assert.match(enviadas[1], /Materiais.*Leitura · 22\/10.*Aprovada/);
    assert.equal(tela.$("abas").hidden, false);
    assert.equal(tela.window.document.querySelector('[data-aba="despesas"]').getAttribute("aria-current"), "page");
  });

  test("'Ver todas' só aparece com mais de 5 enviadas e mostra todas", async () => {
    const dados = dadosIniciais();
    dados.lancamentos = [1, 2, 3, 4, 5, 6, 7].map((n) => ({ ...dados.lancamentos[0], id: `x${n}`, criado_em: `2026-10-0${n}T10:00:00Z` }));
    const tela = await abrirTela({ dados });
    await esperar(() => tela.$("secao-enviadas"), "Minhas despesas");
    assert.equal(tela.$("secao-enviadas").querySelectorAll(".item").length, 5);

    botaoComTexto(tela, "Ver todas").click();
    await esperar(() => tela.$("secao-enviadas")?.querySelectorAll(".item").length === 7, "todas as enviadas");
    assert.equal(botaoComTexto(tela, "Ver todas"), undefined);
  });
});

// --- Câmera e completar ------------------------------------------------------

describe("fotografar e completar", { skip: SEM_JSDOM }, () => {
  test("a foto vira rascunho e o aviso oferece 'Completar agora'", async () => {
    const tela = await abrirTela();
    await esperar(() => tela.$("secao-enviadas"), "Minhas despesas");
    assert.equal(tela.$("campo-camera").getAttribute("capture"), "environment");
    assert.equal(tela.$("campo-camera").getAttribute("accept"), "image/*,application/pdf");

    const foto = new File([new Uint8Array(2048)], "nota.jpg", { type: "image/jpeg" });
    Object.defineProperty(tela.$("campo-camera"), "files", { value: [foto], configurable: true });
    tela.$("campo-camera").dispatchEvent(new tela.window.Event("change"));
    await esperar(() => /A completar/.test(tela.$("aviso-flutuante").textContent), "aviso da foto");

    const [envio] = tela.de("POST", "/rascunhos");
    assert.equal(envio.corpo.get("comprovante").name, "nota.jpg");
    assert.match(tela.$("aviso-flutuante").textContent, /Foto salva em "A completar"/);
    const acao = tela.$("aviso-flutuante").querySelector("a");
    assert.equal(acao.textContent, "Completar agora");
    assert.equal(acao.getAttribute("href"), "#/completar/r-novo");
    await esperar(() => /A completar \(2\)/.test(tela.$("secao-completar")?.textContent || ""), "lista atualizada");
  });

  test("arquivo que não é foto nem PDF não é enviado", async () => {
    const tela = await abrirTela();
    await esperar(() => tela.$("secao-enviadas"), "Minhas despesas");
    const doc = new File([new Uint8Array(10)], "nota.docx", { type: "application/msword" });
    Object.defineProperty(tela.$("campo-galeria"), "files", { value: [doc], configurable: true });
    tela.$("campo-galeria").dispatchEvent(new tela.window.Event("change"));
    await esperar(() => !tela.$("aviso-flutuante").hidden, "aviso");
    assert.match(tela.$("aviso-flutuante").textContent, /foto|PDF/);
    assert.equal(tela.de("POST", "/rascunhos").length, 0);
  });

  test("completar: data da foto, último projeto usado, categoria por botão, envia sem a foto", async () => {
    const tela = await abrirTela({ hash: "#/completar/r1" });
    await esperar(() => tela.$("form-despesa"), "formulário de completar");

    const criada = new Date("2026-10-20T13:42:00Z");
    const esperada = `${criada.getFullYear()}-${String(criada.getMonth() + 1).padStart(2, "0")}-${String(criada.getDate()).padStart(2, "0")}`;
    assert.equal(tela.$("campo-data").value, esperada);
    assert.equal(tela.$("campo-projeto").value, "orc-leitura"); // l3 é a mais recente
    assert.equal(tela.$("abas").hidden, true);
    const categorias = [...tela.$("campo-categoria").querySelectorAll("button")];
    assert.deepEqual(categorias.map((b) => b.textContent), ["Materiais", "Alimentação", "Transporte"]);

    categorias[0].click();
    assert.equal(tela.$("campo-categoria").querySelector("[aria-pressed=true]").textContent, "Materiais");
    digitar(tela, "campo-valor", "180,00");
    digitar(tela, "campo-descricao", "  Livros para a oficina ");
    await enviarFormulario(tela, "form-despesa");
    await esperar(() => tela.window.location.hash === "#/", "volta para Minhas despesas");

    const [envio] = tela.de("POST", "/rascunhos/r1/completar");
    assert.equal(envio.corpo.get("orcamento_id"), "orc-leitura");
    assert.equal(envio.corpo.get("categoria"), "Materiais");
    assert.equal(envio.corpo.get("valor"), "180.00");
    assert.equal(envio.corpo.get("descricao"), "Livros para a oficina");
    assert.equal(envio.corpo.get("data_despesa"), esperada);
    assert.equal(envio.corpo.has("comprovante"), false);
    assert.equal(tela.$("aviso-flutuante").textContent, "Despesa enviada para aprovação");

    tela.window.location.hash = "#/avisos";
    await esperar(() => tela.$("aviso-flutuante").hidden, "aviso some ao trocar de aba");
  });

  test("completar sem valor e sem categoria não envia e aponta os campos", async () => {
    const tela = await abrirTela({ hash: "#/completar/r1" });
    await esperar(() => tela.$("form-despesa"), "formulário de completar");
    digitar(tela, "campo-descricao", "Livros");
    await enviarFormulario(tela, "form-despesa");

    assert.equal(tela.de("POST", "/rascunhos/r1/completar").length, 0);
    assert.equal(tela.$("erro-valor").hidden, false);
    assert.equal(tela.$("erro-categoria").hidden, false);
    assert.equal(tela.$("erro-descricao").hidden, true);
  });

  test("erro da API aparece no formulário e não sai da tela", async () => {
    const tela = await abrirTela({
      hash: "#/completar/r1",
      responder: (metodo, caminho) => (metodo === "POST" && caminho.endsWith("/completar") ? { status: 400, corpo: { detail: "Saldo insuficiente." } } : null),
    });
    await esperar(() => tela.$("form-despesa"), "formulário de completar");
    tela.$("campo-categoria").querySelector("button").click();
    digitar(tela, "campo-valor", "10");
    digitar(tela, "campo-descricao", "Livros");
    await enviarFormulario(tela, "form-despesa");

    await esperar(() => !tela.$("aviso-geral").hidden, "aviso de erro");
    assert.equal(tela.$("aviso-geral").textContent, "Saldo insuficiente.");
    assert.equal(tela.window.location.hash, "#/completar/r1");
  });
});

// --- Rejeitada ---------------------------------------------------------------

describe("despesa rejeitada", { skip: SEM_JSDOM }, () => {
  test("mostra o motivo em destaque e 'Corrigir e reenviar'", async () => {
    const tela = await abrirTela({ hash: "#/despesa/l2" });
    await esperar(() => tela.$("motivo-rejeicao"), "motivo");
    assert.match(tela.$("motivo-rejeicao").textContent, /Motivo informado pela coordenação.*A nota está cortada\./);
    assert.match(tela.texto(), /Alimentação · Esporte/);
    assert.match(tela.texto(), /Lanche do treino · 23\/10\/2026/);
    assert.equal(tela.$("botao-corrigir").getAttribute("href"), "#/corrigir/l2");
  });

  test("despesa aprovada não oferece reenviar", async () => {
    const tela = await abrirTela({ hash: "#/despesa/l1" });
    await esperar(() => tela.window.document.querySelector(".despesa"), "despesa");
    assert.equal(tela.$("motivo-rejeicao"), null);
    assert.equal(tela.$("botao-corrigir"), null);
  });

  test("corrigir abre o formulário preenchido e reenvia pelo PATCH", async () => {
    const tela = await abrirTela({ hash: "#/corrigir/l2" });
    await esperar(() => tela.$("form-despesa"), "formulário de correção");

    assert.equal(tela.$("campo-valor").value, "64,00");
    assert.equal(tela.$("campo-descricao").value, "Lanche do treino");
    assert.equal(tela.$("campo-data").value, "2026-10-23");
    assert.equal(tela.$("campo-projeto").value, "orc-esporte");
    assert.equal(tela.$("campo-projeto").disabled, true);
    assert.equal(tela.$("campo-categoria").querySelector("[aria-pressed=true]").textContent, "Alimentação");

    digitar(tela, "campo-descricao", "Lanche do treino de sábado");
    await enviarFormulario(tela, "form-despesa");
    await esperar(() => tela.window.location.hash === "#/", "volta para Minhas despesas");

    const [envio] = tela.de("PATCH", "/lancamentos/l2/reenviar");
    assert.equal(envio.corpo.get("descricao"), "Lanche do treino de sábado");
    assert.equal(envio.corpo.get("valor"), "64.00");
    assert.equal(envio.corpo.get("categoria"), "Alimentação");
    assert.equal(envio.corpo.has("comprovante"), false);
  });

  test("ao corrigir, 'Trocar foto' manda a foto nova junto", async () => {
    const tela = await abrirTela({ hash: "#/corrigir/l2" });
    await esperar(() => tela.$("form-despesa"), "formulário de correção");
    const foto = new File([new Uint8Array(100)], "nova.jpg", { type: "image/jpeg" });
    Object.defineProperty(tela.$("campo-foto"), "files", { value: [foto], configurable: true });
    tela.$("campo-foto").dispatchEvent(new tela.window.Event("change"));
    await new Promise((ok) => setTimeout(ok, 10));

    await enviarFormulario(tela, "form-despesa");
    await esperar(() => tela.de("PATCH", "/lancamentos/l2/reenviar").length === 1, "reenvio");
    assert.equal(tela.de("PATCH", "/lancamentos/l2/reenviar")[0].corpo.get("comprovante").name, "nova.jpg");
  });
});

// --- Avisos e perfil ---------------------------------------------------------

describe("avisos e perfil", { skip: SEM_JSDOM }, () => {
  test("avisos lista as notificações e marca as novas como lidas", async () => {
    const tela = await abrirTela({ hash: "#/avisos" });
    await esperar(() => tela.window.document.querySelector(".item--aviso"), "avisos");
    assert.match(tela.texto(), /foi rejeitado\. Motivo: A nota está cortada\./);
    assert.equal(tela.window.document.querySelector(".item--aviso").getAttribute("href"), "#/despesa/l2");
    await esperar(() => tela.de("PATCH", "/notificacoes/n1/lida").length === 1, "marcar como lida");
  });

  test("perfil mostra o nome e 'Sair' volta ao primeiro acesso", async () => {
    const tela = await abrirTela({ hash: "#/perfil" });
    await esperar(() => tela.$("perfil-nome"), "perfil");
    assert.equal(tela.$("perfil-nome").textContent, "Marcos Vieira");

    tela.$("botao-sair").click();
    await esperar(() => tela.$("form-acesso"), "primeiro acesso");
    assert.equal(tela.window.localStorage.getItem("mdca.financeiro.sessao.celular"), null);
    assert.equal(tela.window.localStorage.getItem("mdca.financeiro.token"), null);
  });
});
