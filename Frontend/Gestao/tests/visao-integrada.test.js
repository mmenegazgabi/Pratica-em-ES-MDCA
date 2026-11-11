// Visão integrada (T-79 · US-12): física e financeira juntas, filtro de período, papel sem
// valores financeiros e programa sem orçamento (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarVisaoIntegrada, periodoDescrito } = await import("../telas/visao-integrada.js");
const { obterVisaoIntegrada } = await import("../base/api.js");

const PROGRAMAS = [
  { id: "p-1", nome: "Semear", identificador: "SEMEAR" },
  { id: "p-2", nome: "Oficina", identificador: null },
];
const FISICA = {
  metas: [
    { meta_id: "m-1", descricao: "Famílias", unidade: "famílias", acao_id: "a-1", acao: "Encontros", objetivo_id: "o-1", objetivo: "Vínculos", planejado: 40, realizado: 30, percentual: 75 },
  ],
  percentual_medio: 75,
};
const FINANCEIRA = {
  vinculo: "id",
  projeto_id: "p-1",
  projeto: "Semear",
  orcado: 10000,
  realizado: 2500,
  saldo: 7500,
  percentual_executado: 25,
};
const visao = (programaId, extra = {}) => ({
  programa: PROGRAMAS.find((p) => p.id === programaId),
  inicio: null,
  fim: null,
  fisica: FISICA,
  financeira: FINANCEIRA,
  ...extra,
});

let container;
let consultas;
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = () => new Promise((r) => setTimeout(r, 0));
const campo = (nome) => container.querySelector(`[name="${nome}"]`);
const enviar = async () => {
  container.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  await esperar();
};

function api(responder = (id, filtros) => visao(id, { inicio: filtros.inicio || null, fim: filtros.fim || null })) {
  return {
    listarProgramas: async () => PROGRAMAS,
    obterVisaoIntegrada: async (id, filtros) => {
      consultas.push([id, filtros]);
      return responder(id, filtros);
    },
  };
}

async function abrir(opcoes) {
  await mostrarVisaoIntegrada(container, opcoes);
  await esperar();
  await esperar();
}

beforeEach(() => {
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
  consultas = [];
});

test("o cliente da API manda o período só quando informado", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "sessao-de-teste", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "ana", nome: "Ana Martins", papeis: [] } }));
  const chamadas = [];
  globalThis.fetch = async (url) => {
    chamadas.push(url);
    return new Response("{}", { status: 200 });
  };
  await obterVisaoIntegrada("p 1", {});
  await obterVisaoIntegrada("p-1", { inicio: "2026-01-01", fim: "2026-06-30" });

  assert.match(chamadas[0], /\/gestao\/programas\/p%201\/visao-integrada$/);
  assert.match(chamadas[1], /\/visao-integrada\?inicio=2026-01-01&fim=2026-06-30$/);
});

test("mostra a execução física e a financeira do primeiro programa", async () => {
  await abrir(api());

  assert.deepEqual(consultas, [["p-1", { inicio: "", fim: "" }]]);
  assert.match(texto(), /SemearSEMEAR · todo o período/);
  assert.match(texto(), /Execução física/);
  assert.match(texto(), /Famílias.*40 famílias.*30 famílias.*75%/);
  assert.match(texto(), /Orçado.*R\$\s?10\.000,00/);
  assert.match(texto(), /Saldo.*R\$\s?7\.500,00/);
  assert.match(texto(), /Executado do orçamento.*25%/);
});

test("abre direto no programa pedido pela rota", async () => {
  await abrir({ programaInicial: "p-2", ...api() });

  assert.equal(consultas[0][0], "p-2");
  assert.equal(campo("programa").value, "p-2");
});

test("mudar o período atualiza física e financeira juntas, numa consulta só", async () => {
  await abrir(api());

  campo("inicio").value = "2026-08-01";
  campo("fim").value = "2026-08-31";
  await enviar();

  assert.deepEqual(consultas.at(-1), ["p-1", { inicio: "2026-08-01", fim: "2026-08-31" }]);
  assert.equal(consultas.length, 2);
  assert.match(texto(), /de 01\/08\/2026 a 31\/08\/2026/);
});

test("período invertido não consulta a API", async () => {
  await abrir(api());

  campo("inicio").value = "2026-08-01";
  campo("fim").value = "2026-07-01";
  await enviar();

  assert.equal(consultas.length, 1);
  assert.match(texto(), /fim do período não pode ser anterior/);
});

test("papel sem acesso aos valores financeiros vê só a execução física", async () => {
  await abrir(api((id) => visao(id, { financeira: null })));

  assert.match(texto(), /Famílias/);
  assert.match(texto(), /Seu perfil vê só a execução física/);
  assert.doesNotMatch(texto(), /R\$/);
});

test("programa sem projeto no Financeiro mostra só a execução física, sem erro", async () => {
  await abrir(api((id) => visao(id, { financeira: { ...FINANCEIRA, vinculo: "nenhum", projeto: null, projeto_id: null, orcado: 0, realizado: 0, saldo: 0, percentual_executado: null } })));

  assert.match(texto(), /Famílias/);
  assert.match(texto(), /ainda não tem projeto no Financeiro/);
  assert.equal(container.querySelector('[role="alert"]:not([hidden])'), null);
});

test("vínculo pelo nome aparece com o aviso de que é provisório", async () => {
  await abrir(api((id) => visao(id, { financeira: { ...FINANCEIRA, vinculo: "nome" } })));

  assert.match(texto(), /encontrado pelo nome \(Semear\)/);
});

test("sem programas mostra o estado vazio", async () => {
  await abrir({ listarProgramas: async () => [], obterVisaoIntegrada: async () => assert.fail("não deveria consultar") });

  assert.match(texto(), /Nenhum programa cadastrado/);
});

test("descreve o período escolhido", () => {
  assert.equal(periodoDescrito(null, null), "todo o período");
  assert.equal(periodoDescrito("2026-01-01", null), "a partir de 01/01/2026");
  assert.equal(periodoDescrito(null, "2026-06-30"), "até 30/06/2026");
});
