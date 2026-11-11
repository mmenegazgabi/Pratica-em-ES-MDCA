// Cliente de API: sessão do login único, endereço, corpo e tradução dos erros.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import {
  API_PADRAO,
  ERROS,
  ErroApi,
  criarEspaco,
  encerrarSessao,
  listarEquipe,
  listarEspacos,
  listarPapeis,
  listarProgramas,
  listarUsuarios,
  registrarDesligamento,
  requisitar,
  salvarServidor,
  sessaoAtiva,
  urlDaApi,
  usuarioSalvo,
  vincularProfissional,
} from "../base/api.js";

let chamadas;
const daquiAUmaHora = () => new Date(Date.now() + 3600_000).toISOString();
const SESSAO = () => ({
  token: "mdca1.carga.assinatura",
  expira_em: daquiAUmaHora(),
  usuario: { id: "ana", nome: "Ana Martins", email: "ana@mdca.org.br", papeis: ["coordenacao"] },
});

let dados;
let dadosDaAba;

function responder(status, corpo) {
  globalThis.fetch = async (url, opcoes = {}) => {
    chamadas.push({ url, ...opcoes });
    const texto = corpo === undefined ? "" : typeof corpo === "string" ? corpo : JSON.stringify(corpo);
    return new Response(texto || null, { status });
  };
}

async function falhaDe(promessa) {
  try {
    await promessa;
  } catch (erro) {
    return erro;
  }
  assert.fail("a chamada deveria falhar");
}

beforeEach(() => {
  dados = new Map();
  globalThis.localStorage = {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
  dadosDaAba = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (dadosDaAba.has(k) ? dadosDaAba.get(k) : null),
    setItem: (k, v) => dadosDaAba.set(k, String(v)),
    removeItem: (k) => dadosDaAba.delete(k),
  };
  chamadas = [];
  // Login único (T-35): a página inicial da plataforma grava a sessão em "mdca.sessao".
  dados.set("mdca.sessao", JSON.stringify(SESSAO()));
  responder(200, [{ id: "p-1", nome: "Semear" }]);
});

test("manda o token da sessão para o servidor publicado, sem X-Usuario-Id", async () => {
  const corpo = await listarProgramas();

  assert.deepEqual(corpo, [{ id: "p-1", nome: "Semear" }]);
  assert.equal(chamadas[0].url, `${API_PADRAO}/gestao/programas`);
  assert.equal(chamadas[0].headers.Authorization, "Bearer mdca1.carga.assinatura");
  assert.equal(chamadas[0].headers.Accept, "application/json");
  assert.equal("X-Usuario-Id" in chamadas[0].headers, false);
  assert.equal(usuarioSalvo(), "ana");
});

test("sem sessão (nunca entrou, expirada ou malformada), nem chama a API e pede para entrar", async () => {
  for (const guardada of [null, JSON.stringify({ ...SESSAO(), expira_em: "2020-01-01T00:00:00Z" }), "{não é json"]) {
    if (guardada === null) dados.delete("mdca.sessao");
    else dados.set("mdca.sessao", guardada);
    assert.equal(sessaoAtiva(), null);

    const erro = await falhaDe(listarProgramas());

    assert.equal(erro.tipo, ERROS.SESSAO_EXPIRADA);
    assert.equal(erro.detalhe, "Entre na plataforma para continuar.");
  }
  assert.equal(chamadas.length, 0);
  assert.equal(usuarioSalvo(), "");
});

test("o servidor fica na chave da plataforma; a antiga do Financeiro ainda é lida", () => {
  dados.set("mdca.financeiro.api", "http://antigo:8000");
  assert.equal(urlDaApi(), "http://antigo:8000");

  salvarServidor("http://localhost:8000/");
  assert.equal(dados.get("mdca.api"), "http://localhost:8000");
  assert.equal(dados.has("mdca.financeiro.api"), false);
  assert.equal(urlDaApi(), "http://localhost:8000");

  salvarServidor("  ");
  assert.equal(dados.has("mdca.api"), false);
  assert.equal(urlDaApi(), API_PADRAO);
});

test("rotas de equipe, espaços, usuários e papéis", async () => {
  await listarEquipe("p 1");
  await listarEquipe("p-1", { incluirDesligados: true });
  await vincularProfissional("p-1", { usuario_id: "ana", papel_id: "coordenacao", data_entrada: "2026-03-01" });
  await registrarDesligamento("p-1", "v/1", "2026-06-30");
  await listarEspacos("p-1");
  await criarEspaco("p-1", { nome: "Ateliê", capacidade: null });
  await listarUsuarios();
  await listarPapeis();

  const feitas = chamadas.map((c) => [c.method, c.url.replace(API_PADRAO, ""), c.body ?? null]);
  assert.deepEqual(feitas, [
    ["GET", "/gestao/programas/p%201/equipe", null],
    ["GET", "/gestao/programas/p-1/equipe?incluir_desligados=true", null],
    ["POST", "/gestao/programas/p-1/equipe", '{"usuario_id":"ana","papel_id":"coordenacao","data_entrada":"2026-03-01"}'],
    ["PATCH", "/gestao/programas/p-1/equipe/v%2F1/desligamento", '{"data_saida":"2026-06-30"}'],
    ["GET", "/gestao/programas/p-1/espacos", null],
    ["POST", "/gestao/programas/p-1/espacos", '{"nome":"Ateliê","capacidade":null}'],
    ["GET", "/gestao/usuarios", null],
    ["GET", "/gestao/papeis", null],
  ]);
});

test("envia dados como JSON", async () => {
  await requisitar("/gestao/algo", { metodo: "POST", dados: { nome: "Semear" } });

  assert.equal(chamadas[0].method, "POST");
  assert.equal(chamadas[0].headers["Content-Type"], "application/json");
  assert.equal(chamadas[0].body, '{"nome":"Semear"}');
});

test("resposta sem corpo devolve null", async () => {
  responder(204);

  assert.equal(await requisitar("/gestao/algo", { metodo: "POST" }), null);
});

for (const [status, tipo] of [
  [403, ERROS.SEM_PERMISSAO],
  [404, ERROS.NAO_ENCONTRADO],
  [503, ERROS.INDISPONIVEL],
  [500, ERROS.FALHA],
  [422, ERROS.FALHA],
]) {
  test(`status ${status} vira o erro "${tipo}"`, async () => {
    responder(status, { detail: "Motivo da API" });

    const erro = await falhaDe(requisitar("/gestao/programas"));

    assert.ok(erro instanceof ErroApi);
    assert.equal(erro.tipo, tipo);
    assert.equal(erro.status, status);
    assert.equal(erro.detalhe, "Motivo da API");
    assert.ok(erro.message.length > 0);
  });
}

test("erro sem JSON não traz detalhe", async () => {
  responder(500, "Internal Server Error");

  const erro = await falhaDe(requisitar("/gestao/programas"));

  assert.equal(erro.tipo, ERROS.FALHA);
  assert.equal(erro.detalhe, "");
});

test("detail que não é texto (erros de validação) não vira detalhe", async () => {
  responder(422, { detail: [{ loc: ["body", "nome"], msg: "obrigatório" }] });

  assert.equal((await falhaDe(requisitar("/gestao/programas"))).detalhe, "");
});

test("sem conexão vira erro de rede", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };

  const erro = await falhaDe(requisitar("/gestao/programas"));

  assert.equal(erro.tipo, ERROS.REDE);
  assert.equal(erro.status, 0);
});

test("servidor que não responde no tempo limite vira erro de rede", async () => {
  globalThis.fetch = (url, { signal }) =>
    new Promise((_, rejeitar) => signal.addEventListener("abort", () => rejeitar(new DOMException("abortado", "AbortError"))));

  const erro = await falhaDe(requisitar("/gestao/programas", { tempoLimite: 10 }));

  assert.equal(erro.tipo, ERROS.REDE);
});

test("sessão guardada só nesta aba (sem 'Manter conectado') também vale", async () => {
  dadosDaAba.set("mdca.sessao", JSON.stringify(SESSAO()));

  await listarProgramas();

  assert.equal(chamadas[0].headers.Authorization, "Bearer mdca1.carga.assinatura");
});

test("401 com sessão apaga a sessão e pede para entrar de novo", async () => {
  dados.set("mdca.sessao", JSON.stringify(SESSAO()));
  responder(401, { detail: "Autenticação obrigatória." });

  const erro = await falhaDe(listarProgramas());

  assert.equal(erro.tipo, ERROS.SESSAO_EXPIRADA);
  assert.match(erro.message, /Entre de novo/);
  assert.equal(dados.has("mdca.sessao"), false);
});

test("encerrarSessao apaga a sessão dos dois armazenamentos", () => {
  dados.set("mdca.sessao", JSON.stringify(SESSAO()));
  dadosDaAba.set("mdca.sessao", JSON.stringify(SESSAO()));

  encerrarSessao();

  assert.equal(sessaoAtiva(), null);
});
