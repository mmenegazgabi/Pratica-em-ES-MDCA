// Conciliação e Relatórios montados no jsdom com a API simulada (Auditoria: auditoria-tela.test.js).
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const conciliacao = await import("../telas/conciliacao.js");
const relatorios = await import("../telas/relatorios.js");

const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo, text: async () => JSON.stringify(corpo) });
const container = () => document.getElementById("c");
const esperar = () => new Promise((r) => setTimeout(r, 15));

const orc = { id: "o1", projeto_id: "p1", projeto_nome: "Leitura", valor_total: 10000, saldo: 3800, data_inicio: "2026-01-01", data_fim: "2026-12-31", categorias_despesa: ["Materiais"] };
let lancamentos;
let chamadas;

function simular({ conciliar = () => resposta(200, {}) } = {}) {
  chamadas = [];
  globalThis.fetch = async (url, op = {}) => {
    const u = String(url).replace(/^https?:\/\/[^/]+/, "");
    chamadas.push({ metodo: op.method || "GET", url: u, corpo: op.body ? JSON.parse(op.body) : null });
    if (op.method === "PATCH") return conciliar(u);
    if (u.startsWith("/orcamentos")) return resposta(200, [orc]);
    return resposta(200, lancamentos);
  };
}

const voluntario = { papel: "voluntario_financeiro", nome: "Lucas Prado" };

test("conciliação: marca extrato e lançamento de mesmo valor e concilia com a referência", async () => {
  lancamentos = [
    { id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, autor_id: "marcos-vieira", data_despesa: "2026-10-26", aprovado_em: "2026-10-26T10:00:00Z" },
    { id: "l2", orcamento_id: "o1", categoria: "Lanche <b>x</b>", valor: 76.4, status: "aprovado", conciliado: false, aprovado_em: "2026-09-01T10:00:00Z" },
  ];
  simular();
  await conciliacao.mostrar(container(), { sessao: voluntario });
  const t = container().textContent;
  assert.match(t, /2 lançamentos aprovados sem vínculo com o extrato/);
  assert.match(t, /aberto há \d+ dias/);
  assert.ok(container().textContent.includes("Lanche <b>x</b>"), "texto do usuário entra como texto");

  const [extrato, aprovados] = container().querySelectorAll('[role="radiogroup"]');
  const itemExtrato = [...extrato.querySelectorAll('[role="radio"]')].find((b) => b.textContent.includes("PAPELARIA"));
  itemExtrato.click();
  const sugerido = [...container().querySelectorAll('[role="radiogroup"]')[1].querySelectorAll('[role="radio"]')].find((b) => b.textContent.includes("mesmo valor"));
  assert.ok(sugerido, "lançamento de mesmo valor aparece sugerido");
  sugerido.click();

  lancamentos = [{ ...lancamentos[0], conciliado: true, referencia_extrato: "EXT-1027-04" }, lancamentos[1]];
  const botao = [...container().querySelectorAll("button")].find((b) => b.textContent === "Conciliar");
  botao.click();
  await esperar();
  const patch = chamadas.find((c) => c.metodo === "PATCH");
  assert.equal(patch.url, "/lancamentos/l1/conciliar");
  assert.deepEqual(patch.corpo, { referencia_extrato: "EXT-1027-04" });
  assert.match(container().textContent, /conciliado com Materiais/);
  const extratoDepois = container().querySelectorAll('[role="radiogroup"]')[0].textContent;
  assert.doesNotMatch(extratoDepois, /PIX PAPELARIA CENTRAL/);
  assert.doesNotMatch(container().textContent, /null/);
  assert.match(container().textContent, /1 lançamento aprovado sem vínculo/);
});

test("conciliação: erro do servidor aparece e nada some da lista", async () => {
  lancamentos = [{ id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, aprovado_em: "2026-10-26T10:00:00Z" }];
  simular({ conciliar: () => resposta(409, { detail: "Lançamento já está conciliado com outra referência do extrato" }) });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  const grupos = container().querySelectorAll('[role="radiogroup"]');
  grupos[0].querySelector('[role="radio"]').click();
  container().querySelectorAll('[role="radiogroup"]')[1].querySelector('[role="radio"]').click();
  [...container().querySelectorAll("button")].find((b) => b.textContent === "Conciliar").click();
  await esperar();
  assert.match(container().querySelector('[role="alert"]').textContent, /já está conciliado/);
  assert.match(container().textContent, /1 lançamento aprovado sem vínculo/);
});

test("relatórios: prévia só com aprovados do período e aviso de não conciliados", async () => {
  lancamentos = [
    { orcamento_id: "o1", status: "aprovado", data_despesa: "2026-03-10", categoria: "Materiais", descricao: "Livros", valor: 100, conciliado: false },
    { orcamento_id: "o1", status: "aprovado", data_despesa: "2026-05-10", categoria: "Materiais", descricao: "Cola", valor: 20, conciliado: true },
  ];
  simular();
  await relatorios.mostrar(container(), { parametros: { orcamento: "o1" } });
  await esperar();
  const t = container().textContent;
  assert.match(t, /Prestação de contas — Leitura/);
  assert.match(t, /Livros/);
  assert.match(t, /1 lançamento do período ainda não foi conciliado/);
  assert.doesNotMatch(t, /\[object/);
  assert.deepEqual([...container().querySelectorAll('[aria-label="Formato"] [role="radio"]')].map((b) => b.textContent), ["PDF", "Planilha"]);
  const pedido = chamadas.find((c) => c.url.startsWith("/lancamentos"));
  assert.match(pedido.url, /orcamento_id=o1/);
  assert.match(pedido.url, /status=aprovado/);

  const fim = container().querySelector("#rel-fim");
  fim.value = "2025-01-01";
  fim.dispatchEvent(new window.Event("change"));
  assert.match(container().textContent, /O fim do período não pode ser antes do início/);
  assert.equal([...container().querySelectorAll("button")].find((b) => b.textContent.includes("Gerar relatório")).disabled, true);
});
