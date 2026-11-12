// Projetos e Detalhe do projeto: telas montadas (jsdom) com a API simulada.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const lista = await import("../telas/projetos.js");
const detalhe = await import("../telas/projeto.js");

const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo, text: async () => JSON.stringify(corpo) });
const container = () => document.getElementById("c");
const esperar = () => new Promise((r) => setTimeout(r, 15));
const coord = { papel: "coordenacao", nome: "Luana" };

const orc = { id: "o1", projeto_id: "p1", projeto_nome: "Esporte", valor_total: 10000, data_inicio: "2026-01-01", data_fim: "2026-12-31", categorias_despesa: ["Uniformes", "Transporte"], saldo: 1500, realizado: 8500, percentual_consumido: 85, nivel_alerta: "atencao" };
const lancs = [
  { id: "l1", orcamento_id: "o1", categoria: "Uniformes", valor: 640, status: "aprovado", conciliado: true, autor_id: "carla-dias", data_despesa: "2026-10-20", criado_em: "2026-10-20T10:00:00Z" },
  { id: "l2", orcamento_id: "o1", categoria: "Transporte", valor: 92.5, status: "pendente", conciliado: false, autor_id: "ana-souza", data_despesa: "2026-10-27", criado_em: "2026-10-27T10:00:00Z" },
];
let chamadas;
let editar;
let projetos;
let mudarStatus;

function simular({ listaDeProjetos = [{ id: "p1", nome: "Esporte", status: "ativo" }, { id: "p2", nome: "Horta", status: "ativo" }] } = {}) {
  chamadas = [];
  projetos = listaDeProjetos;
  globalThis.fetch = async (url, op = {}) => {
    const u = String(url).replace(/^https?:\/\/[^/]+/, "");
    chamadas.push(`${op.method || "GET"} ${u}`);
    if (op.method === "PATCH" && u.endsWith("/status")) return mudarStatus(u, JSON.parse(op.body));
    if (u.startsWith("/projetos")) return Array.isArray(projetos) ? resposta(200, projetos) : projetos;
    if (op.method === "PATCH") return editar(JSON.parse(op.body));
    if (u.startsWith("/orcamentos/o1")) return resposta(200, orc);
    if (u.startsWith("/orcamentos")) return resposta(200, [orc]);
    return resposta(200, lancs);
  };
}

test("lista: uma linha por projeto, sem orçamento com ação, clique abre o detalhe", async () => {
  simular();
  const rotas = [];
  await lista.mostrar(container(), { parametros: {}, sessao: coord, navegar: (r) => rotas.push(r) });
  const linhas = [...container().querySelectorAll("tbody tr")];
  assert.equal(linhas.length, 2);
  assert.match(linhas[0].textContent, /85%/);
  assert.match(linhas[1].textContent, /Sem orçamento/);
  assert.match(linhas[1].textContent, /Criar orçamento/);
  assert.match(container().textContent, /Aguardando aprovação/);
  linhas[0].click();
  assert.deepEqual(rotas, ["#/projetos/o1"]);
});

test("lista: direção não vê Novo projeto nem Criar orçamento", async () => {
  simular();
  await lista.mostrar(container(), { parametros: {}, sessao: { papel: "direcao", nome: "Jane" }, navegar: () => {} });
  assert.doesNotMatch(container().textContent, /Novo projeto|Criar orçamento/);
});

test("detalhe: números, categorias com 0, últimos lançamentos e Disponível em alerta", async () => {
  simular();
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: coord, navegar: () => {} });
  const t = container().textContent;
  assert.match(t, /Esporte/);
  assert.match(t, /85% usado/);
  assert.match(t, /Uniformes/);
  assert.doesNotMatch(t, /object HTML/);
  assert.match(t, /Conciliado/);
  assert.match(t, /Aguardando/);
  assert.match(t, /Editar orçamento/);
  assert.ok(chamadas.some((c) => c.includes("orcamento_id=o1")));
});

test("edição: erro 400 do servidor aparece no diálogo; sucesso fecha e recarrega", async () => {
  simular();
  editar = () => resposta(400, { detail: "O valor total não pode ficar abaixo do gasto." });
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: coord, navegar: () => {} });
  [...container().querySelectorAll("button")].find((b) => b.textContent === "Editar orçamento").click();
  const dialogo = container().querySelector("dialog");
  assert.ok(dialogo);
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.match(dialogo.textContent, /abaixo do gasto/);
  editar = (corpo) => {
    assert.equal(corpo.valor_total, 10000);
    return resposta(200, orc);
  };
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.equal(container().querySelector("dialog"), null);
});

test("edição: validação local impede o envio sem categorias", async () => {
  simular();
  editar = () => assert.fail("não deveria enviar");
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: coord, navegar: () => {} });
  [...container().querySelectorAll("button")].find((b) => b.textContent === "Editar orçamento").click();
  const dialogo = container().querySelector("dialog");
  dialogo.querySelectorAll("button[aria-label^='Remover']").forEach((b) => b.click());
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.match(dialogo.textContent, /ao menos uma categoria/);
});

test("detalhe: direção não edita", async () => {
  simular();
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: { papel: "direcao", nome: "Jane" }, navegar: () => {} });
  assert.doesNotMatch(container().textContent, /Editar orçamento/);
});

const botao = (texto) => [...container().querySelectorAll("button")].find((b) => b.textContent === texto);

test("lista: projeto encerrado aparece como Encerrado", async () => {
  simular({ listaDeProjetos: [{ id: "p1", nome: "Esporte", status: "encerrado" }, { id: "p2", nome: "Horta", status: "ativo" }] });
  await lista.mostrar(container(), { parametros: {}, sessao: coord, navegar: () => {} });
  const linhas = [...container().querySelectorAll("tbody tr")];
  assert.match(linhas[0].textContent, /Encerrado/);
  assert.doesNotMatch(linhas[1].textContent, /Encerrado/);
});

test("detalhe: encerrar pede confirmação, chama PATCH /projetos/{id}/status e mostra Encerrado", async () => {
  simular();
  mudarStatus = (u, corpo) => {
    projetos = [{ id: "p1", nome: "Esporte", status: corpo.status }];
    return resposta(200, projetos[0]);
  };
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: coord, navegar: () => {} });
  assert.doesNotMatch(container().textContent, /Encerrado/);
  botao("Encerrar projeto").click();
  const dialogo = container().querySelector("dialog");
  assert.ok(dialogo, "abre o diálogo de confirmação");
  assert.match(dialogo.textContent, /Esporte/);
  assert.equal(chamadas.filter((c) => c.startsWith("PATCH")).length, 0, "não muda antes de confirmar");
  [...dialogo.querySelectorAll("button")].find((b) => b.textContent === "Cancelar").click();
  assert.equal(container().querySelector("dialog"), null);

  botao("Encerrar projeto").click();
  container().querySelector("dialog form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.ok(chamadas.includes("PATCH /projetos/p1/status"));
  assert.equal(container().querySelector("dialog"), null);
  assert.match(container().textContent, /Encerrado/);
  assert.ok(botao("Reativar projeto"));
});

test("detalhe: reativar (direção) manda status ativo; erro aparece no diálogo", async () => {
  simular({ listaDeProjetos: [{ id: "p1", nome: "Esporte", status: "encerrado" }] });
  const corpos = [];
  mudarStatus = (u, corpo) => {
    corpos.push(corpo);
    return resposta(404, { detail: "Projeto não encontrado" });
  };
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: { papel: "direcao", nome: "Jane" }, navegar: () => {} });
  assert.match(container().textContent, /Encerrado/);
  botao("Reativar projeto").click();
  const dialogo = container().querySelector("dialog");
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.deepEqual(corpos, [{ status: "ativo" }]);
  assert.match(dialogo.querySelector('[role="alert"]').textContent, /Projeto não encontrado/);
  assert.ok(container().querySelector("dialog"), "o diálogo continua aberto");
});

test("detalhe: voluntário não encerra; sem a lista de projetos o botão não aparece", async () => {
  simular();
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: { papel: "voluntario_financeiro", nome: "Lucas" }, navegar: () => {} });
  assert.equal(botao("Encerrar projeto"), undefined);
  simular({ listaDeProjetos: resposta(503, {}) });
  await detalhe.mostrar(container(), { parametros: { id: "o1" }, sessao: coord, navegar: () => {} });
  assert.match(container().textContent, /85% usado/);
  assert.equal(botao("Encerrar projeto"), undefined);
});
