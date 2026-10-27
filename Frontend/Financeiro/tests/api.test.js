import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import {
  API_PADRAO,
  criarRascunho,
  editarOrcamento,
  listarLancamentos,
  listarOrcamentos,
  rejeitarLancamento,
  requisitar,
  salvarAcesso,
} from "../base/api.js";
import { encerrarSessao, salvarSessao } from "../base/sessao.js";

let chamadas;

beforeEach(() => {
  const dados = new Map();
  globalThis.localStorage = {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
  chamadas = [];
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  salvarAcesso("token-de-teste");
});

test("api envia papel e usuário da sessão", async () => {
  salvarSessao({ papel: "coordenacao", nome: "Ana Souza" });
  const r = await requisitar("/projetos");
  assert.deepEqual(r, { status: 200, corpo: { ok: true } });
  assert.equal(chamadas[0].url, `${API_PADRAO}/projetos`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer token-de-teste");
  assert.equal(chamadas[0].headers["X-Papel-Usuario"], "coordenacao");
  assert.equal(chamadas[0].headers["X-Usuario-Id"], "ana-souza");
});

test("sem sessão não envia papel nem usuário", async () => {
  encerrarSessao();
  await requisitar("/projetos");
  assert.equal(chamadas[0].headers.Authorization, "Bearer token-de-teste");
  assert.equal("X-Papel-Usuario" in chamadas[0].headers, false);
  assert.equal("X-Usuario-Id" in chamadas[0].headers, false);
});

test("api devolve status 0 sem conexão", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("rede fora");
  };
  assert.deepEqual(await requisitar("/projetos"), { status: 0, corpo: null });
});

test("listarLancamentos omite filtros indefinidos", async () => {
  await listarLancamentos({ status: "pendente", orcamento_id: undefined, meus: true, conciliado: false });
  assert.equal(chamadas[0].url, `${API_PADRAO}/lancamentos?status=pendente&meus=true&conciliado=false`);
  await listarLancamentos();
  assert.equal(chamadas[1].url, `${API_PADRAO}/lancamentos`);
});

test("listarOrcamentos com e sem data de vigência", async () => {
  await listarOrcamentos("2026-10-27");
  await listarOrcamentos();
  assert.equal(chamadas[0].url, `${API_PADRAO}/orcamentos?vigentes_em=2026-10-27`);
  assert.equal(chamadas[1].url, `${API_PADRAO}/orcamentos`);
});

test("corpos JSON e métodos das escritas", async () => {
  await rejeitarLancamento("l/1", "sem nota");
  await editarOrcamento("o1", { valor_total: 10 });
  assert.equal(chamadas[0].url, `${API_PADRAO}/lancamentos/l%2F1/rejeitar`);
  assert.equal(chamadas[0].method, "PATCH");
  assert.equal(chamadas[0].body, JSON.stringify({ motivo: "sem nota" }));
  assert.equal(chamadas[0].headers["Content-Type"], "application/json");
  assert.equal(chamadas[1].method, "PATCH");
  assert.equal(chamadas[1].url, `${API_PADRAO}/orcamentos/o1`);
});

test("criarRascunho envia o comprovante em multipart", async () => {
  await criarRascunho(new File([new Uint8Array(4)], "nota.jpg", { type: "image/jpeg" }));
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].body.get("comprovante").name, "nota.jpg");
  assert.equal("Content-Type" in chamadas[0].headers, false);
});
