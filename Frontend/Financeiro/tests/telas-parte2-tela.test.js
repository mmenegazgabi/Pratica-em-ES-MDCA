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
const esperar = (ms = 15) => new Promise((r) => setTimeout(r, ms));
const botao = (texto) => [...container().querySelectorAll("button")].find((b) => b.textContent.includes(texto));

const orc = { id: "o1", projeto_id: "p1", projeto_nome: "Leitura", valor_total: 10000, saldo: 3800, data_inicio: "2026-01-01", data_fim: "2026-12-31", categorias_despesa: ["Materiais"] };
let lancamentos;
let extrato;
let chamadas;

// ---------- Conciliação ----------

function simularConciliacao({ conciliar = () => resposta(200, {}), importar = () => resposta(201, { importados: 0, ignorados_repetidos: 0, itens: [] }), listarExtrato = () => resposta(200, extrato) } = {}) {
  chamadas = [];
  globalThis.fetch = async (url, op = {}) => {
    const u = String(url).replace(/^https?:\/\/[^/]+/, "");
    const metodo = op.method || "GET";
    chamadas.push({ metodo, url: u, corpo: typeof op.body === "string" ? JSON.parse(op.body) : op.body ?? null });
    if (metodo === "PATCH") return conciliar(u);
    if (metodo === "POST" && u === "/extrato") return importar(op.body);
    if (u.startsWith("/extrato")) return listarExtrato(u);
    if (u.startsWith("/orcamentos")) return resposta(200, [orc]);
    return resposta(200, lancamentos);
  };
}

const voluntario = { papel: "voluntario_financeiro", nome: "Lucas Prado" };
const papelaria = { id: "e-1", data: "2026-10-27", descricao: "PIX PAPELARIA CENTRAL", valor: -180, importado_em: "2026-10-28T10:00:00Z", conciliado_com: null };
const padaria = { id: "e-2", data: "2026-10-09", descricao: "DEB PADARIA ESPERANCA", valor: -76.4, importado_em: "2026-10-28T10:00:00Z", conciliado_com: null };

test("conciliação: extrato vem da API (em aberto), marca os dois e concilia com o id do item", async () => {
  lancamentos = [
    { id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, autor_id: "marcos-vieira", data_despesa: "2026-10-26", aprovado_em: "2026-10-26T10:00:00Z" },
    { id: "l2", orcamento_id: "o1", categoria: "Lanche <b>x</b>", valor: 76.4, status: "aprovado", conciliado: false, aprovado_em: "2026-09-01T10:00:00Z" },
  ];
  extrato = [padaria, papelaria];
  simularConciliacao();
  await conciliacao.mostrar(container(), { sessao: voluntario });
  assert.ok(chamadas.some((c) => c.url === "/extrato?em_aberto=true"));
  const t = container().textContent;
  assert.match(t, /2 lançamentos aprovados sem vínculo com o extrato/);
  assert.match(t, /aberto há \d+ dias/);
  assert.match(t, /−R\$\s180,00/);
  assert.doesNotMatch(t, /exemplo/i);
  assert.ok(container().textContent.includes("Lanche <b>x</b>"), "texto do usuário entra como texto");

  const [colunaExtrato] = container().querySelectorAll('[role="radiogroup"]');
  [...colunaExtrato.querySelectorAll('[role="radio"]')].find((b) => b.textContent.includes("PAPELARIA")).click();
  const sugerido = [...container().querySelectorAll('[role="radiogroup"]')[1].querySelectorAll('[role="radio"]')].find((b) => b.textContent.includes("mesmo valor"));
  assert.ok(sugerido, "lançamento de mesmo valor (sem o sinal) aparece sugerido");
  assert.match(sugerido.textContent, /Materiais/);
  sugerido.click();
  assert.doesNotMatch(container().textContent, /Atenção: o lançamento é de/);

  lancamentos = [{ ...lancamentos[0], conciliado: true, referencia_extrato: "e-1" }, lancamentos[1]];
  extrato = [padaria];
  botao("Conciliar").click();
  await esperar();
  const patch = chamadas.find((c) => c.metodo === "PATCH");
  assert.equal(patch.url, "/lancamentos/l1/conciliar");
  assert.deepEqual(patch.corpo, { referencia_extrato: "e-1" });
  assert.match(container().textContent, /conciliado com Materiais/);
  assert.doesNotMatch(container().querySelectorAll('[role="radiogroup"]')[0].textContent, /PAPELARIA/);
  assert.equal(chamadas.filter((c) => c.url === "/extrato?em_aberto=true").length, 2, "recarrega o extrato");
  assert.doesNotMatch(container().textContent, /null/);
  assert.match(container().textContent, /1 lançamento aprovado sem vínculo/);
});

test("conciliação: erro do servidor aparece e nada some da lista", async () => {
  lancamentos = [{ id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, aprovado_em: "2026-10-26T10:00:00Z" }];
  extrato = [papelaria];
  simularConciliacao({ conciliar: () => resposta(400, { detail: "Item do extrato já conciliado com outro lançamento." }) });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  container().querySelectorAll('[role="radiogroup"]')[0].querySelector('[role="radio"]').click();
  container().querySelectorAll('[role="radiogroup"]')[1].querySelector('[role="radio"]').click();
  botao("Conciliar").click();
  await esperar();
  assert.match(container().querySelector('[role="alert"]').textContent, /já conciliado com outro lançamento/);
  assert.match(container().textContent, /1 lançamento aprovado sem vínculo/);
  assert.match(container().textContent, /PAPELARIA/);
});

test("conciliação: extrato vazio pede a importação", async () => {
  lancamentos = [];
  extrato = [];
  simularConciliacao();
  await conciliacao.mostrar(container(), { sessao: voluntario });
  assert.match(container().textContent, /Nenhum item do extrato em aberto\. Importe o arquivo do banco\./);
});

test("conciliação: falha ao carregar o extrato aparece na coluna, o resto continua", async () => {
  lancamentos = [{ id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, aprovado_em: "2026-10-26T10:00:00Z" }];
  simularConciliacao({ listarExtrato: () => resposta(503, { detail: "x" }) });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  assert.match(container().querySelector('[role="alert"]').textContent, /Não foi possível carregar o extrato/);
  assert.match(container().textContent, /1 lançamento aprovado sem vínculo/);
});

function escolherArquivo(arquivo) {
  const entrada = container().querySelector('input[type="file"]');
  Object.defineProperty(entrada, "files", { value: [arquivo], configurable: true });
  entrada.dispatchEvent(new window.Event("change"));
}

test("conciliação: Importar extrato (CSV) envia o arquivo, mostra o resultado e recarrega", async () => {
  lancamentos = [];
  extrato = [];
  simularConciliacao({
    importar: (corpo) => {
      assert.equal(corpo.get("arquivo").name, "banco.csv");
      extrato = [papelaria];
      return resposta(201, { importados: 3, ignorados_repetidos: 2, itens: [papelaria] });
    },
  });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  const importar = botao("Importar extrato (CSV)");
  assert.ok(importar);
  const entrada = container().querySelector('input[type="file"]');
  assert.equal(entrada.getAttribute("accept"), ".csv,text/csv");
  let abriu = false;
  entrada.click = () => { abriu = true; };
  importar.click();
  assert.ok(abriu, "o botão abre a escolha do arquivo");
  escolherArquivo(new File(["data;descricao;valor\n"], "banco.csv", { type: "text/csv" }));
  await esperar();
  assert.ok(chamadas.some((c) => c.metodo === "POST" && c.url === "/extrato"));
  assert.match(container().querySelector('[role="status"]').textContent, /3 itens importados, 2 repetidos ignorados/);
  assert.match(container().textContent, /PAPELARIA/);
});

test("conciliação: erro da importação (com a linha) aparece na tela", async () => {
  lancamentos = [];
  extrato = [];
  simularConciliacao({ importar: () => resposta(400, { detail: "Linha 3: valor inválido." }) });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  escolherArquivo(new File(["x"], "banco.csv", { type: "text/csv" }));
  await esperar();
  assert.match(container().querySelector('[role="alert"]').textContent, /Linha 3: valor inválido\./);
});

test("conciliação: arquivo acima de 1 MB nem é enviado", async () => {
  lancamentos = [];
  extrato = [];
  simularConciliacao({ importar: () => assert.fail("não deveria enviar") });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  escolherArquivo(new File([new Uint8Array(1024 * 1024 + 1)], "grande.csv", { type: "text/csv" }));
  await esperar();
  assert.match(container().querySelector('[role="alert"]').textContent, /Arquivo acima de 1 MB/);
});

test("conciliação: só o voluntário financeiro importa (a tela é dele)", async () => {
  lancamentos = [];
  extrato = [];
  simularConciliacao();
  await conciliacao.mostrar(container(), { sessao: { papel: "coordenacao", nome: "Luana" } });
  assert.equal(botao("Importar extrato (CSV)"), undefined);
  assert.equal(container().querySelector('input[type="file"]'), null);
});

test("conciliação: importação em andamento bloqueia Conciliar, e conciliação bloqueia a importação", async () => {
  lancamentos = [{ id: "l1", orcamento_id: "o1", categoria: "Materiais", valor: 180, status: "aprovado", conciliado: false, aprovado_em: "2026-10-26T10:00:00Z" }];
  extrato = [papelaria];
  let terminarImportacao;
  let terminarConciliacao;
  simularConciliacao({
    importar: () => new Promise((r) => { terminarImportacao = () => r(resposta(201, { importados: 0, ignorados_repetidos: 1, itens: [] })); }),
    conciliar: () => new Promise((r) => { terminarConciliacao = () => r(resposta(200, {})); }),
  });
  await conciliacao.mostrar(container(), { sessao: voluntario });
  container().querySelectorAll('[role="radiogroup"]')[0].querySelector('[role="radio"]').click();
  container().querySelectorAll('[role="radiogroup"]')[1].querySelector('[role="radio"]').click();
  escolherArquivo(new File(["x"], "banco.csv", { type: "text/csv" }));
  await esperar();
  assert.equal(botao("Conciliar").disabled, true);
  terminarImportacao();
  await esperar();
  assert.equal(botao("Conciliar").disabled, false);
  botao("Conciliar").click();
  await esperar();
  assert.equal(botao("Importar extrato (CSV)").disabled, true);
  terminarConciliacao();
  await esperar();
  assert.equal(botao("Importar extrato (CSV)").disabled, false);
});

// ---------- Relatórios ----------

let baixados;
dom.window.HTMLAnchorElement.prototype.click = function () {
  baixados.push({ nome: this.getAttribute("download"), href: this.getAttribute("href") });
};
URL.createObjectURL = () => "blob:teste";
URL.revokeObjectURL = () => {};

function simularRelatorios(relatorio) {
  chamadas = [];
  baixados = [];
  globalThis.fetch = async (url, op = {}) => {
    const u = String(url).replace(/^https?:\/\/[^/]+/, "");
    chamadas.push({ metodo: op.method || "GET", url: u });
    if (u.startsWith("/relatorios")) return relatorio(u);
    if (u.startsWith("/orcamentos")) return resposta(200, [orc]);
    return resposta(200, lancamentos);
  };
}

const arquivo = (nome) =>
  new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: nome ? { "Content-Disposition": `attachment; filename="${nome}"` } : {} });

test("relatórios: prévia só com aprovados do período e aviso de não conciliados", async () => {
  lancamentos = [
    { orcamento_id: "o1", status: "aprovado", data_despesa: "2026-03-10", categoria: "Materiais", descricao: "Livros", valor: 100, conciliado: false },
    { orcamento_id: "o1", status: "aprovado", data_despesa: "2026-05-10", categoria: "Materiais", descricao: "Cola", valor: 20, conciliado: true },
  ];
  simularRelatorios(() => assert.fail("não gera sem clicar"));
  await relatorios.mostrar(container(), { parametros: { orcamento: "o1" } });
  await esperar();
  const t = container().textContent;
  assert.match(t, /Prestação de contas — Leitura/);
  assert.match(t, /Livros/);
  assert.match(t, /1 lançamento do período ainda não foi conciliado/);
  assert.doesNotMatch(t, /\[object/);
  assert.deepEqual([...container().querySelectorAll('[aria-label="Formato"] [role="radio"]')].map((b) => b.textContent), ["PDF", "Planilha (XLSX)"]);
  const pedido = chamadas.find((c) => c.url.startsWith("/lancamentos"));
  assert.match(pedido.url, /orcamento_id=o1/);
  assert.match(pedido.url, /status=aprovado/);

  const fim = container().querySelector("#rel-fim");
  fim.value = "2025-01-01";
  fim.dispatchEvent(new window.Event("change"));
  assert.match(container().textContent, /O fim do período não pode ser antes do início/);
  assert.equal(botao("Gerar relatório").disabled, true);
});

test("relatórios: Gerar baixa o PDF oficial da API com o nome do Content-Disposition", async () => {
  lancamentos = [];
  simularRelatorios(() => arquivo("prestacao-contas-leitura.pdf"));
  let imprimiu = false;
  window.print = () => { imprimiu = true; };
  await relatorios.mostrar(container(), { parametros: { orcamento: "o1" } });
  await esperar();
  const inicio = container().querySelector("#rel-inicio");
  inicio.value = "2026-03-01";
  inicio.dispatchEvent(new window.Event("change"));
  botao("Gerar relatório").click();
  await esperar();
  const pedido = chamadas.find((c) => c.url.startsWith("/relatorios"));
  assert.equal(pedido.url, "/relatorios/prestacao-contas?projeto_id=p1&data_inicio=2026-03-01&data_fim=2026-12-31&formato=pdf");
  assert.deepEqual(baixados, [{ nome: "prestacao-contas-leitura.pdf", href: "blob:teste" }]);
  assert.equal(imprimiu, false, "não usa mais a impressão do navegador");
  assert.equal(botao("Gerar relatório").disabled, false);
});

test("relatórios: Planilha (XLSX) pede formato xlsx; sem Content-Disposition usa o nome padrão", async () => {
  lancamentos = [];
  simularRelatorios(() => arquivo(null));
  await relatorios.mostrar(container(), { parametros: { orcamento: "o1" } });
  await esperar();
  [...container().querySelectorAll('[aria-label="Formato"] [role="radio"]')].find((b) => b.textContent === "Planilha (XLSX)").click();
  botao("Gerar relatório").click();
  await esperar();
  assert.match(chamadas.find((c) => c.url.startsWith("/relatorios")).url, /formato=xlsx$/);
  assert.deepEqual(baixados.map((b) => b.nome), ["prestacao-de-contas-leitura-2026-01-01-a-2026-12-31.xlsx"]);
});

for (const [caso, gerar, esperado] of [
  ["404", () => resposta(404, { detail: "Projeto não encontrado." }), /Projeto não encontrado\./],
  ["422", () => resposta(422, { detail: "O período informado é inválido." }), /O período informado é inválido\./],
  ["422 de validação", () => resposta(422, { detail: [{ msg: "x" }] }), /Não foi possível gerar o relatório/],
  ["403", () => resposta(403, { detail: "Papel sem permissão para esta operação." }), /Papel sem permissão/],
  ["rede", () => { throw new TypeError("offline"); }, /Não foi possível falar com o servidor/],
]) {
  test(`relatórios: erro ${caso} aparece na tela e nada é baixado`, async () => {
    lancamentos = [];
    simularRelatorios(gerar);
    await relatorios.mostrar(container(), { parametros: { orcamento: "o1" } });
    await esperar();
    botao("Gerar relatório").click();
    await esperar();
    const alerta = [...container().querySelectorAll('[role="alert"]')].find((a) => !a.hidden);
    assert.match(alerta.textContent, esperado);
    assert.deepEqual(baixados, []);
  });
}
