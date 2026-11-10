import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import * as modulo from "../base/api.js";
import {
  API_PADRAO,
  configurarSaida,
  criarRascunho,
  editarOrcamento,
  listarLancamentos,
  listarOrcamentos,
  rejeitarLancamento,
  requisitar,
} from "../base/api.js";
import { sessaoDeTeste } from "./ajuda-sessao.js";

let chamadas;
let destinos;

function armazemFalso() {
  const dados = new Map();
  return {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
}

beforeEach(() => {
  globalThis.localStorage = armazemFalso();
  globalThis.sessionStorage = armazemFalso();
  destinos = [];
  globalThis.window = { location: { assign: (destino) => destinos.push(destino) } };
  chamadas = [];
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  configurarSaida("../");
  sessaoDeTeste({ papeis: ["coordenacao"], token: "tok-sessao" });
});

test("saíram o código de acesso fixo e o salvo no aparelho", () => {
  for (const nome of ["TOKEN_FIXO", "salvarAcesso", "esquecerAcesso", "tokenSalvo"]) assert.equal(nome in modulo, false, nome);
});

test("requisições levam o token da sessão e o papel em uso, sem X-Usuario-Id", async () => {
  const r = await requisitar("/projetos");
  assert.deepEqual(r, { status: 200, corpo: { ok: true } });
  assert.equal(chamadas[0].url, `${API_PADRAO}/projetos`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer tok-sessao");
  assert.equal(chamadas[0].headers["X-Papel-Usuario"], "coordenacao");
  assert.equal("X-Usuario-Id" in chamadas[0].headers, false);
});

test("o papel em uso é o escolhido entre os da pessoa", async () => {
  sessaoDeTeste({ papeis: ["coordenacao", "educador"], papel: "educador" });
  await requisitar("/rascunhos");
  assert.equal(chamadas[0].headers["X-Papel-Usuario"], "educador");
});

test("sem sessão não envia token nem papel", async () => {
  localStorage.removeItem("mdca.sessao");
  await requisitar("/projetos");
  assert.equal("Authorization" in chamadas[0].headers, false);
  assert.equal("X-Papel-Usuario" in chamadas[0].headers, false);
});

test("endereço da API vem da plataforma (chave mdca.api)", async () => {
  localStorage.setItem("mdca.api", "http://localhost:8000/");
  await requisitar("/projetos");
  assert.equal(chamadas[0].url, "http://localhost:8000/projetos");
});

test("401 apaga a sessão e o papel e volta para a página inicial", async () => {
  sessaoDeTeste({ papeis: ["coordenacao", "direcao"], papel: "direcao" });
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Sessão expirada." }), { status: 401 });
  const r = await requisitar("/projetos");
  assert.equal(r.status, 401);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);
  assert.deepEqual(destinos, ["../"]);
});

test("configurarSaida muda o destino do 401 (app do celular)", async () => {
  configurarSaida("../../");
  globalThis.fetch = async () => new Response(null, { status: 401 });
  await requisitar("/rascunhos");
  assert.deepEqual(destinos, ["../../"]);
});

test("baixarArquivo também trata o 401", async () => {
  globalThis.fetch = async () => new Response(null, { status: 401 });
  const r = await modulo.baixarArquivo("/comprovantes/a.jpg");
  assert.deepEqual(r, { status: 401, blob: null });
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.deepEqual(destinos, ["../"]);
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

test("baixarRelatorio pede o relatório oficial e usa o nome do Content-Disposition", async () => {
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    return new Response(new Uint8Array([37, 80, 68, 70]), {
      status: 200,
      headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="prestacao-contas-leitura-2026-01-01-a-2026-12-31.pdf"' },
    });
  };
  const r = await modulo.baixarRelatorio({ projeto_id: "p 1", data_inicio: "2026-01-01", data_fim: "2026-12-31", formato: "pdf" });
  assert.equal(chamadas[0].url, `${API_PADRAO}/relatorios/prestacao-contas?projeto_id=p+1&data_inicio=2026-01-01&data_fim=2026-12-31&formato=pdf`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer tok-sessao");
  assert.equal(r.status, 200);
  assert.equal(r.nome, "prestacao-contas-leitura-2026-01-01-a-2026-12-31.pdf");
  assert.equal(r.blob.size, 4);
});

test("baixarRelatorio sem Content-Disposition devolve nome nulo; erro traz o corpo", async () => {
  globalThis.fetch = async () => new Response("x", { status: 200 });
  assert.equal((await modulo.baixarRelatorio({ projeto_id: "p1" })).nome, null);
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Projeto não encontrado." }), { status: 404 });
  assert.deepEqual(await modulo.baixarRelatorio({ projeto_id: "p9" }), { status: 404, blob: null, nome: null, corpo: { detail: "Projeto não encontrado." } });
  globalThis.fetch = async () => {
    throw new TypeError("rede fora");
  };
  assert.deepEqual(await modulo.baixarRelatorio({ projeto_id: "p1" }), { status: 0, blob: null, nome: null, corpo: null });
});

test("baixarRelatorio trata o 401 como as outras", async () => {
  globalThis.fetch = async () => new Response(null, { status: 401 });
  const r = await modulo.baixarRelatorio({ projeto_id: "p1" });
  assert.equal(r.status, 401);
  assert.equal(localStorage.getItem("mdca.sessao"), null);
  assert.deepEqual(destinos, ["../"]);
});

test("nomeDoArquivo lê filename com e sem aspas e filename*", () => {
  assert.equal(modulo.nomeDoArquivo('attachment; filename="a b.pdf"'), "a b.pdf");
  assert.equal(modulo.nomeDoArquivo("attachment; filename=rel.xlsx"), "rel.xlsx");
  assert.equal(modulo.nomeDoArquivo("attachment; filename*=UTF-8''presta%C3%A7%C3%A3o.pdf"), "prestação.pdf");
  assert.equal(modulo.nomeDoArquivo('attachment; filename="../../x.pdf"'), "x.pdf");
  assert.equal(modulo.nomeDoArquivo(null), null);
  assert.equal(modulo.nomeDoArquivo("attachment"), null);
});

test("status do projeto, painel da direção, extrato e auditoria", async () => {
  await modulo.alterarStatusProjeto("p/1", "encerrado");
  await modulo.resumoDosProjetos();
  await modulo.listarExtrato(true);
  await modulo.listarAuditoria({ texto: "aprov", modulo: "financeiro", desde: "2026-10-01", ate: "", limite: undefined });
  await modulo.listarAuditoria();
  assert.equal(chamadas[0].url, `${API_PADRAO}/projetos/p%2F1/status`);
  assert.equal(chamadas[0].method, "PATCH");
  assert.equal(chamadas[0].body, JSON.stringify({ status: "encerrado" }));
  assert.equal(chamadas[1].url, `${API_PADRAO}/dashboard/projetos`);
  assert.equal(chamadas[2].url, `${API_PADRAO}/extrato?em_aberto=true`);
  assert.equal(chamadas[3].url, `${API_PADRAO}/auditoria?texto=aprov&modulo=financeiro&desde=2026-10-01`);
  assert.equal(chamadas[4].url, `${API_PADRAO}/auditoria`);
});

test("importarExtrato envia o CSV no campo arquivo, em multipart", async () => {
  await modulo.importarExtrato(new File(["data;descricao;valor\n"], "extrato.csv", { type: "text/csv" }));
  assert.equal(chamadas[0].url, `${API_PADRAO}/extrato`);
  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].body.get("arquivo").name, "extrato.csv");
  assert.equal("Content-Type" in chamadas[0].headers, false);
});
