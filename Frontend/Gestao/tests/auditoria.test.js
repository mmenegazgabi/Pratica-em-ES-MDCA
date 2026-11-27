// Auditoria única (telas/auditoria.js): a trilha da Gestão, do Financeiro e do acesso numa
// tela só, com coluna e filtro de módulo, lida de GET /auditoria (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { mostrarAuditoria } = await import("../telas/auditoria.js");
const { listarAuditoria, ErroApi, ERROS } = await import("../base/api.js");
const { problemasDeLayout } = await import("./ajuda-layout.js");

const EVENTOS = [
  { id: 3, quando: "2026-11-24T21:06:00Z", modulo: "plataforma", quem: "Luana Ferraz", acao: "Entrou no sistema", alvo: null, codigo: "login" },
  { id: 2, quando: "2026-11-24T20:00:00Z", modulo: "gestao", quem: "Paula", acao: "Baixou documento de pessoa atendida", alvo: "Download de documento da pessoa atendida", codigo: "download_documento" },
  { id: 1, quando: "2026-11-24T19:00:00Z", modulo: "financeiro", quem: "Luana Ferraz", acao: "Aprovou despesa", alvo: "Materiais · R$ 180,00 · Semear", codigo: "aprovar_lancamento" },
];

let container;
let consultas;
const esperar = () => new Promise((r) => setTimeout(r, 0));
const $ = (seletor) => container.querySelector(seletor);
const linhas = () => [...container.querySelectorAll("#auditoria-tabela tbody tr")];
const celulas = (tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent);

function pagina(itens = EVENTOS, extra = {}) {
  return { itens, total: itens.length, pagina: 1, tamanho: 50, escopo: "todos", ...extra };
}

async function abrir(responder = () => pagina()) {
  await mostrarAuditoria(container, {
    listar: async (filtros) => {
      consultas.push(filtros);
      return responder(filtros);
    },
  });
  await esperar();
}

beforeEach(() => {
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
  consultas = [];
});
afterEach(() => assert.deepEqual(problemasDeLayout(container), []));

test("o cliente da API pede GET /auditoria só com os filtros preenchidos", async () => {
  localStorage.setItem("mdca.sessao", JSON.stringify({ token: "sessao-de-teste", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "luana", nome: "Luana", papeis: [] } }));
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(url);
    return new Response(JSON.stringify(pagina([])), { status: 200 });
  };
  await listarAuditoria({ modulo: "todos", desde: "", ate: "2026-11-24", pagina: 2, tamanho: 50 });
  assert.match(urls[0], /\/auditoria\?modulo=todos&ate=2026-11-24&pagina=2&tamanho=50$/);
});

test("abre com todos os módulos e mostra a coluna Módulo", async () => {
  await abrir();

  assert.deepEqual(consultas[0], { modulo: "todos", desde: "", ate: "", pagina: 1, tamanho: 50 });
  const cabecalho = [...container.querySelectorAll("#auditoria-tabela th")].map((th) => th.textContent);
  assert.deepEqual(cabecalho, ["Quando", "Módulo", "Quem", "Ação", "Detalhe"]);
  assert.deepEqual(linhas().map((tr) => celulas(tr)[1]), ["Acesso e contas", "Gestão", "Financeiro"]);
  assert.deepEqual(celulas(linhas()[2]), ["24/11/2026 16:00", "Financeiro", "Luana Ferraz", "Aprovou despesa", "Materiais · R$ 180,00 · Semear"]);
  assert.equal(celulas(linhas()[0])[4], "—"); // evento sem detalhe
  assert.equal($("#auditoria-intervalo").textContent, "1–3 de 3");
  assert.equal($("#auditoria-escopo"), null);
  // Só leitura: nenhum botão de editar ou apagar.
  assert.deepEqual([...container.querySelectorAll("button")].map((b) => b.textContent), ["Aplicar", "Anterior", "Próxima"]);
});

test("o filtro de módulo consulta a API de novo com o módulo escolhido", async () => {
  await abrir((filtros) => pagina(EVENTOS.filter((e) => filtros.modulo === "todos" || e.modulo === filtros.modulo)));
  const modulo = $("#auditoria-modulo");
  assert.deepEqual([...modulo.options].map((o) => [o.value, o.textContent]), [
    ["todos", "Todos"], ["gestao", "Gestão"], ["financeiro", "Financeiro"], ["plataforma", "Acesso e contas"],
  ]);

  modulo.value = "gestao";
  modulo.dispatchEvent(new window.Event("change"));
  await esperar();

  assert.equal(consultas.at(-1).modulo, "gestao");
  assert.deepEqual(linhas().map((tr) => celulas(tr)[1]), ["Gestão"]);
});

test("período: De e Até vão para a API; Até antes de De não consulta", async () => {
  await abrir();
  $("#auditoria-desde").value = "2026-11-01";
  $("#auditoria-ate").value = "2026-11-30";
  $("form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  assert.deepEqual(consultas.at(-1), { modulo: "todos", desde: "2026-11-01", ate: "2026-11-30", pagina: 1, tamanho: 50 });

  $("#auditoria-ate").value = "2026-10-01";
  $("form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  assert.equal(consultas.length, 2);
  assert.match(container.querySelector('[role="alert"]').textContent, /data final não pode ser anterior/);
});

test("a busca filtra a página sem chamar a API, inclusive pelo módulo", async () => {
  await abrir();
  const busca = $("#auditoria-busca");
  busca.value = "gestão";
  busca.dispatchEvent(new window.Event("input"));
  assert.deepEqual(linhas().map((tr) => celulas(tr)[2]), ["Paula"]);
  busca.value = "ninguém";
  busca.dispatchEvent(new window.Event("input"));
  assert.match(container.textContent, /Nenhuma ação desta página corresponde à busca/);
  assert.equal(consultas.length, 1);
});

test("páginas: Próxima pede a página seguinte", async () => {
  const muitos = Array.from({ length: 50 }, (_, i) => ({ ...EVENTOS[2], id: 100 - i }));
  await abrir((filtros) => pagina(muitos, { total: 120, pagina: filtros.pagina }));
  assert.equal($("#auditoria-anterior").disabled, true);
  $("#auditoria-proxima").click();
  await esperar();
  assert.equal(consultas.at(-1).pagina, 2);
  assert.equal($("#auditoria-intervalo").textContent, "51–100 de 120");
  assert.equal($("#auditoria-anterior").disabled, false);
});

test("psicologia: a tela avisa que mostra só os próprios registros", async () => {
  await abrir(() => pagina([EVENTOS[1]], { escopo: "proprios" }));
  assert.equal($("#auditoria-escopo").textContent, "Você vê só os registros feitos por você.");
  assert.equal(linhas().length, 1);
});

test("sem registros e sem permissão", async () => {
  await abrir(() => pagina([]));
  assert.match(container.textContent, /Nenhuma ação registrada/);

  container.replaceChildren();
  await abrir(() => {
    throw new ErroApi(ERROS.SEM_PERMISSAO, 403, "A auditoria é para Coordenação, Direção e Administração.");
  });
  assert.match(container.textContent, /Acesso restrito/);
});
