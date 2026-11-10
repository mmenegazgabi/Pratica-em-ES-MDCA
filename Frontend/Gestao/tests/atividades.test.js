// Atividades e frequência, registro em campo e fila local (T-57 · US-05), no formato do
// protótipo da E2, com a fila do aparelho em memória e a API substituída (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { armazenamentoEmMemoria, criarFila } = await import("../base/fila.js");
const {
  inicioDaSemana,
  matriculadosNaData,
  mostrarAgenda,
  mostrarRegistro,
  mostrarSincronizacao,
  presencasParaApi,
  situacaoDoEncontro,
  validarArquivo,
  validarPasso,
} = await import("../telas/atividades.js");

const HOJE = "2026-10-07"; // quarta-feira
const PROGRAMAS = [{ id: "p-1", nome: "Semear" }, { id: "p-2", nome: "Oficina" }];
const encontro = (data, extra = {}) => ({
  data,
  turma_id: "t-1",
  turma: "Oficina de arte",
  espaco: "Ateliê",
  responsavel_id: "jessica",
  responsavel: "Jéssica Almeida",
  hora_inicio: "14:00",
  hora_fim: "16:00",
  previsto: true,
  atividades: [],
  ...extra,
});
const matricula = (pessoa, entrada, saida = null) => ({
  id: `m-${pessoa}`,
  pessoa_id: `pe-${pessoa.toLowerCase()}`,
  pessoa,
  situacao: saida ? "desligada" : "ativa",
  data_entrada: entrada,
  data_saida: saida,
});
const TURMA = {
  turma: { id: "t-1", nome: "Oficina de arte", espaco: "Ateliê", hora_inicio: "14:00:00", hora_fim: "16:00:00" },
  matriculas: [matricula("Lara", "2026-09-01"), matricula("Davi", "2026-09-01"), matricula("Nina", "2026-10-06")],
  lista_de_espera: [],
  desligadas: [matricula("Bia", "2026-09-01", "2026-10-01")],
};

let container;
let registro;
let avisos;
let idas;
let fila;
let respostasDaApi;

const esperar = () => new Promise((r) => setTimeout(r, 0));
// Texto como aparece na tela: cada pedaço de texto separado por espaço (o espaçamento
// entre elementos vizinhos vem do CSS).
function texto(no = container) {
  const pedacos = [];
  const andar = no.ownerDocument.createTreeWalker(no, 4 /* NodeFilter.SHOW_TEXT */);
  while (andar.nextNode()) pedacos.push(andar.currentNode.textContent);
  return pedacos.join(" ").replace(/\s+/g, " ").trim();
}
const botao = (rotulo, raiz = container) => [...raiz.querySelectorAll("button, a.btn")].find((b) => texto(b) === rotulo);
/** Linhas da tabela do computador (os cartões do celular trazem o mesmo conteúdo). */
const linhas = () => [...container.querySelectorAll(".so-computador tbody tr")].map((tr) => [...tr.cells].map((td) => texto(td)));
const cartoes = () => [...container.querySelectorAll(".so-celular .phone-record")];
const passoAtivo = () => texto(container.querySelector(".step.active"));

function novaFila() {
  return criarFila({
    armazenamento: armazenamentoEmMemoria(),
    api: {
      registrarAtividade: async (...args) => {
        registro.push(["registrarAtividade", ...args]);
        const r = respostasDaApi.shift();
        if (r instanceof Error) throw r;
        return { id: "srv-1" };
      },
      enviarEvidencia: async (...args) => {
        registro.push(["enviarEvidencia", ...args]);
        return { id: "srv-ev" };
      },
    },
    agora: () => new Date("2026-10-07T17:32:00"),
  });
}

const apiDaAgenda = (encontros) => ({
  listarProgramas: async () => PROGRAMAS,
  obterAgenda: async (...args) => {
    registro.push(["obterAgenda", ...args]);
    if (encontros instanceof Error) throw encontros;
    return encontros;
  },
});

beforeEach(() => {
  localStorage.clear();
  document.body.replaceChildren();
  container = document.createElement("div");
  document.body.append(container);
  registro = [];
  avisos = [];
  idas = [];
  respostasDaApi = [];
  fila = novaFila();
});

const abrirAgenda = async (encontros, opcoes = {}) => {
  await mostrarAgenda(container, { programaInicial: "p-1", podeRegistrar: true, fila, hoje: HOJE, ...apiDaAgenda(encontros), ...opcoes });
  await esperar();
  await esperar();
};

async function abrirRegistro({ online = false, data = "2026-10-07", obterTurma = async () => TURMA } = {}) {
  await mostrarRegistro(container, "p-1", "t-1", data, {
    fila,
    hoje: HOJE,
    online: () => online,
    ir: (url) => idas.push(url),
    avisar: (m) => avisos.push(m),
    obterTurma,
  });
}

async function continuar() {
  container.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  await esperar();
}

function preencherAtividade(conteudo = "Pintura com guache") {
  container.querySelector("textarea[name=conteudo]").value = conteudo;
}

function marcar(pessoa, opcao, motivo = "") {
  const escolha = container.querySelector(`select[name="att-pe-${pessoa}"]`);
  escolha.value = opcao;
  escolha.dispatchEvent(new window.Event("change"));
  if (motivo) {
    const campo = container.querySelector(`input[name="motivo-pe-${pessoa}"]`);
    campo.value = motivo;
    campo.dispatchEvent(new window.Event("input"));
  }
}

/** Percorre os quatro passos: atividade, chamada (todos presentes), sem evidências, revisão. */
async function registrarTudo({ chamada = () => botao("Marcar todos presentes").click() } = {}) {
  preencherAtividade();
  await continuar();
  chamada();
  await continuar();
  await continuar();
}

// --- Apoio -----------------------------------------------------------------------------

test("a semana começa na segunda-feira", () => {
  assert.equal(inicioDaSemana("2026-10-07"), "2026-10-05");
  assert.equal(inicioDaSemana("2026-10-05"), "2026-10-05");
  assert.equal(inicioDaSemana("2026-10-11"), "2026-10-05");
});

test("a chamada lista quem estava matriculado na data, como a API confere", () => {
  assert.deepEqual(matriculadosNaData(TURMA, "2026-10-05").map((p) => p.pessoa), ["Davi", "Lara"]);
  assert.deepEqual(matriculadosNaData(TURMA, "2026-09-28").map((p) => p.pessoa), ["Bia", "Davi", "Lara"]);
  assert.deepEqual(matriculadosNaData(TURMA, "2026-10-07").map((p) => p.pessoa), ["Davi", "Lara", "Nina"]);
});

test("as três opções de presença do protótipo viram presente/ausente/justificativa na API", () => {
  const pessoas = [{ pessoa_id: "a" }, { pessoa_id: "b" }, { pessoa_id: "c" }];
  const marcadas = new Map([
    ["a", { opcao: "Presente" }],
    ["b", { opcao: "Ausente" }],
    ["c", { opcao: "Falta justificada", motivo: " Consulta médica " }],
  ]);

  assert.deepEqual(presencasParaApi(pessoas, marcadas), [
    { pessoa_id: "a", presente: true, justificativa: null },
    { pessoa_id: "b", presente: false, justificativa: null },
    { pessoa_id: "c", presente: false, justificativa: "Consulta médica" },
  ]);
});

test("falta justificada exige o motivo", () => {
  const pessoas = [{ pessoa_id: "c", pessoa: "Caio" }];
  const problema = validarPasso(2, { presencas: new Map([["c", { opcao: "Falta justificada", motivo: " " }]]), pessoas }, HOJE);

  assert.equal(problema, "Informe o motivo da falta justificada de Caio.");
});

test("evidência: só foto ou PDF de até 5 MB", () => {
  assert.equal(validarArquivo({ name: "a.jpg", size: 10, type: "image/jpeg" }), "");
  assert.match(validarArquivo({ name: "a.jpg", size: 6 * 1024 * 1024, type: "image/jpeg" }), /maior que 5 MB/);
  assert.match(validarArquivo({ name: "a.txt", size: 10, type: "text/plain" }), /foto .* ou PDF/);
  assert.match(validarArquivo({ name: "a.jpg", size: 0, type: "image/jpeg" }), /vazio/);
});

// --- Agenda ----------------------------------------------------------------------------

test("agenda da semana em tabela, com a situação de cada encontro", async () => {
  await fila.adicionarRegistro({ programaId: "p-1", turmaId: "t-1", turma: "Oficina de arte", data: "2026-10-06", conteudo: "x", presencas: [] });

  await abrirAgenda([
    encontro("2026-10-05", { atividades: ["a-1"] }),
    encontro("2026-10-06", { previsto: false }),
    encontro("2026-10-07"),
    encontro("2026-10-09"),
  ]);

  assert.deepEqual(registro[0], ["obterAgenda", "p-1", { inicio: "2026-10-05", fim: "2026-10-11" }]);
  assert.deepEqual(
    linhas().map((l) => [l[0], l[1], l[4], l[5]]),
    [
      ["seg 05/10/2026 14:00–16:00", "Oficina de arte", "Concluída", "—"],
      ["ter 06/10/2026 14:00–16:00", "Oficina de arte Fora da agenda da turma", "Aguardando sincronização", "—"],
      ["qua 07/10/2026 14:00–16:00", "Oficina de arte", "Chamada pendente", "Fazer chamada"],
      ["sex 09/10/2026 14:00–16:00", "Oficina de arte", "Agendada", "—"],
    ],
  );
  assert.equal(botao("Fazer chamada").getAttribute("href"), "#/atividades/p-1/registro/t-1?data=2026-10-07");
});

test("no celular, os mesmos encontros em cartões do protótipo; o pendente abre a chamada", async () => {
  await abrirAgenda([encontro("2026-10-05", { atividades: ["a-1"] }), encontro("2026-10-07")]);

  assert.equal(texto(container.querySelector(".so-celular .phone-record-count")), "2 encontro(s)");
  const [feito, pendente] = cartoes();
  assert.equal(feito.tagName, "DIV");
  assert.match(texto(feito), /Oficina de arte Concluída/);
  assert.equal(pendente.tagName, "A");
  assert.equal(pendente.getAttribute("href"), "#/atividades/p-1/registro/t-1?data=2026-10-07");
  assert.match(texto(pendente), /Chamada pendente.*qua 07\/10\/2026 · 14:00–16:00 Fazer chamada →/);
});

test("quem não registra não vê como fazer a chamada", async () => {
  await abrirAgenda([encontro("2026-10-05")], { podeRegistrar: false });

  assert.deepEqual(linhas()[0].slice(4), ["Chamada pendente", "—"]);
  assert.equal(cartoes()[0].tagName, "DIV");
});

test("trocar de semana consulta o novo período", async () => {
  await abrirAgenda([]);

  botao("Próxima →").click();
  await esperar();

  assert.deepEqual(registro.at(-1), ["obterAgenda", "p-1", { inicio: "2026-10-12", fim: "2026-10-18" }]);
});

test("sem conexão, a agenda vem da última cópia salva no aparelho", async () => {
  await abrirAgenda([encontro("2026-10-07")]);
  container.replaceChildren();

  await abrirAgenda(new ErroApi(ERROS.REDE));

  assert.match(texto(), /Sem conexão: mostrando a agenda salva neste aparelho/);
  assert.equal(linhas().length, 1);
});

test("situação: erro no envio aparece na agenda", () => {
  const naFila = [{ tipo: "atividade", turmaId: "t-1", data: "2026-10-05", situacao: "erro" }];

  assert.equal(situacaoDoEncontro(encontro("2026-10-05"), naFila, HOJE).texto, "Erro no envio");
});

// --- Registro em quatro passos -----------------------------------------------------------

test("o registro segue os passos do protótipo: Atividade, Chamada, Evidências, Revisão", async () => {
  await abrirRegistro();
  assert.deepEqual([...container.querySelectorAll(".stepper .step")].map((s) => texto(s)), ["1 Atividade", "2 Chamada", "3 Evidências", "4 Revisão"]);
  assert.equal(passoAtivo(), "1 Atividade");

  preencherAtividade();
  await continuar();
  assert.equal(passoAtivo(), "2 Chamada");
  assert.match(texto(), /Quem participou\? Marcar todos presentes Turma Oficina de arte · 07\/10\/2026/);
  // Avatar com as iniciais, como no protótipo.
  assert.deepEqual([...container.querySelectorAll(".attendance .avatar")].map((a) => a.textContent), ["D", "L", "N"]);

  botao("Marcar todos presentes").click();
  await continuar();
  assert.equal(passoAtivo(), "3 Evidências");
  assert.match(texto(), /Evidências do encontro Vincule fotos e documentos à atividade\. Os anexos recebem programa, atividade, autor e data\./);

  await continuar();
  assert.equal(passoAtivo(), "4 Revisão");
  assert.match(texto(), /Está tudo certo\? Revise o encontro antes de concluir\./);
  assert.match(texto(), /Presentes 3 Ausências 0 Evidências 0 arquivo\(s\)/);
});

test("cada passo confere o que precisa antes de seguir", async () => {
  await abrirRegistro();
  await continuar();
  assert.match(texto(), /Informe o conteúdo e as ocorrências do encontro/);
  assert.equal(passoAtivo(), "1 Atividade");

  preencherAtividade();
  await continuar();
  marcar("lara", "Presente");
  marcar("davi", "Falta justificada");
  await continuar();

  assert.match(texto(), /Selecione a presença de todos: falta Nina/);
  marcar("nina", "Ausente");
  await continuar();
  assert.match(texto(), /Informe o motivo da falta justificada de Davi/);
  assert.equal(passoAtivo(), "2 Chamada");
});

test("voltar a um passo mantém o que foi preenchido", async () => {
  await abrirRegistro();
  preencherAtividade("Roda de conversa");
  await continuar();
  marcar("lara", "Presente");

  botao("Voltar").click();
  assert.equal(container.querySelector("textarea[name=conteudo]").value, "Roda de conversa");
  await continuar();

  assert.equal(container.querySelector('select[name="att-pe-lara"]').value, "Presente");
});

test("a chamada usa quem estava matriculado na data escolhida no primeiro passo", async () => {
  await abrirRegistro();
  const data = container.querySelector("input[name=data]");
  data.value = "2026-09-28";
  preencherAtividade();
  await continuar();

  assert.deepEqual([...container.querySelectorAll(".attendance label")].map((l) => l.textContent), ["Bia", "Davi", "Lara"]);
});

// --- Critério 1: sem conexão, o registro salvo fica na fila local ------------------------

test("sem conexão, Salvar no dispositivo guarda o registro na fila", async () => {
  await abrirRegistro({ online: false });
  preencherAtividade();
  await continuar();
  marcar("lara", "Presente");
  marcar("davi", "Falta justificada", "Consulta médica");
  marcar("nina", "Ausente");
  await continuar();
  await continuar();

  assert.match(texto(), /Você está sem conexão\. O registro ficará na fila local até a sincronização\./);
  assert.ok(botao("Salvar no dispositivo"));
  await continuar();

  const [item] = await fila.listar();
  assert.equal(item.situacao, "pendente");
  assert.deepEqual(item.dados.presencas, [
    { pessoa_id: "pe-davi", presente: false, justificativa: "Consulta médica" },
    { pessoa_id: "pe-lara", presente: true, justificativa: null },
    { pessoa_id: "pe-nina", presente: false, justificativa: null },
  ]);
  assert.equal(registro.length, 0, "nada foi para a API");
  assert.deepEqual(avisos, ["Atividade salva no dispositivo."]);
  assert.deepEqual(idas, ["/sincronizacao"]);
});

test("com conexão, Concluir atividade grava na fila e já envia", async () => {
  await abrirRegistro({ online: true });
  await registrarTudo();
  assert.ok(botao("Concluir atividade"));

  await continuar();

  assert.equal(registro[0][0], "registrarAtividade");
  assert.equal((await fila.listar())[0].situacao, "enviado");
  assert.deepEqual(avisos, ["Atividade e chamada registradas. Enviando…"]);
});

test("as evidências escolhidas vão para a fila junto com o encontro", async () => {
  await abrirRegistro();
  preencherAtividade();
  await continuar();
  botao("Marcar todos presentes").click();
  await continuar();
  const seletor = container.querySelector("input[type=file]");
  const arquivos = [new window.File(["x"], "foto.jpg", { type: "image/jpeg" }), new window.File(["y"], "nota.txt", { type: "text/plain" })];
  Object.defineProperty(seletor, "files", { value: arquivos, configurable: true });
  seletor.dispatchEvent(new window.Event("change"));

  assert.match(texto(), /nota\.txt: envie foto/);
  assert.equal(container.querySelectorAll(".file-item").length, 1);
  await continuar();
  assert.match(texto(), /Evidências 1 arquivo\(s\)/);
  await continuar();

  assert.deepEqual((await fila.listar()).map((i) => [i.tipo, i.nome || ""]), [["atividade", ""], ["evidencia", "foto.jpg"]]);
});

test("sem conexão, a lista da turma vem da cópia salva", async () => {
  await abrirRegistro();
  container.replaceChildren();

  await abrirRegistro({ obterTurma: async () => Promise.reject(new ErroApi(ERROS.REDE)) });
  preencherAtividade();
  await continuar();

  assert.match(texto(), /mostrando a lista da turma salva neste aparelho/);
  assert.equal(container.querySelectorAll(".attendance").length, 3);
});

// --- Fila local: critérios 2 e 3 -----------------------------------------------------------

const REGISTRO = { programaId: "p-1", turmaId: "t-1", turma: "Oficina de arte", data: "2026-10-05", conteudo: "x", presencas: [{ pessoa_id: "pe-lara", presente: true }] };

test("cada registro enviado mostra a confirmação com data e hora", async () => {
  await fila.adicionarRegistro(REGISTRO);
  await fila.sincronizar();

  await mostrarSincronizacao(container, { fila, online: () => true });

  assert.match(texto(), /Fila local 0 registro\(s\) aguardando/);
  assert.deepEqual(linhas(), [["Chamada · Oficina de arte 1 presente(s), 0 ausência(s)", "05/10/2026", "Enviado em 07/10 às 17:32", "—"]]);
  assert.match(texto(cartoes()[0]), /Enviado em 07\/10 às 17:32/);
});

test("na falha, o registro continua na fila com o erro visível e as ações", async () => {
  await fila.adicionarRegistro(REGISTRO);
  respostasDaApi = [new ErroApi(ERROS.FALHA, 400, "Há pessoas na chamada sem matrícula na turma nessa data.")];
  await fila.sincronizar();

  await mostrarSincronizacao(container, { fila, online: () => true });

  const [linha] = linhas();
  assert.equal(linha[2], "Erro no envio Há pessoas na chamada sem matrícula na turma nessa data.");
  assert.equal(linha[3], "Tentar de novo Descartar");
  // No celular, o mesmo erro e as mesmas ações no cartão.
  assert.match(texto(cartoes()[0]), /Erro no envio 1 presente\(s\), 0 ausência\(s\) Há pessoas na chamada sem matrícula na turma nessa data\. Tentar de novo Descartar/);
  assert.match(texto(), /1 registro\(s\) aguardando/);
});

test("tentar de novo envia e a confirmação aparece", async () => {
  await fila.adicionarRegistro(REGISTRO);
  respostasDaApi = [new ErroApi(ERROS.REDE)];
  await fila.sincronizar();
  await mostrarSincronizacao(container, { fila, online: () => true });
  assert.match(texto(), /Será tentado de novo quando a conexão voltar/);

  botao("Tentar de novo").click();
  await esperar();
  await esperar();
  await esperar();

  assert.match(texto(), /Enviado em/);
});

test("sem conexão, sincronizar fica desabilitado e o aviso explica", async () => {
  await fila.adicionarRegistro(REGISTRO);

  await mostrarSincronizacao(container, { fila, online: () => false });

  assert.match(texto(), /Sem conexão\. Os registros ficam guardados neste dispositivo/);
  assert.equal(botao("Sincronizar agora").disabled, true);
  assert.match(texto(), /Aguardando sincronização/);
});

test("sincronizar agora envia e avisa quantos foram", async () => {
  await fila.adicionarRegistro(REGISTRO);
  await mostrarSincronizacao(container, { fila, online: () => true, avisar: (m) => avisos.push(m) });

  botao("Sincronizar agora").click();
  await esperar();
  await esperar();
  await esperar();

  assert.deepEqual(avisos, ["1 registro(s) sincronizado(s)."]);
  assert.match(texto(), /Enviado em/);
});

test("fila vazia: tudo em dia", async () => {
  await mostrarSincronizacao(container, { fila, online: () => true });

  assert.match(texto(), /Tudo em dia Nenhum registro aguardando envio\./);
});

test("evidência espera a chamada e o nome do arquivo entra como texto", async () => {
  await fila.adicionarRegistro({ ...REGISTRO, evidencias: [{ arquivo: new Blob(["x"]), nome: '<img src=x onerror="alert(1)">' }] });

  await mostrarSincronizacao(container, { fila, online: () => false });

  assert.match(texto(), /Aguardando o envio da chamada/);
  assert.equal(container.querySelector("img"), null);
});
