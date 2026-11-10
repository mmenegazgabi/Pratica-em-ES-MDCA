// Critérios da US-05 do lado do aparelho (T-58): a fila de verdade (base/fila.js) contra
// um servidor falso que se comporta como a API da T-56 — guarda cada registro pelo
// `registro_id` e, no reenvio, devolve o que já tinha gravado. Com ele dá para simular o
// que só acontece em campo: a rede cair no meio, e a resposta se perder depois de o
// servidor já ter gravado.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";

const { ERROS, ErroApi } = await import("../base/api.js");
const { SITUACAO, armazenamentoEmMemoria, criarFila } = await import("../base/fila.js");

/** Servidor com a regra da T-56: o mesmo registro_id não grava de novo. */
function servidorDaT56() {
  const atividades = new Map();
  const evidencias = new Map();
  const arquivosRecebidos = [];
  let conectado = true;
  let perderProximaResposta = false;

  function responder(gravar) {
    if (!conectado) return Promise.reject(new ErroApi(ERROS.REDE));
    const resultado = gravar();
    if (perderProximaResposta) {
      // Gravou, mas a resposta não chegou ao aparelho.
      perderProximaResposta = false;
      return Promise.reject(new ErroApi(ERROS.REDE));
    }
    return Promise.resolve(resultado);
  }

  return {
    atividades,
    evidencias,
    arquivosRecebidos,
    desligar: () => (conectado = false),
    ligar: () => (conectado = true),
    perderProximaResposta: () => (perderProximaResposta = true),
    api: {
      registrarAtividade: (programaId, turmaId, dados) =>
        responder(() => {
          if (!atividades.has(dados.registro_id)) {
            atividades.set(dados.registro_id, { id: `a-${atividades.size + 1}`, programaId, turmaId, ...structuredClone(dados) });
          }
          return { id: atividades.get(dados.registro_id).id };
        }),
      enviarEvidencia: (programaId, atividadeId, { registro_id, arquivo, nome }) =>
        responder(() => {
          if (!evidencias.has(registro_id)) {
            arquivosRecebidos.push(nome);
            evidencias.set(registro_id, { id: `ev-${evidencias.size + 1}`, programaId, atividadeId, nome, tamanho: arquivo.size });
          }
          return { id: evidencias.get(registro_id).id };
        }),
    },
  };
}

const ENCONTRO = {
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
const arquivo = (nome) => ({ arquivo: new Blob([`conteúdo de ${nome}`]), nome });

let servidor;
let fila;
let relogio;

beforeEach(() => {
  servidor = servidorDaT56();
  relogio = Date.parse("2026-10-05T17:00:00Z");
  let n = 0;
  fila = criarFila({ armazenamento: armazenamentoEmMemoria(), api: servidor.api, agora: () => new Date(relogio), novoId: () => `aparelho-${++n}` });
});

const situacoes = async () => (await fila.listar()).map((i) => [i.tipo, i.situacao]);

// --- Critério 1: a chamada encerrada leva todos os campos -------------------------------

test("a chamada encerrada chega ao servidor com data, turma, conteúdo e presenças", async () => {
  await fila.adicionarRegistro(ENCONTRO);

  await fila.sincronizar();

  const [gravada] = servidor.atividades.values();
  assert.deepEqual(
    { programaId: gravada.programaId, turmaId: gravada.turmaId, data: gravada.data, conteudo: gravada.conteudo, presencas: gravada.presencas },
    { programaId: "p-1", turmaId: "t-1", data: "2026-10-05", conteudo: "Pintura com guache", presencas: ENCONTRO.presencas },
  );
});

// --- Critério 2: feito sem conexão, sincronizado depois, sem duplicar ----------------

test("feito sem conexão: fica no aparelho e só vai quando a rede volta, uma vez", async () => {
  servidor.desligar();
  await fila.adicionarRegistro({ ...ENCONTRO, evidencias: [arquivo("mural.jpg")] });
  await fila.sincronizar();
  assert.deepEqual(await situacoes(), [["atividade", "erro"], ["evidencia", "pendente"]]);
  assert.equal(servidor.atividades.size, 0);

  servidor.ligar();
  relogio += 3 * 86400000; // três dias depois
  await fila.sincronizar();

  assert.deepEqual(await situacoes(), [["atividade", "enviado"], ["evidencia", "enviado"]]);
  assert.equal(servidor.atividades.size, 1);
  assert.equal(servidor.evidencias.size, 1);
  // A data do encontro é a do registro em campo, não a do envio.
  assert.equal([...servidor.atividades.values()][0].data, "2026-10-05");
});

test("resposta perdida depois de gravar: o reenvio não duplica o encontro", async () => {
  await fila.adicionarRegistro(ENCONTRO);
  servidor.perderProximaResposta();

  await fila.sincronizar(); // o servidor gravou, o aparelho não soube
  assert.deepEqual(await situacoes(), [["atividade", "erro"]]);
  await fila.sincronizar(); // reenvia o mesmo registro_id

  assert.deepEqual(await situacoes(), [["atividade", "enviado"]]);
  assert.equal(servidor.atividades.size, 1);
});

test("resposta perdida no envio da foto: o arquivo não é gravado duas vezes", async () => {
  await fila.adicionarRegistro({ ...ENCONTRO, evidencias: [arquivo("mural.jpg")] });
  const original = servidor.api.enviarEvidencia;
  let primeira = true;
  servidor.api.enviarEvidencia = (...args) => {
    if (primeira) servidor.perderProximaResposta();
    primeira = false;
    return original(...args);
  };

  await fila.sincronizar(); // o servidor guardou a foto, o aparelho não soube
  assert.deepEqual(await situacoes(), [["atividade", "enviado"], ["evidencia", "erro"]]);
  await fila.sincronizar(); // reenvia a foto com o mesmo registro_id

  assert.deepEqual(await situacoes(), [["atividade", "enviado"], ["evidencia", "enviado"]]);
  assert.equal(servidor.evidencias.size, 1);
  assert.deepEqual(servidor.arquivosRecebidos, ["mural.jpg"]);
});

test("a rede cai no meio da fila: o que foi não vai de novo, o resto vai depois", async () => {
  await fila.adicionarRegistro({ ...ENCONTRO, evidencias: [arquivo("mural.jpg")] });
  await fila.adicionarRegistro({ ...ENCONTRO, data: "2026-10-07" });
  // O primeiro encontro vai; a rede cai antes da foto.
  const original = servidor.api.registrarAtividade;
  servidor.api.registrarAtividade = async (...args) => {
    const r = await original(...args);
    servidor.desligar();
    return r;
  };
  await fila.sincronizar();
  servidor.api.registrarAtividade = original;
  assert.deepEqual(await situacoes(), [["atividade", "enviado"], ["evidencia", "erro"], ["atividade", "pendente"]]);

  servidor.ligar();
  await fila.sincronizar();

  assert.deepEqual(await situacoes(), [["atividade", "enviado"], ["evidencia", "enviado"], ["atividade", "enviado"]]);
  assert.equal(servidor.atividades.size, 2);
  assert.equal(servidor.evidencias.size, 1);
});

test("muitas sincronizações seguidas (rede oscilando) mandam cada registro uma vez", async () => {
  for (let i = 0; i < 5; i += 1) await fila.adicionarRegistro({ ...ENCONTRO, data: `2026-10-0${i + 1}`, evidencias: [arquivo(`foto-${i}.jpg`)] });

  await Promise.all([fila.sincronizar(), fila.sincronizar(), fila.sincronizar()]);
  await fila.sincronizar();

  assert.equal(servidor.atividades.size, 5);
  assert.equal(servidor.arquivosRecebidos.length, 5);
});

// --- Critério 3: evidência ligada à atividade e ao programa ------------------------------

test("cada evidência vai para o encontro certo, com o id que o servidor deu a ele", async () => {
  await fila.adicionarRegistro({ ...ENCONTRO, evidencias: [arquivo("mural.jpg")] });
  await fila.adicionarRegistro({ ...ENCONTRO, data: "2026-10-07", evidencias: [arquivo("roda.jpg"), arquivo("lista.pdf")] });

  await fila.sincronizar();

  const idDoEncontro = (data) => [...servidor.atividades.values()].find((a) => a.data === data).id;
  assert.deepEqual(
    [...servidor.evidencias.values()].map((e) => [e.nome, e.atividadeId, e.programaId]),
    [
      ["mural.jpg", idDoEncontro("2026-10-05"), "p-1"],
      ["roda.jpg", idDoEncontro("2026-10-07"), "p-1"],
      ["lista.pdf", idDoEncontro("2026-10-07"), "p-1"],
    ],
  );
});

test("evidência não vai sem o encontro: se ele for recusado, ela espera", async () => {
  await fila.adicionarRegistro({ ...ENCONTRO, evidencias: [arquivo("mural.jpg")] });
  servidor.api.registrarAtividade = () => Promise.reject(new ErroApi(ERROS.FALHA, 400, "Há pessoas na chamada sem matrícula na turma nessa data."));

  await fila.sincronizar();

  assert.deepEqual(await situacoes(), [["atividade", "erro"], ["evidencia", "pendente"]]);
  assert.equal(servidor.evidencias.size, 0);
});
