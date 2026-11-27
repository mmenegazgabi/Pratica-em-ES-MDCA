// Painel de indicadores (T-73 · US-10): filtros que mudam tudo junto, período em aberto
// e nenhum dado pessoal na tela (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarIndicadores, mesAtual, mesDescrito } = await import("../telas/indicadores.js");
const { obterIndicadores } = await import("../base/api.js");
const { problemasDeLayout } = await import("./ajuda-layout.js");

const numeros = (extra = {}) => ({
  pessoas_acompanhadas: 2,
  encontros_realizados: 3,
  presencas: 3,
  ausencias: 2,
  frequencia: 60,
  horas_de_atividades: 5.5,
  metas: 2,
  percentual_medio_das_metas: 25,
  ...extra,
});
const PROGRAMAS = [
  { programa_id: "p-2", nome: "Oficina", identificador: "OFICINA", numeros: numeros({ pessoas_acompanhadas: 1, encontros_realizados: 1, presencas: 1, ausencias: 0, frequencia: 100, horas_de_atividades: 1, metas: 0, percentual_medio_das_metas: null }) },
  { programa_id: "p-1", nome: "Semear", identificador: "SEMEAR", numeros: numeros() },
];
const TOTAIS = numeros({ pessoas_acompanhadas: 3, encontros_realizados: 4, presencas: 4, frequencia: 66.7, horas_de_atividades: 6.5 });

function resposta({ programaId = "", inicio = "" } = {}, fechado = true) {
  const mes = inicio ? inicio.slice(0, 7) : "2026-09";
  const programas = programaId ? PROGRAMAS.filter((p) => p.programa_id === programaId) : PROGRAMAS;
  return {
    periodo: { inicio: `${mes}-01`, fim: `${mes}-30`, fechado },
    totais: programaId ? programas[0].numeros : TOTAIS,
    programas,
  };
}

let container;
let consultas;
// Texto dos nós separado por espaço (o textContent cola rótulo e valor dos cartões).
function texto() {
  const andar = document.createTreeWalker(container, window.NodeFilter.SHOW_TEXT);
  const partes = [];
  while (andar.nextNode()) partes.push(andar.currentNode.textContent);
  return partes.join(" ").replace(/\s+/g, " ").trim();
}
const esperar = () => new Promise((r) => setTimeout(r, 0));
const campo = (nome) => container.querySelector(`[name="${nome}"]`);
const HOJE = new Date(2026, 8, 15);

function api(responder = (filtros) => resposta(filtros)) {
  return {
    obterIndicadores: async (filtros) => {
      consultas.push(filtros);
      return responder(filtros);
    },
  };
}

async function abrir(opcoes = {}) {
  mostrarIndicadores(container, { hoje: HOJE, ...api(), ...opcoes });
  for (let i = 0; i < 4; i++) await esperar();
}

async function mudar(nome, valor) {
  campo(nome).value = valor;
  campo(nome).dispatchEvent(new window.Event("change", { bubbles: true }));
  for (let i = 0; i < 4; i++) await esperar();
}

beforeEach(() => {
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
  consultas = [];
});

afterEach(() => {
  assert.deepEqual(problemasDeLayout(container), []);
});

test("o cliente da API manda só os filtros informados", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "sessao-de-teste", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "ana", nome: "Ana Martins", papeis: [] } }));
  const chamadas = [];
  globalThis.fetch = async (url) => {
    chamadas.push(url);
    return new Response("{}", { status: 200 });
  };
  await obterIndicadores();
  await obterIndicadores({ programaId: "p 1", inicio: "2026-09-01" });

  assert.match(chamadas[0], /\/gestao\/indicadores$/);
  assert.match(chamadas[1], /\/gestao\/indicadores\?programa_id=p\+1&inicio=2026-09-01$/);
});

test("mês atual e descrição do mês", () => {
  assert.equal(mesAtual(HOJE), "2026-09");
  assert.equal(mesDescrito("2026-09-01"), "setembro de 2026");
});

test("abre no mês atual com os totais, o gráfico, a tabela e as metas", async () => {
  await abrir();

  assert.deepEqual(consultas, [{ programaId: "", inicio: "2026-09-01" }]);
  assert.match(texto(), /Pessoas acompanhadas 3 em 2 programas/);
  assert.match(texto(), /Encontros realizados 4/);
  assert.match(texto(), /Frequência 66,7% 4 presenças e 2 ausências/);
  assert.match(texto(), /Horas de atividades 6,5 h/);
  assert.match(texto(), /Presenças e ausências por programa/);
  assert.match(texto(), /Semear 2 3 60% 5,5 h/);
  assert.match(texto(), /Oficina Sem metas/);
  assert.match(texto(), /Semear 25%/);
  // Os programas visíveis vêm da própria resposta.
  assert.deepEqual([...campo("programa").options].map((o) => o.value), ["", "p-2", "p-1"]);
});

test("filtro de programa muda cartões, gráfico, tabela e metas numa consulta só", async () => {
  await abrir();

  await mudar("programa", "p-2");

  assert.equal(consultas.length, 2);
  assert.deepEqual(consultas.at(-1), { programaId: "p-2", inicio: "2026-09-01" });
  assert.match(texto(), /Pessoas acompanhadas 1 em 1 programa/);
  assert.doesNotMatch(container.querySelector(".indicadores-resultado").textContent, /Semear/);
  // A lista de programas do filtro continua completa.
  assert.equal(campo("programa").options.length, 3);
});

test("filtro de mês também vale para tudo", async () => {
  await abrir();

  await mudar("mes", "2026-08");

  assert.deepEqual(consultas.at(-1), { programaId: "", inicio: "2026-08-01" });
  assert.match(texto(), /Período fechado: 01\/08\/2026 a 30\/08\/2026/);
});

test("abre direto no programa pedido", async () => {
  await abrir({ programaInicial: "p-1" });

  assert.equal(campo("programa").value, "p-1");
  assert.deepEqual(consultas.at(-1), { programaId: "p-1", inicio: "2026-09-01" });
  assert.doesNotMatch(texto(), /Oficina \d/);
});

test("período em aberto avisa que os números ainda podem mudar", async () => {
  await abrir(api((filtros) => resposta(filtros, false)));

  const aviso = container.querySelector(".indicadores-periodo");
  assert.ok(aviso.classList.contains("em-aberto"));
  assert.match(aviso.textContent, /Período em aberto .*podem mudar/);
});

test("período fechado não tem o aviso de em aberto", async () => {
  await abrir();

  assert.ok(!container.querySelector(".indicadores-periodo").classList.contains("em-aberto"));
  assert.match(texto(), /Período fechado/);
});

test("sem programas no recorte mostra o estado vazio", async () => {
  await abrir(api(() => ({ periodo: { inicio: "2026-09-01", fim: "2026-09-30", fechado: true }, totais: numeros(), programas: [] })));

  assert.match(texto(), /Nenhum programa no seu recorte/);
});

test("a tela não mostra dado pessoal: só números e nomes de programas", async () => {
  await abrir();

  assert.match(texto(), /sem identificar as pessoas atendidas/);
  assert.doesNotMatch(container.innerHTML, /pessoa_id|nascimento|pe-/);
});
