// Lançamentos: a tela montada (jsdom) com a API simulada.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><span data-contador hidden>0</span><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const revogadas = [];
URL.createObjectURL = () => "blob:fake-1";
URL.revokeObjectURL = (u) => revogadas.push(u);
const { mostrar } = await import("../telas/lancamentos.js");

const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo, text: async () => JSON.stringify(corpo) });
const container = () => document.getElementById("c");
const esperar = () => new Promise((r) => setTimeout(r, 15));

const orcamentos = [
  { id: "o1", projeto_id: "p1", projeto_nome: "Leitura", saldo: 3800, percentual_consumido: 62, nivel_alerta: "normal", data_fim: "2026-12-31" },
  { id: "o2", projeto_id: "p2", projeto_nome: "Esporte", saldo: 500, percentual_consumido: 50, nivel_alerta: "normal", data_fim: "2026-12-31" },
];
const base = (id, extra) => ({ id, orcamento_id: "o1", projeto_id: "p1", valor: 180, categoria: "Materiais", autor_id: "marcos-vieira", status: "pendente", conciliado: false, data_despesa: "2026-10-26", criado_em: "2026-10-26T12:00:00Z", ...extra });
let lista;
let chamadas;
let detalhes;

function simular({ aprovar = () => resposta(200, { id: "l1" }), rejeitar = () => resposta(200, { id: "l1" }), blob = new window.Blob(["x"], { type: "image/jpeg" }) } = {}) {
  chamadas = [];
  globalThis.fetch = async (url, op = {}) => {
    const u = String(url);
    const metodo = op.method || "GET";
    chamadas.push(`${metodo} ${u.replace(/^https?:\/\/[^/]+/, "")}`);
    if (u.includes("/orcamentos")) return resposta(200, orcamentos);
    if (u.includes("/aprovar")) return aprovar();
    if (u.includes("/rejeitar")) return rejeitar(JSON.parse(op.body));
    if (u.includes("/arquivos/")) return { ok: true, status: 200, blob: async () => blob };
    const id = u.match(/\/lancamentos\/([^/?]+)$/)?.[1];
    if (id) return resposta(200, detalhes[id]);
    return resposta(200, lista);
  };
}

function preparar() {
  lista = [
    base("l1", { criado_em: "2026-10-26T12:00:00Z" }),
    base("l2", { orcamento_id: "o2", projeto_id: "p2", categoria: "Alimentação", valor: 92.5, autor_id: "ana-souza", criado_em: "2026-10-25T12:00:00Z" }),
    base("l3", { status: "aprovado", categoria: "Transporte", valor: 45, conciliado: true }),
    base("l4", { status: "rejeitado", categoria: "Outros" }),
  ];
  detalhes = {
    l1: { id: "l1", orcamento_id: "o1", valor: 180, descricao: "Livros <b>para</b> a oficina", categoria: "Materiais", data_despesa: "2026-10-26", status: "pendente", motivos_rejeicao_anteriores: [], comprovante_url: "/arquivos/l1.jpg", conciliado: false, referencia_extrato: null },
    l3: { id: "l3", orcamento_id: "o1", valor: 45, descricao: "Ônibus", categoria: "Transporte", data_despesa: "2026-10-26", status: "aprovado", motivos_rejeicao_anteriores: [], comprovante_url: null, conciliado: true, referencia_extrato: "EXT-77" },
    l4: { id: "l4", orcamento_id: "o1", valor: 180, descricao: "Coisa", categoria: "Outros", data_despesa: "2026-10-26", status: "rejeitado", motivo_rejeicao: "Foto ilegível", motivos_rejeicao_anteriores: [], comprovante_url: null, conciliado: false, referencia_extrato: null },
  };
}

const coord = { papel: "coordenacao", nome: "Luana Ferraz" };
const abas = () => [...container().querySelectorAll("button.filtro")].map((b) => b.textContent);

test("coordenação: abre em Aguardando, fila mais antiga primeiro, contagens e rótulos", async () => {
  preparar();
  simular();
  await mostrar(container(), { parametros: {}, sessao: coord, navegar() {} });
  assert.deepEqual(abas(), ["Aguardando2", "Aprovados1", "Rejeitados1", "Todos4"]);
  const linhas = [...container().querySelectorAll("tbody tr")];
  assert.equal(linhas.length, 2);
  assert.match(linhas[0].textContent, /Alimentação.*Ana Souza · Esporte.*26\/10.*92,50/);
  assert.match(linhas[1].textContent, /Materiais.*Marcos Vieira · Leitura/);
  assert.equal(document.querySelector("[data-contador]").textContent, "2");
});

test("voluntário abre em Aprovados e o painel não tem botões", async () => {
  preparar();
  simular();
  await mostrar(container(), { parametros: {}, sessao: { papel: "voluntario_financeiro", nome: "Ana" }, navegar() {} });
  assert.equal(container().querySelector(".filtro--ativo").textContent, "Aprovados1");
  container().querySelector("tbody tr").click();
  await esperar();
  const painel = container().querySelector(".painel-lateral");
  assert.match(painel.textContent, /Conciliado/);
  assert.match(painel.textContent, /EXT-77/);
  assert.equal(painel.querySelector(".btn--perigo"), null);
  assert.doesNotMatch(painel.textContent, /Saldo após/);
});

test("abrir=<id> abre o painel com detalhes, saldo após e texto sem HTML", async () => {
  preparar();
  simular();
  await mostrar(container(), { parametros: { status: "pendente", abrir: "l1" }, sessao: coord, navegar() {} });
  await esperar();
  const painel = container().querySelector(".painel-lateral");
  assert.match(painel.textContent, /Aguardando aprovação/);
  assert.match(painel.textContent, /R\$\s180,00/);
  assert.match(painel.textContent, /Livros <b>para<\/b> a oficina/);
  assert.equal(painel.querySelector("b"), null);
  assert.match(painel.textContent, /Saldo após.*R\$\s3\.620,00/);
  assert.match(painel.textContent, /Marcos Vieira/);
  assert.equal(painel.querySelector("img").getAttribute("src"), "blob:fake-1");
  assert.deepEqual([...painel.querySelectorAll("button")].map((b) => b.textContent).filter(Boolean), ["Rejeitar", "Aprovar"]);
});

test("comprovante em PDF vira link e o blob é liberado ao fechar", async () => {
  preparar();
  simular({ blob: new window.Blob(["x"], { type: "application/pdf" }) });
  revogadas.length = 0;
  await mostrar(container(), { parametros: { abrir: "l1" }, sessao: coord, navegar() {} });
  await esperar();
  assert.equal(container().querySelector(".painel-lateral a").textContent, "Abrir comprovante");
  container().querySelector("[aria-label='Fechar painel']").click();
  assert.equal(container().querySelector(".painel-lateral"), null);
  assert.deepEqual(revogadas, ["blob:fake-1"]);
});

test("rejeitado mostra o motivo", async () => {
  preparar();
  simular();
  await mostrar(container(), { parametros: { status: "rejeitado", abrir: "l4" }, sessao: coord, navegar() {} });
  await esperar();
  const painel = container().querySelector(".painel-lateral");
  assert.match(painel.textContent, /Motivo: Foto ilegível/);
  assert.equal(painel.querySelector(".btn--perigo"), null);
});

test("aprovar fecha o painel, recarrega a lista e atualiza o contador", async () => {
  preparar();
  simular({
    aprovar: () => {
      lista = lista.map((l) => (l.id === "l1" ? { ...l, status: "aprovado" } : l));
      return resposta(200, { id: "l1" });
    },
  });
  await mostrar(container(), { parametros: { abrir: "l1" }, sessao: coord, navegar() {} });
  await esperar();
  [...container().querySelectorAll(".painel-lateral button")].find((b) => b.textContent === "Aprovar").click();
  await esperar();
  assert.ok(chamadas.includes("PATCH /lancamentos/l1/aprovar"));
  assert.equal(container().querySelector(".painel-lateral"), null);
  assert.equal(container().querySelectorAll("tbody tr").length, 1);
  assert.equal(document.querySelector("[data-contador]").textContent, "1");
});

test("409 ao aprovar mostra a mensagem do servidor no painel", async () => {
  preparar();
  simular({ aprovar: () => resposta(409, { detail: "Lançamento já foi analisado." }) });
  await mostrar(container(), { parametros: { abrir: "l1" }, sessao: coord, navegar() {} });
  await esperar();
  [...container().querySelectorAll(".painel-lateral button")].find((b) => b.textContent === "Aprovar").click();
  await esperar();
  assert.match(container().querySelector(".painel-lateral [role=alert]").textContent, /já foi analisado/);
});

test("rejeitar: motivo vazio é barrado; com motivo envia e fecha", async () => {
  preparar();
  let enviado;
  simular({
    rejeitar: (corpo) => {
      enviado = corpo;
      lista = lista.map((l) => (l.id === "l1" ? { ...l, status: "rejeitado" } : l));
      return resposta(200, { id: "l1" });
    },
  });
  await mostrar(container(), { parametros: { abrir: "l1" }, sessao: coord, navegar() {} });
  await esperar();
  [...container().querySelectorAll(".painel-lateral button")].find((b) => b.textContent === "Rejeitar").click();
  const dialogo = container().querySelector("dialog");
  assert.ok(dialogo);
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  assert.match(dialogo.querySelector("[role=alert]").textContent, /Informe o motivo da rejeição\./);
  assert.equal(enviado, undefined);
  dialogo.querySelector("textarea").value = "  Recibo ilegível ";
  dialogo.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();
  assert.deepEqual(enviado, { motivo: "Recibo ilegível" });
  assert.equal(container().querySelector("dialog"), null);
  assert.equal(container().querySelector(".painel-lateral"), null);
  assert.equal(document.querySelector("[data-contador]").textContent, "1");
});

test("abas e filtro de projeto navegam pela rota", async () => {
  preparar();
  simular();
  const destinos = [];
  await mostrar(container(), { parametros: { orcamento: "o1" }, sessao: coord, navegar: (h) => destinos.push(h) });
  assert.deepEqual(abas(), ["Aguardando1", "Aprovados1", "Rejeitados1", "Todos3"]);
  container().querySelectorAll("button.filtro")[1].click();
  assert.equal(destinos[0], "#/lancamentos?status=aprovado&orcamento=o1");
  const seletor = container().querySelector("select");
  seletor.value = "o2";
  seletor.dispatchEvent(new window.Event("change"));
  assert.equal(destinos[1], "#/lancamentos?status=pendente&orcamento=o2");
});

test("falha da API mostra mensagem", async () => {
  globalThis.fetch = async () => { throw new Error("offline"); };
  await mostrar(container(), { parametros: {}, sessao: coord, navegar() {} });
  assert.match(container().textContent, /Não foi possível carregar os lançamentos/);
});
