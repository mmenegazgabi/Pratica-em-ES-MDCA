// Visão geral ligada à API (T-91 · US-10): números do banco, filtro de programa para
// todos os cartões e uma fonte com erro sem derrubar as outras (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarVisaoGeral, somarDias, situacao } = await import("../telas/visao-geral.js");
const { obterPendencias } = await import("../base/api.js");
const { problemasDeLayout } = await import("./ajuda-layout.js");

const HOJE = "2026-11-18";
const PROGRAMAS = [
  { id: "p-1", nome: "Semear", identificador: "SEMEAR" },
  { id: "p-2", nome: "Oficina", identificador: "OFICINA" },
];
const numeros = (extra = {}) => ({
  pessoas_acompanhadas: 5,
  encontros_realizados: 4,
  presencas: 9,
  ausencias: 3,
  frequencia: 75,
  horas_de_atividades: 8,
  metas: 1,
  percentual_medio_das_metas: 63.3,
  ...extra,
});
const NUMEROS = { "p-1": numeros(), "p-2": numeros({ pessoas_acompanhadas: 2, encontros_realizados: 1, frequencia: 50, metas: 0, percentual_medio_das_metas: null }) };
const PERIODO = { inicio: "2026-11-01", fim: "2026-11-30", fechado: false };

function indicadores({ programaId }) {
  const ids = programaId ? [programaId] : ["p-1", "p-2"];
  const programas = ids.map((id) => ({ programa_id: id, nome: PROGRAMAS.find((p) => p.id === id).nome, identificador: null, numeros: NUMEROS[id] }));
  const totais = programaId ? NUMEROS[programaId] : numeros({ pessoas_acompanhadas: 7, encontros_realizados: 5, frequencia: 70 });
  return { periodo: PERIODO, totais, programas };
}

const pendencias = ({ programaId }) => ({
  periodo: PERIODO,
  totais: programaId === "p-2"
    ? { chamadas_sem_registro: 0, encontros_sem_evidencia: 1, autorizacoes_de_imagem_vencidas: 0, total: 1 }
    : { chamadas_sem_registro: 2, encontros_sem_evidencia: 1, autorizacoes_de_imagem_vencidas: 3, total: 6 },
  programas: [],
});

const encontro = (data, turma, extra = {}) => ({
  data,
  turma_id: `t-${turma}`,
  turma,
  espaco: "Ateliê",
  responsavel_id: "jessica",
  responsavel: "Jéssica Almeida",
  hora_inicio: "14:00:00",
  hora_fim: "16:00:00",
  previsto: true,
  atividades: [],
  ...extra,
});
const AGENDA = {
  "p-1": [encontro("2026-11-18", "Convivência", { atividades: ["a-7"] }), encontro("2026-11-20", "Convivência")],
  "p-2": [encontro("2026-11-19", "Marcenaria", { hora_inicio: "08:00:00", hora_fim: "09:00:00" })],
};
const ALERTAS = [
  { title: "Lucas precisa de um contato", description: "3 faltas seguidas.", link: "/alertas/al-1", programa: "p-1" },
  { title: "Caio precisa de um contato", description: "4 faltas seguidas.", link: "/alertas/al-2", programa: "p-2" },
];

let container;
let consultas;
const texto = () => {
  const andar = document.createTreeWalker(container, window.NodeFilter.SHOW_TEXT);
  const partes = [];
  while (andar.nextNode()) partes.push(andar.currentNode.textContent);
  return partes.join(" ").replace(/\s+/g, " ").trim();
};
const esperar = async () => {
  for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
};

function api(falhas = {}) {
  const registrar = (nome, responder) => async (...args) => {
    consultas.push([nome, ...args]);
    if (falhas[nome]) throw new Error(`Falha em ${nome}`);
    return responder(...args);
  };
  return {
    listarProgramas: registrar("programas", () => PROGRAMAS),
    obterIndicadores: registrar("indicadores", indicadores),
    obterPendencias: registrar("pendencias", pendencias),
    obterAgenda: registrar("agenda", (id) => AGENDA[id]),
  };
}

async function abrir(opcoes = {}) {
  mostrarVisaoGeral(container, { hoje: HOJE, alertas: () => ALERTAS, podeRegistrar: true, mostrarPendencias: true, ...api(), ...opcoes });
  await esperar();
}

async function escolherPrograma(id) {
  const select = container.querySelector('[name="programa"]');
  select.value = id;
  select.dispatchEvent(new window.Event("change", { bubbles: true }));
  await esperar();
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

test("apoio: soma de dias e situação do encontro", () => {
  assert.equal(somarDias("2026-11-28", 6), "2026-12-04");
  assert.equal(situacao(encontro("2026-11-17", "X"), HOJE).texto, "Chamada pendente");
  assert.equal(situacao(encontro("2026-11-18", "X"), HOJE).texto, "Hoje");
  assert.equal(situacao(encontro("2026-11-20", "X"), HOJE).texto, "Agendada");
  assert.equal(situacao(encontro("2026-11-17", "X", { atividades: ["a"] }), HOJE).texto, "Concluída");
});

test("o cliente da API das pendências manda só os filtros informados", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "t", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "ana", nome: "Ana", papeis: [] } }));
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(url);
    return new Response("{}", { status: 200 });
  };
  await obterPendencias({ inicio: "2026-11-01" });

  assert.match(urls[0], /\/gestao\/pendencias\?inicio=2026-11-01$/);
});

test("os cartões mostram os números da API no mês atual", async () => {
  await abrir();

  assert.deepEqual(consultas.find(([n]) => n === "indicadores")[1], { programaId: "", inicio: "2026-11-01" });
  assert.match(texto(), /Pessoas acompanhadas 7 em 2 programas/);
  assert.match(texto(), /Encontros realizados 5/);
  assert.match(texto(), /Frequência registrada 70%/);
  assert.match(texto(), /Pontos de atenção 2/);
  assert.match(texto(), /Semear Atenção à meta .*63,3%/);
  assert.match(texto(), /Oficina Sem metas/);
});

test("alertas abertos aparecem em Precisam do seu olhar, com o destino do acompanhamento", async () => {
  await abrir();

  const links = [...container.querySelectorAll(".priority-item a")].map((a) => a.getAttribute("href"));
  assert.ok(links.includes("#/alertas/al-1"));
  assert.match(texto(), /2 abertos/);
});

test("a agenda junta os programas em ordem de data, com chamada a fazer e chamada feita", async () => {
  await abrir();

  assert.deepEqual(
    consultas.filter(([n]) => n === "agenda").map(([, id, f]) => [id, f]),
    [["p-1", { inicio: HOJE, fim: "2026-11-24" }], ["p-2", { inicio: HOJE, fim: "2026-11-24" }]],
  );
  const linhas = [...container.querySelectorAll("tbody tr")].map((tr) => tr.textContent);
  assert.match(linhas[0], /qua 18\/11.*Convivência.*Semear.*Concluída.*Ver chamada/);
  assert.match(linhas[1], /qui 19\/11.*08:00–09:00.*Marcenaria.*Oficina.*Agendada/);
  assert.match(linhas[2], /sex 20\/11.*Agendada/);
  assert.equal(container.querySelector('tbody a[href^="#/atividades/p-1/encontro/a-7"]').textContent, "Ver chamada");
});

test("o filtro de programa muda todos os cartões juntos", async () => {
  await abrir();
  consultas = [];

  await escolherPrograma("p-2");

  assert.deepEqual(consultas.find(([n]) => n === "indicadores")[1], { programaId: "p-2", inicio: "2026-11-01" });
  assert.deepEqual(consultas.find(([n]) => n === "pendencias")[1], { programaId: "p-2", inicio: "2026-11-01" });
  assert.deepEqual(consultas.filter(([n]) => n === "agenda").map(([, id]) => id), ["p-2"]);
  assert.match(texto(), /Pessoas acompanhadas 2 em 1 programa/);
  assert.match(texto(), /Pontos de atenção 1/);
  assert.doesNotMatch(texto(), /Lucas precisa/);
  assert.doesNotMatch(container.querySelector("tbody").textContent, /Convivência/);
  assert.match(texto(), /Encontros sem evidência · 1/);
});

test("uma fonte com erro só derruba o próprio cartão", async () => {
  await abrir(api({ indicadores: true }));

  assert.match(texto(), /Não foi possível carregar/);
  // Agenda, alertas e pendências continuam.
  assert.match(texto(), /Marcenaria/);
  assert.match(texto(), /Lucas precisa de um contato/);
  assert.match(texto(), /Chamadas sem registro · 2/);
});

test("agenda com erro não esconde os números", async () => {
  await abrir(api({ agenda: true }));

  assert.match(texto(), /Pessoas acompanhadas 7/);
  assert.match(texto(), /Não foi possível carregar/);
});

test("pendências só para quem fecha o período, e só com destino que o perfil abre", async () => {
  await abrir({ rotaPermitida: (rota) => rota !== "/pessoas" });
  assert.match(texto(), /Antes de fechar o período/);
  assert.match(texto(), /Chamadas sem registro · 2/);
  assert.doesNotMatch(texto(), /Autorizações de imagem/);

  container.replaceChildren();
  consultas = [];
  await abrir({ mostrarPendencias: false });
  assert.doesNotMatch(texto(), /Antes de fechar o período/);
  assert.ok(!consultas.some(([n]) => n === "pendencias"));
});

test("sem permissão de registrar, a agenda não oferece fazer chamada", async () => {
  AGENDA["p-1"][1] = encontro("2026-11-17", "Convivência");
  await abrir({ podeRegistrar: false });
  AGENDA["p-1"][1] = encontro("2026-11-20", "Convivência");

  assert.doesNotMatch(texto(), /Fazer chamada/);
  assert.match(texto(), /Chamada pendente/);
});
