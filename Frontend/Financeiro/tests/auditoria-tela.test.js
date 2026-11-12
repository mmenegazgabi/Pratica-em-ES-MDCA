// T-34 · US-08: tela Auditoria lida de GET /auditoria (jsdom, API simulada).
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><div id="c"></div></body>', { url: "http://localhost/Financeiro/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const auditoria = await import("../telas/auditoria.js");

const container = () => document.getElementById("c");
const esperar = () => new Promise((r) => setTimeout(r, 15));
const resposta = (status, corpo) => ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => corpo });

const evento = (id, quando, quem, acao, alvo, codigo) => ({ id, quando, quem, acao, alvo, codigo, usuario_id: quem, alvo_tipo: "lancamento", alvo_id: `l-${id}`, detalhes: {} });
const PRIMEIRA = [
  evento(3, "2026-11-11T21:06:00+00:00", "Luana Ferraz", "Aprovou despesa", "Divertidamente · Materiais · R$ 87,50", "aprovar_lancamento"),
  evento(2, "2026-11-11T20:40:00+00:00", "Lucas Prado", "Conciliou lançamento", "Divertidamente · R$ 180,00 · EXT-42", "conciliar_lancamento"),
  evento(1, "2026-11-11T13:15:00+00:00", "Marcos Vieira", "Acesso negado", "PATCH /lancamentos/l-9/aprovar", "acesso_negado"),
];

let chamadas;
function simular(responder) {
  chamadas = [];
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    const params = Object.fromEntries(u.searchParams);
    chamadas.push({ caminho: u.pathname, params });
    return responder(params);
  };
}
const linhas = () => [...container().querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent));
const botao = (texto) => [...container().querySelectorAll("button")].find((b) => b.textContent === texto);

test("lê a trilha da API, sem dados de exemplo, com o horário de Brasília", async () => {
  simular(() => resposta(200, { itens: PRIMEIRA, total: 3, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());

  assert.deepEqual(chamadas, [{ caminho: "/auditoria", params: { modulo: "financeiro", pagina: "1", tamanho: "50" } }]);
  assert.deepEqual(linhas()[0], ["11/11/2026 18:06", "Luana Ferraz", "Aprovou despesa", "Divertidamente · Materiais · R$ 87,50"]);
  assert.equal(linhas().length, 3);
  assert.match(container().textContent, /1–3 de 3/);
  assert.doesNotMatch(container().textContent, /exemplo/i);
});

test("só leitura: nenhum botão de editar ou apagar registro", async () => {
  simular(() => resposta(200, { itens: PRIMEIRA, total: 3, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());
  const textos = [...container().querySelectorAll("button")].map((b) => b.textContent);
  assert.deepEqual(textos, ["Aplicar", "Anterior", "Próxima"]);
});

test("a busca filtra a página carregada sem novo pedido", async () => {
  simular(() => resposta(200, { itens: PRIMEIRA, total: 3, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());
  const busca = container().querySelector("#auditoria-busca");
  busca.value = "concil";
  busca.dispatchEvent(new window.Event("input"));

  assert.equal(chamadas.length, 1);
  assert.deepEqual(linhas().map((l) => l[1]), ["Lucas Prado"]);
  busca.value = "nada disso";
  busca.dispatchEvent(new window.Event("input"));
  assert.match(container().textContent, /Nenhuma ação desta página corresponde à busca/);
});

test("filtro de período vai para a API e volta para a primeira página", async () => {
  simular((p) => resposta(200, { itens: p.desde ? PRIMEIRA.slice(0, 1) : PRIMEIRA, total: p.desde ? 1 : 3, pagina: Number(p.pagina), tamanho: 50 }));
  await auditoria.mostrar(container());
  container().querySelector("#auditoria-desde").value = "2026-11-11";
  container().querySelector("#auditoria-ate").value = "2026-11-11";
  container().querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();

  assert.deepEqual(chamadas.at(-1).params, { modulo: "financeiro", desde: "2026-11-11", ate: "2026-11-11", pagina: "1", tamanho: "50" });
  assert.equal(linhas().length, 1);
});

test("período invertido avisa e não consulta", async () => {
  simular(() => resposta(200, { itens: PRIMEIRA, total: 3, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());
  container().querySelector("#auditoria-desde").value = "2026-11-12";
  container().querySelector("#auditoria-ate").value = "2026-11-01";
  container().querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await esperar();

  assert.equal(chamadas.length, 1);
  assert.match(container().querySelector('[role="alert"]').textContent, /O fim do período não pode ser antes do início/);
});

test("páginas: mostra o intervalo e anda para a próxima e a anterior", async () => {
  const pagina = (n) => Array.from({ length: n === 3 ? 20 : 50 }, (_, i) => evento(i, "2026-11-10T12:00:00+00:00", `Pessoa ${n}-${i}`, "Aprovou despesa", "x", "aprovar_lancamento"));
  simular((p) => resposta(200, { itens: pagina(Number(p.pagina)), total: 120, pagina: Number(p.pagina), tamanho: 50 }));
  await auditoria.mostrar(container());
  assert.match(container().textContent, /1–50 de 120/);
  assert.equal(botao("Anterior").disabled, true);

  botao("Próxima").click();
  await esperar();
  assert.equal(chamadas.at(-1).params.pagina, "2");
  assert.match(container().textContent, /51–100 de 120/);

  botao("Próxima").click();
  await esperar();
  assert.match(container().textContent, /101–120 de 120/);
  assert.equal(botao("Próxima").disabled, true);

  botao("Anterior").click();
  await esperar();
  assert.equal(chamadas.at(-1).params.pagina, "2");
});

test("sem registros e erro do servidor aparecem na tela", async () => {
  simular(() => resposta(200, { itens: [], total: 0, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());
  assert.match(container().textContent, /Nenhuma ação registrada neste período/);
  assert.equal(botao("Próxima"), undefined);

  simular(() => resposta(403, { detail: "Ação permitida apenas para: coordenacao, direcao." }));
  await auditoria.mostrar(container());
  assert.match(container().querySelector(".aviso-tela").textContent, /Ação permitida apenas para: coordenacao, direcao\./);
});

test("texto vindo da API entra como texto", async () => {
  simular(() => resposta(200, { itens: [evento(9, "2026-11-11T12:00:00+00:00", "<img src=x>", "Aprovou despesa", "<b>x</b>", "aprovar_lancamento")], total: 1, pagina: 1, tamanho: 50 }));
  await auditoria.mostrar(container());
  assert.equal(container().querySelector("img"), null);
  assert.deepEqual(linhas()[0].slice(1), ["<img src=x>", "Aprovou despesa", "<b>x</b>"]);
});
