// T-31 · US-07: testes de componente dos filtros do Painel da Diretoria (período e
// situação). A tela é montada no jsdom e a API simulada aplica os filtros sobre os
// mesmos dados, como o backend: assim o teste confere o que a tela pede E o que ela exibe.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const painel = await import("../telas/painel.js");

const container = () => document.getElementById("c");
const esperar = () => new Promise((r) => setTimeout(r, 15));
const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo });

// Três projetos: dois ativos e um encerrado, com despesas aprovadas em datas diferentes.
const PROJETOS = [
  {
    projeto_id: "p-div",
    nome: "Divertidamente",
    status: "ativo",
    orcamento: { inicio: "2026-01-01", fim: "2026-12-31", valor: 24000 },
    aprovados: [
      { data: "2026-03-12", valor: 180 },
      { data: "2026-03-28", valor: 645.3 },
      { data: "2026-04-09", valor: 96 },
      { data: "2026-11-11", valor: 87.5 },
    ],
  },
  {
    projeto_id: "p-ado",
    nome: "Adolescer",
    status: "ativo",
    orcamento: { inicio: "2026-01-01", fim: "2026-12-31", valor: 18000 },
    aprovados: [{ data: "2026-08-20", valor: 1200 }],
  },
  {
    projeto_id: "p-ant",
    nome: "Oficina antiga",
    status: "encerrado",
    orcamento: { inicio: "2025-01-01", fim: "2025-12-31", valor: 5000 },
    aprovados: [{ data: "2025-06-10", valor: 4800 }],
  },
];

/** O que o backend faria (Backend/Financeiro/dashboard.py), em centavos. */
function servidor(params) {
  const inicio = params.get("data_inicio") || "";
  const fim = params.get("data_fim") || "";
  const status = params.get("status") || "";
  const noPeriodo = (dia) => (!inicio || dia >= inicio) && (!fim || dia <= fim);
  const cruza = (o) => (!fim || o.inicio <= fim) && (!inicio || o.fim >= inicio);
  return PROJETOS.filter((p) => !status || p.status === status).map((p) => {
    const orcado = cruza(p.orcamento) ? p.orcamento.valor * 100 : 0;
    const realizado = p.aprovados.filter((l) => noPeriodo(l.data)).reduce((t, l) => t + Math.round(l.valor * 100), 0);
    return { projeto_id: p.projeto_id, nome: p.nome, status: p.status, orcado: orcado / 100, realizado: realizado / 100, saldo: (orcado - realizado) / 100 };
  });
}

let chamadas;
let falha = null;
function simular() {
  chamadas = [];
  falha = null;
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    chamadas.push({ caminho: u.pathname, params: Object.fromEntries(u.searchParams) });
    if (falha) return falha;
    return resposta(200, servidor(u.searchParams));
  };
}

/** Linhas da tabela: [nome, situação, orçado, realizado, saldo]. */
const linhas = () =>
  [...container().querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")].slice(0, 5).map((td) => td.textContent.replace(/\s/g, " ")));
const nomes = () => linhas().map((l) => l[0]);
const totaisNaTela = () => [...container().querySelectorAll(".caixa .num")].slice(0, 3).map((n) => n.textContent.replace(/\s/g, " "));
const botao = (texto) => [...container().querySelectorAll("button")].find((b) => b.textContent === texto);
async function aplicarPeriodo(inicio, fim) {
  container().querySelector("#painel-inicio").value = inicio;
  container().querySelector("#painel-fim").value = fim;
  container().querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
}

test("abre com todos os projetos e todo o período: um pedido sem filtros", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });

  assert.deepEqual(chamadas, [{ caminho: "/dashboard/projetos", params: {} }]);
  assert.deepEqual(nomes(), ["Adolescer", "Divertidamente", "Oficina antiga"]);
  assert.match(container().querySelector(".painel-descricao").textContent, /Todos os projetos · todo o período/);
  assert.equal(botao("Todos").getAttribute("aria-pressed"), "true");
  assert.deepEqual(totaisNaTela(), ["R$ 47.000,00", "R$ 7.008,80", "R$ 39.991,20"]);
});

test("filtro de período: manda as datas e os valores exibidos mudam para o período", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });
  const antes = linhas().find((l) => l[0] === "Divertidamente");
  assert.deepEqual(antes.slice(2), ["R$ 24.000,00", "R$ 1.008,80", "R$ 22.991,20"]);

  await aplicarPeriodo("2026-03-01", "2026-03-31");

  assert.deepEqual(chamadas.at(-1).params, { data_inicio: "2026-03-01", data_fim: "2026-03-31" });
  const depois = linhas().find((l) => l[0] === "Divertidamente");
  assert.deepEqual(depois.slice(2), ["R$ 24.000,00", "R$ 825,30", "R$ 23.174,70"], "só as despesas de março entram no realizado");
  assert.deepEqual(linhas().find((l) => l[0] === "Adolescer").slice(2), ["R$ 18.000,00", "R$ 0,00", "R$ 18.000,00"]);
  // O orçamento de 2025 não cruza março de 2026: o projeto aparece zerado.
  assert.deepEqual(linhas().find((l) => l[0] === "Oficina antiga").slice(2), ["R$ 0,00", "R$ 0,00", "R$ 0,00"]);
  assert.deepEqual(totaisNaTela(), ["R$ 42.000,00", "R$ 825,30", "R$ 41.174,70"]);
  assert.match(container().querySelector(".painel-descricao").textContent, /de 01\/03\/2026 a 31\/03\/2026/);
});

test("filtro de período com uma ponta só e volta para todo o período", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });
  await aplicarPeriodo("2026-04-01", "");
  assert.deepEqual(chamadas.at(-1).params, { data_inicio: "2026-04-01" });
  assert.deepEqual(linhas().find((l) => l[0] === "Divertidamente").slice(3), ["R$ 183,50", "R$ 23.816,50"]);
  assert.match(container().querySelector(".painel-descricao").textContent, /a partir de 01\/04\/2026/);

  botao("Todo o período").click();
  await esperar();
  assert.deepEqual(chamadas.at(-1).params, {});
  assert.equal(container().querySelector("#painel-inicio").value, "");
  assert.deepEqual(linhas().find((l) => l[0] === "Divertidamente").slice(3), ["R$ 1.008,80", "R$ 22.991,20"]);
});

test("filtro de situação \"ativo\": mostra apenas os projetos ativos", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });

  botao("Ativos").click();
  await esperar();

  assert.deepEqual(chamadas.at(-1).params, { status: "ativo" });
  assert.deepEqual(nomes(), ["Adolescer", "Divertidamente"]);
  assert.ok(linhas().every((l) => l[1] === "Ativo"));
  assert.equal(botao("Ativos").getAttribute("aria-pressed"), "true");
  assert.equal(botao("Todos").getAttribute("aria-pressed"), "false");
  assert.deepEqual(totaisNaTela(), ["R$ 42.000,00", "R$ 2.208,80", "R$ 39.791,20"]);
});

test("filtro de situação \"encerrado\": mostra apenas os projetos encerrados", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });

  botao("Encerrados").click();
  await esperar();

  assert.deepEqual(chamadas.at(-1).params, { status: "encerrado" });
  assert.deepEqual(nomes(), ["Oficina antiga"]);
  assert.deepEqual(linhas()[0].slice(1), ["Encerrado", "R$ 5.000,00", "R$ 4.800,00", "R$ 200,00"]);
  assert.match(container().querySelector(".painel-descricao").textContent, /Projetos encerrados/);
});

test("período e situação juntos: os dois filtros vão no mesmo pedido", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });
  botao("Ativos").click();
  await esperar();
  await aplicarPeriodo("2026-08-01", "2026-08-31");

  assert.deepEqual(chamadas.at(-1).params, { data_inicio: "2026-08-01", data_fim: "2026-08-31", status: "ativo" });
  assert.deepEqual(nomes(), ["Adolescer", "Divertidamente"]);
  assert.deepEqual(linhas().find((l) => l[0] === "Adolescer").slice(3), ["R$ 1.200,00", "R$ 16.800,00"]);
  assert.deepEqual(linhas().find((l) => l[0] === "Divertidamente").slice(3), ["R$ 0,00", "R$ 24.000,00"]);
});

test("os filtros podem vir na rota (#/painel?inicio=…&fim=…&situacao=…)", async () => {
  simular();
  await painel.mostrar(container(), { parametros: { inicio: "2025-01-01", fim: "2025-12-31", situacao: "encerrado" } });
  assert.deepEqual(chamadas, [{ caminho: "/dashboard/projetos", params: { data_inicio: "2025-01-01", data_fim: "2025-12-31", status: "encerrado" } }]);
  assert.deepEqual(nomes(), ["Oficina antiga"]);

  simular();
  await painel.mostrar(container(), { parametros: { inicio: "ontem", situacao: "qualquer" } });
  assert.deepEqual(chamadas.at(-1).params, {}, "valores inválidos na rota são ignorados");
});

test("período invertido: avisa e não faz o pedido", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });
  const antes = chamadas.length;
  await aplicarPeriodo("2026-06-30", "2026-06-01");

  assert.equal(chamadas.length, antes);
  assert.match(container().querySelector('[role="alert"]').textContent, /O fim do período não pode ser antes do início/);
  assert.deepEqual(nomes(), ["Adolescer", "Divertidamente", "Oficina antiga"], "a tabela anterior continua");
});

test("filtro sem resultado e erro do servidor aparecem na tela", async () => {
  simular();
  globalThis.fetch = async () => resposta(200, []);
  await painel.mostrar(container(), { parametros: { situacao: "encerrado" } });
  assert.match(container().textContent, /Nenhum projeto encerrado\./);

  simular();
  falha = resposta(403, { detail: "Ação permitida apenas para: direcao." });
  await painel.mostrar(container(), { parametros: {} });
  assert.match(container().querySelector(".aviso-tela").textContent, /Ação permitida apenas para: direcao\./);
});

test("resposta atrasada de um filtro antigo não sobrescreve a do filtro novo", async () => {
  simular();
  await painel.mostrar(container(), { parametros: {} });
  let liberarAntiga;
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    if (u.searchParams.get("status") === "ativo") await new Promise((r) => (liberarAntiga = r));
    return resposta(200, servidor(u.searchParams));
  };
  botao("Ativos").click();
  botao("Encerrados").click();
  await esperar();
  liberarAntiga();
  await esperar();
  assert.deepEqual(nomes(), ["Oficina antiga"]);
});

test("nome do projeto entra como texto; projeto sem orçamento no período aparece assim", async () => {
  simular();
  globalThis.fetch = async () => resposta(200, [{ projeto_id: "p-1", nome: "<b>Horta</b>", status: "ativo", orcado: 0, realizado: 0, saldo: 0 }]);
  await painel.mostrar(container(), { parametros: {} });
  assert.equal(container().querySelector("tbody b"), null);
  assert.equal(linhas()[0][0], "<b>Horta</b>");
  assert.match(container().querySelector("tbody").textContent, /Sem orçamento/);
});
