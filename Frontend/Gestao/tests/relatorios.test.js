// Tela do relatório técnico (T-76 · US-11): configurar, pendências antes da versão final,
// prévia já minimizada, exportação em PDF ou XLSX e histórico (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarNovoRelatorio, mostrarEmissoes, mesDe, nomeDoArquivo, validarConfiguracao } = await import("../telas/relatorios.js");
const { obterPreviaDoRelatorio, exportarRelatorio, listarEmissoes } = await import("../base/api.js");
const { problemasDeLayout } = await import("./ajuda-layout.js");

const PROGRAMAS = [
  { id: "p-1", nome: "Semear", identificador: "SEMEAR" },
  { id: "p-2", nome: "Oficina", identificador: null },
];
const EVIDENCIAS = [
  { id: "ev-1", data: "2026-09-02", turma: "Oficina de arte", liberada_externa: false },
  { id: "ev-2", data: "2026-09-16", turma: "Leitura", liberada_externa: true },
];

function previa(pedido) {
  const externa = pedido.finalidade === "externa";
  return {
    programa_id: pedido.programa_id,
    programa: "Semear",
    periodo: { inicio: pedido.inicio, fim: pedido.fim, fechado: true },
    finalidade: pedido.finalidade,
    secoes: pedido.secoes,
    titulo: "Relatório técnico — Semear — 01/09/2026 a 30/09/2026",
    cabecalho: [["Programa", "Semear (SEMEAR)"], ["Finalidade", externa ? "Circulação externa" : "Consulta interna"]],
    conteudo: [
      externa
        ? { titulo: "Pessoas atendidas", colunas: ["Turma", "Pessoas"], linhas: [["Oficina de arte", "2"]], nota: "Circulação externa: só o número de pessoas, sem nomes.", vazio: "" }
        : { titulo: "Pessoas atendidas", colunas: ["Pessoa", "Turmas", "Presenças", "Ausências", "Frequência"], linhas: [["Lara Oliveira", "Oficina de arte", "2", "1", "66,7%"]], nota: null, vazio: "" },
      { titulo: "Indicadores", colunas: ["Indicador", "Valor"], linhas: [], nota: null, vazio: "Nada a mostrar neste período." },
    ],
    rodape: externa ? "Documento para circulação externa: sem dados pessoais identificáveis." : "Documento de consulta interna.",
    pendencias: [
      { tipo: "chamadas_sem_registro", descricao: "Chamadas sem registro no período", quantidade: 7 },
      ...(externa ? [{ tipo: "autorizacoes_de_imagem_vencidas", descricao: "Autorizações de imagem vencidas ou revogadas", quantidade: 2 }] : []),
    ],
    evidencias_disponiveis: pedido.secoes.includes("evidencias") ? EVIDENCIAS : [],
    finalidades_permitidas: ["externa", "interna"],
  };
}

let container;
let chamadas;
let baixados;
let avisos;
// Texto dos nós separado por espaço (o textContent cola o rótulo no valor).
function texto() {
  const andar = document.createTreeWalker(container, window.NodeFilter.SHOW_TEXT);
  const partes = [];
  while (andar.nextNode()) partes.push(andar.currentNode.textContent);
  return partes.join(" ").replace(/\s+/g, " ").trim();
}
const esperar = async () => {
  for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
};
const campo = (nome) => container.querySelector(`[name="${nome}"]`);
const botao = (rotulo) => [...container.querySelectorAll("button, a.btn")].find((b) => b.textContent.trim() === rotulo);
async function enviar() {
  container.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
}

function api(extra = {}) {
  return {
    listarProgramas: async () => PROGRAMAS,
    obterPreviaDoRelatorio: async (pedido) => {
      chamadas.push(["previa", structuredClone(pedido)]);
      return previa(pedido);
    },
    exportarRelatorio: async (pedido, formato) => {
      chamadas.push(["exportar", structuredClone(pedido), formato]);
      return new window.Blob(["arquivo"]);
    },
    ...extra,
  };
}

async function abrir(opcoes = {}) {
  mostrarNovoRelatorio(container, { hoje: "2026-09-18", avisar: (m) => avisos.push(m), baixar: (arquivo, nome) => baixados.push(nome), ...api(), ...opcoes });
  await esperar();
}

beforeEach(() => {
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
  chamadas = [];
  baixados = [];
  avisos = [];
});

afterEach(() => {
  assert.deepEqual(problemasDeLayout(container), []);
});

test("apoio: mês, nome do arquivo e validação da configuração", () => {
  assert.deepEqual(mesDe("2026-02-10"), ["2026-02-01", "2026-02-28"]);
  assert.equal(nomeDoArquivo("Semear Ação", "2026-09-01", "2026-09-30", "pdf"), "relatorio-tecnico-semear-acao-01-09-2026-a-30-09-2026.pdf");
  const ok = { programa_id: "p-1", inicio: "2026-09-01", fim: "2026-09-30", finalidade: "externa", secoes: ["plano"] };
  assert.equal(validarConfiguracao(ok), "");
  assert.match(validarConfiguracao({ ...ok, fim: "2026-08-01" }), /anterior ao início/);
  assert.match(validarConfiguracao({ ...ok, secoes: [] }), /ao menos uma seção/);
});

test("o cliente da API manda o pedido em JSON e pede o arquivo como Blob", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "t", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "ana", nome: "Ana", papeis: [] } }));
  const pedidos = [];
  globalThis.fetch = async (url, opcoes) => {
    pedidos.push([url, opcoes.method, opcoes.body]);
    return new Response("{}", { status: 200 });
  };
  await obterPreviaDoRelatorio({ programa_id: "p-1" });
  await exportarRelatorio({ programa_id: "p-1" }, "xlsx");
  await listarEmissoes();

  assert.match(pedidos[0][0], /\/gestao\/relatorios-tecnicos\/previa$/);
  assert.deepEqual([pedidos[0][1], pedidos[0][2]], ["POST", '{"programa_id":"p-1"}']);
  assert.match(pedidos[1][0], /\/exportacao\?formato=xlsx$/);
  assert.match(pedidos[2][0], /\/emissoes$/);
});

test("abre no mês atual, em circulação externa, com as seções menos a financeira", async () => {
  await abrir();

  assert.equal(campo("programa").value, "p-1");
  assert.equal(campo("inicio").value, "2026-09-01");
  assert.equal(campo("fim").value, "2026-09-30");
  assert.equal(campo("finalidade").value, "externa");
  const secoes = [...container.querySelectorAll('[name="secoes"]')];
  assert.deepEqual(secoes.map((s) => [s.value, s.checked]), [["plano", true], ["pessoas", true], ["atividades", true], ["indicadores", true], ["evidencias", true]]);
});

test("quem vê valores financeiros pode incluir a seção financeira", async () => {
  await abrir({ comFinanceiro: true });

  assert.ok(container.querySelector('[name="secoes"][value="financeiro"]'));
});

test("a direção só tem a circulação externa", async () => {
  await abrir({ finalidades: ["externa"] });

  assert.deepEqual([...campo("finalidade").options].map((o) => o.value), ["externa"]);
});

test("sem seção escolhida não consulta a API", async () => {
  await abrir();
  container.querySelectorAll('[name="secoes"]').forEach((c) => (c.checked = false));

  await enviar();

  assert.equal(chamadas.length, 0);
  assert.match(texto(), /ao menos uma seção/);
});

test("pendências aparecem antes da versão final, com onde corrigir", async () => {
  await abrir();
  await enviar();

  assert.equal(chamadas[0][1].evidencias, null);
  assert.match(texto(), /2 pendências encontradas/);
  assert.match(texto(), /Chamadas sem registro no período 7 Corrigir/);
  assert.match(texto(), /Autorizações de imagem vencidas ou revogadas 2/);
  assert.equal(container.querySelector('a[href="#/pessoas"]').textContent, "Corrigir");
  assert.ok(botao("Visualizar rascunho"));
});

test("na circulação externa a evidência sem autorização não pode ser escolhida", async () => {
  await abrir();
  await enviar();

  const ev1 = container.querySelector('[name="evidencias"][value="ev-1"]');
  const ev2 = container.querySelector('[name="evidencias"][value="ev-2"]');
  assert.equal(ev1.disabled, true);
  assert.equal(ev1.checked, false);
  assert.equal(ev2.checked, true);
  assert.match(texto(), /Sem autorização de imagem de todos os presentes/);
});

test("a prévia usa as evidências escolhidas e já mostra os dados minimizados", async () => {
  await abrir();
  await enviar();
  await enviar();

  assert.deepEqual(chamadas.at(-1)[1].evidencias, ["ev-2"]);
  assert.match(texto(), /Rascunho · pendências em aberto · Circulação externa/);
  assert.match(texto(), /Pessoas atendidas Turma Pessoas Oficina de arte 2/);
  assert.match(texto(), /Circulação externa: só o número de pessoas, sem nomes/);
  assert.doesNotMatch(texto(), /Lara/);
  assert.match(texto(), /Indicadores Nada a mostrar neste período/);
});

test("na consulta interna a prévia mostra os nomes", async () => {
  await abrir();
  campo("finalidade").value = "interna";
  await enviar();
  await enviar();

  assert.match(texto(), /Consulta interna/);
  assert.match(texto(), /Lara Oliveira/);
});

test("exporta PDF e XLSX com o mesmo pedido da prévia e avisa que entrou no histórico", async () => {
  await abrir();
  await enviar();
  await enviar();

  botao("Exportar PDF").click();
  await esperar();
  botao("Exportar XLSX").click();
  await esperar();

  const exportacoes = chamadas.filter(([tipo]) => tipo === "exportar");
  assert.deepEqual(exportacoes.map(([, , formato]) => formato), ["pdf", "xlsx"]);
  // O arquivo sai do mesmo pedido da prévia que está na tela.
  assert.deepEqual(exportacoes[0][1], chamadas.filter(([tipo]) => tipo === "previa").at(-1)[1]);
  assert.deepEqual(exportacoes[0][1], exportacoes[1][1]);
  assert.deepEqual(baixados, ["relatorio-tecnico-semear-01-09-2026-a-30-09-2026.pdf", "relatorio-tecnico-semear-01-09-2026-a-30-09-2026.xlsx"]);
  assert.match(avisos.at(-1), /XLSX e registrado no histórico/);
});

test("erro na exportação avisa sem perder a prévia", async () => {
  await abrir({
    exportarRelatorio: async () => {
      throw Object.assign(new Error("falhou"), { detalhe: "Seu perfil emite só relatórios para circulação externa, sem dados pessoais." });
    },
  });
  await enviar();
  await enviar();

  botao("Exportar PDF").click();
  await esperar();

  assert.match(avisos.at(-1), /só relatórios para circulação externa/);
  assert.match(texto(), /Pessoas atendidas/);
});

test("ajustar a configuração volta ao primeiro passo com as escolhas", async () => {
  await abrir();
  campo("finalidade").value = "interna";
  await enviar();
  botao("Voltar").click();
  await esperar();

  assert.equal(campo("finalidade").value, "interna");
});

test("histórico lista as emissões; sem emissões, convida a gerar", async () => {
  mostrarEmissoes(container, {
    listarEmissoes: async () => [
      { momento: "2026-09-30T18:00:00Z", usuario: "Ana Martins", programa_id: "p-1", programa: "Semear", inicio: "2026-09-01", fim: "2026-09-30", finalidade: "externa", secoes: ["plano", "indicadores"], formato: "xlsx" },
    ],
  });
  await esperar();
  assert.match(texto(), /30\/09\/2026 .*Semear 01\/09\/2026 a 30\/09\/2026 Circulação externa 2 XLSX Ana Martins/);

  container.replaceChildren();
  mostrarEmissoes(container, { listarEmissoes: async () => [] });
  await esperar();
  assert.match(texto(), /Nenhum relatório emitido/);
  assert.ok(container.querySelector('a[href="#/relatorios/novo"]'));
});
