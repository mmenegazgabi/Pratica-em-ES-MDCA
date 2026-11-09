// Cliente de API: endereço, código de acesso, corpo e tradução dos erros.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import {
  API_PADRAO,
  ERROS,
  ErroApi,
  criarEspaco,
  encerrarSessao,
  esquecerAcesso,
  listarEquipe,
  listarEspacos,
  listarPapeis,
  listarProgramas,
  listarUsuarios,
  registrarDesligamento,
  requisitar,
  salvarAcesso,
  salvarServidor,
  salvarUsuario,
  sessaoAtiva,
  urlDaApi,
  usuarioSalvo,
  vincularProfissional,
} from "../base/api.js";

let chamadas;
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
  esquecerAcesso();
  salvarUsuario("");
  responder(200, [{ id: "p-1", nome: "Semear" }]);
});

test("envia o usuário salvo em X-Usuario-Id, numa chave própria de Gestão", async () => {
  salvarUsuario("  jessica ");

  await requisitar("/gestao/programas");

  assert.equal(chamadas[0].headers["X-Usuario-Id"], "jessica");
  assert.equal(dados.get("mdca.gestao.usuario"), "jessica");
  assert.equal(usuarioSalvo(), "jessica");
});

test("sem usuário salvo não envia X-Usuario-Id", async () => {
  await requisitar("/gestao/programas");

  assert.equal("X-Usuario-Id" in chamadas[0].headers, false);
});

test("400 por falta de identificação vira o erro sem_usuario; outro 400 continua falha", async () => {
  responder(400, { detail: "Identificação do usuário obrigatória." });
  assert.equal((await falhaDe(requisitar("/gestao/usuarios"))).tipo, ERROS.SEM_USUARIO);

  responder(400, { detail: "Papel inválido." });
  const erro = await falhaDe(requisitar("/gestao/programas/p-1/equipe", { metodo: "POST" }));
  assert.equal(erro.tipo, ERROS.FALHA);
  assert.equal(erro.detalhe, "Papel inválido.");
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

test("usa o servidor publicado e envia o código de acesso salvo", async () => {
  salvarAcesso("  token-de-teste  ");

  const corpo = await listarProgramas();

  assert.deepEqual(corpo, [{ id: "p-1", nome: "Semear" }]);
  assert.equal(chamadas[0].url, `${API_PADRAO}/gestao/programas`);
  assert.equal(chamadas[0].method, "GET");
  assert.equal(chamadas[0].headers.Authorization, "Bearer token-de-teste");
  assert.equal(chamadas[0].headers.Accept, "application/json");
});

test("sem código de acesso não envia Authorization", async () => {
  await requisitar("/gestao/programas");

  assert.equal("Authorization" in chamadas[0].headers, false);
});

test("o código e o servidor ficam nas mesmas chaves do Financeiro", () => {
  salvarAcesso("token-de-teste", "http://localhost:8000/");

  assert.equal(dados.get("mdca.financeiro.token"), "token-de-teste");
  assert.equal(dados.get("mdca.financeiro.api"), "http://localhost:8000");
  assert.equal(urlDaApi(), "http://localhost:8000");
});

test("voltar ao servidor publicado apaga o endereço salvo", () => {
  salvarAcesso("token-de-teste", "http://localhost:8000");
  salvarAcesso("token-de-teste", API_PADRAO);

  assert.equal(dados.has("mdca.financeiro.api"), false);
  assert.equal(urlDaApi(), API_PADRAO);
});

test("trocar só o servidor não mexe no código salvo; em branco volta ao publicado", () => {
  salvarAcesso("token-de-teste", "http://localhost:8000");
  salvarServidor("  ");

  assert.equal(dados.has("mdca.financeiro.api"), false);
  assert.equal(dados.get("mdca.financeiro.token"), "token-de-teste");
  assert.equal(urlDaApi(), API_PADRAO);
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
  [401, ERROS.NAO_AUTENTICADO],
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

// --- Login único (T-35) ------------------------------------------------------

const daquiAUmaHora = () => new Date(Date.now() + 3600_000).toISOString();
const SESSAO = () => ({
  token: "mdca1.carga.assinatura",
  expira_em: daquiAUmaHora(),
  usuario: { id: "ana", nome: "Ana Martins", email: "ana@mdca.org.br", papeis: ["coordenacao"] },
});

test("com sessão, manda o token da sessão e não manda o código nem X-Usuario-Id", async () => {
  salvarAcesso("codigo-antigo");
  salvarUsuario("jessica");
  dados.set("mdca.sessao", JSON.stringify(SESSAO()));

  await listarProgramas();

  assert.equal(chamadas[0].headers.Authorization, "Bearer mdca1.carga.assinatura");
  assert.equal("X-Usuario-Id" in chamadas[0].headers, false);
  assert.equal(usuarioSalvo(), "ana");
});

test("sessão guardada só nesta aba (sem 'Manter conectado') também vale", async () => {
  dadosDaAba.set("mdca.sessao", JSON.stringify(SESSAO()));

  await listarProgramas();

  assert.equal(chamadas[0].headers.Authorization, "Bearer mdca1.carga.assinatura");
});

test("sessão expirada ou malformada é ignorada e volta o código de acesso", async () => {
  salvarAcesso("codigo");
  dados.set("mdca.sessao", JSON.stringify({ ...SESSAO(), expira_em: "2020-01-01T00:00:00Z" }));
  assert.equal(sessaoAtiva(), null);
  dados.set("mdca.sessao", "{não é json");
  assert.equal(sessaoAtiva(), null);

  await listarProgramas();

  assert.equal(chamadas[0].headers.Authorization, "Bearer codigo");
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
