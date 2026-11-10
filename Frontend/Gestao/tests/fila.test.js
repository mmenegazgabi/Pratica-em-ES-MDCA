// Fila do aparelho do registro em campo (T-57 · US-05): guarda sem conexão, envia em
// ordem quando a rede volta, confirma cada envio e mantém na fila o que falhou, com o erro.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";

const { ERROS, ErroApi } = await import("../base/api.js");
const { SITUACAO, armazenamentoEmMemoria, armazenamentoIndexedDB, criarFila } = await import("../base/fila.js");

const REGISTRO = {
  programaId: "p-1",
  turmaId: "t-1",
  turma: "Oficina de arte",
  data: "2026-10-05",
  conteudo: "Pintura com guache",
  presencas: [
    { pessoa_id: "pe-lara", presente: true, justificativa: null },
    { pessoa_id: "pe-davi", presente: false, justificativa: "Consulta médica" },
  ],
};
const foto = (nome = "foto.jpg") => ({ arquivo: new Blob(["\xff\xd8\xff conteúdo"], { type: "image/jpeg" }), nome });

let chamadas;
let respostas;
let relogio;
let contador;

/** API falsa: cada chamada anota os argumentos e usa a próxima resposta da lista (ou sucesso). */
function apiFalsa() {
  const responder = (nome, args) => {
    chamadas.push([nome, ...args]);
    const proxima = respostas.shift();
    if (proxima instanceof Error) return Promise.reject(proxima);
    if (nome === "registrarAtividade") return Promise.resolve(proxima || { id: `srv-a-${chamadas.length}` });
    return Promise.resolve(proxima || { id: `srv-e-${chamadas.length}` });
  };
  return {
    registrarAtividade: (...args) => responder("registrarAtividade", args),
    enviarEvidencia: (...args) => responder("enviarEvidencia", args),
  };
}

function novaFila(armazenamento = armazenamentoEmMemoria()) {
  return criarFila({
    armazenamento,
    api: apiFalsa(),
    agora: () => new Date(relogio),
    novoId: () => `reg-${++contador}`,
  });
}

beforeEach(() => {
  chamadas = [];
  respostas = [];
  relogio = Date.parse("2026-10-05T17:30:00Z");
  contador = 0;
});

// --- 1. Sem conexão, o registro salvo fica na fila local -----------------------------

test("salvar guarda o encontro e as evidências na fila, sem chamar a API", async () => {
  const fila = novaFila();

  const atividade = await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto(), foto("lista.pdf")] });

  assert.deepEqual(chamadas, []);
  const itens = await fila.listar();
  assert.deepEqual(
    itens.map((i) => [i.tipo, i.situacao, i.id]),
    [
      ["atividade", "pendente", "reg-1"],
      ["evidencia", "pendente", "reg-2"],
      ["evidencia", "pendente", "reg-3"],
    ],
  );
  // O registro_id é gerado no aparelho e é o mesmo em todo reenvio.
  assert.equal(atividade.dados.registro_id, "reg-1");
  assert.equal(itens[1].atividadeRegistroId, "reg-1");
});

test("a fila sobrevive a fechar o app: fica no IndexedDB, com as fotos", async () => {
  const banco = `teste-${Math.random()}`;
  await novaFila(armazenamentoIndexedDB(indexedDB, banco)).adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });

  // "Reabre o app": outra fila sobre o mesmo banco.
  const itens = await novaFila(armazenamentoIndexedDB(indexedDB, banco)).listar();

  assert.deepEqual(itens.map((i) => [i.tipo, i.situacao]), [["atividade", "pendente"], ["evidencia", "pendente"]]);
  assert.equal(await itens[1].arquivo.text(), await foto().arquivo.text());
});

// --- 2. Com a rede de volta, cada registro mostra a confirmação de envio --------------

test("sincronizar envia em ordem e confirma cada registro com data e hora", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });
  relogio = Date.parse("2026-10-05T18:00:00Z");

  const resultado = await fila.sincronizar();

  assert.deepEqual(resultado, { enviados: 2, falhas: 0, aguardando: 0 });
  assert.deepEqual(chamadas[0], ["registrarAtividade", "p-1", "t-1", { registro_id: "reg-1", data: "2026-10-05", conteudo: "Pintura com guache", observacao: null, presencas: REGISTRO.presencas }]);
  // A evidência vai para o id que a API devolveu ao encontro.
  assert.equal(chamadas[1][0], "enviarEvidencia");
  assert.deepEqual([chamadas[1][1], chamadas[1][2], chamadas[1][3].registro_id], ["p-1", "srv-a-1", "reg-2"]);
  const itens = await fila.listar();
  assert.deepEqual(itens.map((i) => [i.situacao, i.enviadoEm, i.resultadoId]), [
    ["enviado", "2026-10-05T18:00:00.000Z", "srv-a-1"],
    ["enviado", "2026-10-05T18:00:00.000Z", "srv-e-2"],
  ]);
  assert.equal(itens[1].arquivo, null, "a foto enviada não ocupa mais o aparelho");
});

test("quem ouve a fila é avisado a cada mudança", async () => {
  const fila = novaFila();
  const vistos = [];
  fila.aoMudar((itens) => vistos.push(itens.map((i) => i.situacao).join(",")));

  await fila.adicionarRegistro(REGISTRO);
  await fila.sincronizar();

  assert.deepEqual(vistos, ["pendente", "enviado"]);
});

test("duas sincronizações ao mesmo tempo fazem um envio só", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);

  await Promise.all([fila.sincronizar(), fila.sincronizar()]);

  assert.equal(chamadas.length, 1);
});

test("resposta perdida: o reenvio usa o mesmo registro_id (a API não duplica)", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  respostas = [new ErroApi(ERROS.REDE)];

  await fila.sincronizar();
  await fila.sincronizar();

  assert.deepEqual(chamadas.map((c) => c[3].registro_id), ["reg-1", "reg-1"]);
  assert.equal((await fila.listar())[0].situacao, SITUACAO.ENVIADO);
});

// --- 3. Na falha, o registro continua na fila com o erro visível -----------------------

test("falha de conexão: o registro fica na fila com o erro e os outros esperam", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  await fila.adicionarRegistro({ ...REGISTRO, data: "2026-10-07" });
  respostas = [new ErroApi(ERROS.REDE)];

  const resultado = await fila.sincronizar();

  assert.deepEqual(resultado, { enviados: 0, falhas: 1, aguardando: 2 });
  assert.equal(chamadas.length, 1, "sem conexão, não adianta tentar os demais");
  const [primeiro, segundo] = await fila.listar();
  assert.equal(primeiro.situacao, SITUACAO.ERRO);
  assert.equal(primeiro.erro, "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.");
  assert.equal(primeiro.repetir, true);
  assert.equal(segundo.situacao, SITUACAO.PENDENTE);
});

test("falha passageira é tentada de novo na próxima sincronização", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  respostas = [new ErroApi(ERROS.INDISPONIVEL, 503)];
  await fila.sincronizar();

  await fila.sincronizar();

  assert.equal((await fila.listar())[0].situacao, SITUACAO.ENVIADO);
});

test("recusa da API: fica com a mensagem dela e não é reenviada sozinha", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  await fila.adicionarRegistro({ ...REGISTRO, data: "2026-10-07" });
  respostas = [new ErroApi(ERROS.FALHA, 400, "Há pessoas na chamada sem matrícula na turma nessa data.")];

  await fila.sincronizar();
  await fila.sincronizar();

  const [recusado, outro] = await fila.listar();
  assert.deepEqual([recusado.situacao, recusado.erro, recusado.repetir], [
    "erro",
    "Há pessoas na chamada sem matrícula na turma nessa data.",
    false,
  ]);
  // Uma recusa não trava o resto da fila.
  assert.equal(outro.situacao, SITUACAO.ENVIADO);
  assert.equal(chamadas.filter((c) => c[3].registro_id === recusado.id).length, 1);
});

test("evidência espera o envio do encontro que falhou", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });
  respostas = [new ErroApi(ERROS.FALHA, 400, "Recusado.")];

  await fila.sincronizar();

  assert.deepEqual(chamadas.map((c) => c[0]), ["registrarAtividade"]);
  assert.deepEqual((await fila.listar()).map((i) => i.situacao), ["erro", "pendente"]);
});

test("tentar de novo volta o item para a fila e envia", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });
  respostas = [new ErroApi(ERROS.FALHA, 400, "Recusado.")];
  await fila.sincronizar();

  const resultado = await fila.tentarDeNovo("reg-1");

  assert.equal(resultado.enviados, 2);
  assert.deepEqual((await fila.listar()).map((i) => i.situacao), ["enviado", "enviado"]);
});

test("descartar o encontro leva junto as evidências não enviadas", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });
  await fila.adicionarRegistro({ ...REGISTRO, data: "2026-10-07" });

  await fila.descartar("reg-1");

  assert.deepEqual((await fila.listar()).map((i) => i.id), ["reg-3"]);
});

test("um registro já enviado não pode ser descartado", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  await fila.sincronizar();

  await fila.descartar("reg-1");

  assert.equal((await fila.listar()).length, 1);
});

// --- Histórico -------------------------------------------------------------------------

test("limpar enviados mantém o encontro cuja evidência ainda não foi", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [foto()] });
  await fila.adicionarRegistro({ ...REGISTRO, data: "2026-10-07" });
  respostas = [undefined, new ErroApi(ERROS.FALHA, 400, "Arquivo recusado.")];
  await fila.sincronizar();

  const removidos = await fila.limparEnviados();

  assert.equal(removidos, 1);
  assert.deepEqual((await fila.listar()).map((i) => [i.id, i.situacao]), [["reg-1", "enviado"], ["reg-2", "erro"]]);
});

test("ao abrir, os enviados há mais de uma semana saem da lista", async () => {
  const fila = novaFila();
  await fila.adicionarRegistro(REGISTRO);
  await fila.sincronizar();
  await fila.adicionarRegistro({ ...REGISTRO, data: "2026-10-07" });

  relogio += 8 * 86400000;
  await fila.podarHistorico();

  assert.deepEqual((await fila.listar()).map((i) => i.id), ["reg-2"]);
});
