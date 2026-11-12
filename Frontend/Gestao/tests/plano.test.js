// Plano e metas pela API da T-44 (T-45 · US-02): planejado, realizado e percentual por
// ação, e cadastro de objetivo, ação, meta e realizado (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarPlano, percentualDaAcao } = await import("../telas/plano.js");

const OBJETIVOS = [{ id: "o-1", descricao: "Fortalecer vínculos familiares" }];
const ACOES = [
  {
    id: "a-1",
    objetivo_id: "o-1",
    descricao: "Encontros com as famílias",
    periodo_inicio: "2026-03-01",
    periodo_fim: "2026-11-30",
    resultado_esperado: "Famílias participando",
    periodicidade: "mensal",
  },
  {
    id: "a-2",
    objetivo_id: "o-1",
    descricao: "Visitas domiciliares",
    periodo_inicio: "2026-03-01",
    periodo_fim: "2026-11-30",
    resultado_esperado: "Famílias acompanhadas",
    periodicidade: "trimestral",
  },
];
const META = (id, descricao, planejado, realizado, percentual, unidade = "famílias") => ({
  meta_id: id,
  descricao,
  unidade,
  acao_id: "a-1",
  acao: "Encontros com as famílias",
  objetivo_id: "o-1",
  objetivo: "Fortalecer vínculos familiares",
  planejado,
  realizado,
  percentual,
});
const PAINEL = {
  programa_id: "p-1",
  metas: [META("m-1", "Famílias nos encontros", 40, 30, 75), META("m-2", "Encontros realizados", 9, 3, 33.3, "encontros")],
};

let container;
// Espaçamento e caixas (T-00m): depois de cada teste, o que a tela montou passa pelo
// verificador de layout (nada de caixa dentro de caixa nem blocos sem espaço entre eles).
const { problemasDeLayout } = await import("./ajuda-layout.js");
afterEach(() => {
  if (container) assert.deepEqual(problemasDeLayout(container), []);
});
let registro;
let avisos;
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = () => new Promise((r) => setTimeout(r, 0));
const dialogo = () => document.getElementById("dialog");
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button")].find((b) => texto(b) === rotulo);
const enviar = async (form) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  await esperar();
};

function api(extra = {}) {
  const anotar = (nome, resposta) => async (...args) => {
    registro.push([nome, ...args]);
    return resposta;
  };
  return {
    listarObjetivos: anotar("listarObjetivos", OBJETIVOS),
    listarAcoes: anotar("listarAcoes", ACOES),
    obterPainel: anotar("obterPainel", PAINEL),
    cadastrarObjetivo: anotar("cadastrarObjetivo", { id: "o-2" }),
    cadastrarAcao: anotar("cadastrarAcao", { id: "a-3" }),
    cadastrarMeta: anotar("cadastrarMeta", { id: "m-3" }),
    registrarRealizado: anotar("registrarRealizado", { id: "r-1" }),
    avisar: (t) => avisos.push(t),
    ...extra,
  };
}

beforeEach(() => {
  document.body.replaceChildren(document.createElement("dialog"));
  document.querySelector("dialog").id = "dialog";
  container = document.createElement("div");
  document.body.append(container);
  registro = [];
  avisos = [];
});

test("percentual da ação é a média dos percentuais das metas", () => {
  assert.equal(percentualDaAcao([{ percentual: 75 }, { percentual: 33.3 }]), 54.2);
  assert.equal(percentualDaAcao([]), null);
});

test("plano mostra planejado, realizado e percentual de cada meta e o da ação", async () => {
  await mostrarPlano(container, "p-1", api());

  const linhas = [...container.querySelectorAll("tbody tr")].map((tr) => [...tr.cells].slice(0, 4).map((c) => texto(c)));
  assert.deepEqual(linhas, [
    ["Famílias nos encontros", "40 famílias", "30 famílias", "75%"],
    ["Encontros realizados", "9 encontros", "3 encontros", "33,3%"],
  ]);
  assert.match(texto(), /54,2% da ação/);
  // A ação sem metas aparece com o aviso, não com percentual.
  assert.match(texto(), /Visitas domiciliares.*Sem metas/);
  assert.match(texto(), /2 metas · média 54,2%/);
});

test("barra de progresso não passa de 100% quando a meta é superada", async () => {
  await mostrarPlano(container, "p-1", api({ obterPainel: async () => ({ programa_id: "p-1", metas: [META("m-1", "Meta", 10, 15, 150)] }) }));

  assert.equal(container.querySelector(".progress span").style.width, "100%");
  assert.match(texto(), /150%/);
});

test("sem objetivos mostra como começar e só quem gerencia vê os botões", async () => {
  await mostrarPlano(container, "p-1", api({ listarObjetivos: async () => [], listarAcoes: async () => [], obterPainel: async () => ({ programa_id: "p-1", metas: [] }) }));

  assert.match(texto(), /Nenhum objetivo cadastrado/);
  assert.equal(botao("+ Objetivo", container), undefined);
});

test("quem gerencia cadastra objetivo e a tela recarrega", async () => {
  await mostrarPlano(container, "p-1", api({ podeGerenciar: true }));

  botao("+ Objetivo", container).click();
  dialogo().querySelector("#f-objetivo-descricao").value = "Ampliar a participação";
  await enviar(dialogo().querySelector("form"));

  assert.deepEqual(registro.find(([n]) => n === "cadastrarObjetivo"), ["cadastrarObjetivo", "p-1", { descricao: "Ampliar a participação" }]);
  assert.deepEqual(avisos, ["Objetivo cadastrado."]);
  assert.equal(registro.filter(([n]) => n === "obterPainel").length, 2);
});

test("ação sem período, resultado ou periodicidade não chama a API", async () => {
  await mostrarPlano(container, "p-1", api({ podeGerenciar: true }));

  botao("+ Ação", container).click();
  dialogo().querySelector("#f-acao-objetivo").value = "o-1";
  dialogo().querySelector("#f-acao-descricao").value = "Rodas de conversa";
  await enviar(dialogo().querySelector("form"));

  assert.equal(registro.some(([n]) => n === "cadastrarAcao"), false);
  assert.match(texto(dialogo()), /Informe o início, o fim, o resultado esperado, a periodicidade/);
});

test("ação completa vai para a API com a periodicidade escolhida", async () => {
  await mostrarPlano(container, "p-1", api({ podeGerenciar: true }));

  botao("+ Ação", container).click();
  const d = dialogo();
  d.querySelector("#f-acao-objetivo").value = "o-1";
  d.querySelector("#f-acao-descricao").value = "Rodas de conversa";
  d.querySelector("#f-acao-inicio").value = "2026-04-01";
  d.querySelector("#f-acao-fim").value = "2026-10-31";
  d.querySelector("#f-acao-resultado").value = "Jovens participando";
  d.querySelector("#f-acao-periodicidade").value = "quinzenal";
  await enviar(d.querySelector("form"));

  assert.deepEqual(registro.find(([n]) => n === "cadastrarAcao")[2], {
    objetivo_id: "o-1",
    descricao: "Rodas de conversa",
    periodo_inicio: "2026-04-01",
    periodo_fim: "2026-10-31",
    resultado_esperado: "Jovens participando",
    periodicidade: "quinzenal",
  });
});

test("registrar realizado envia data e valor da meta escolhida", async () => {
  await mostrarPlano(container, "p-1", api({ podeGerenciar: true }));

  botao("Registrar realizado", container).click();
  dialogo().querySelector("#f-registro-valor").value = "5";
  await enviar(dialogo().querySelector("form"));

  const [, programa, meta, dados] = registro.find(([n]) => n === "registrarRealizado");
  assert.equal(programa, "p-1");
  assert.equal(meta, "m-1");
  assert.equal(dados.valor_realizado, 5);
  assert.match(dados.data, /^\d{4}-\d{2}-\d{2}$/);
  assert.deepEqual(avisos, ["Realizado registrado."]);
});
