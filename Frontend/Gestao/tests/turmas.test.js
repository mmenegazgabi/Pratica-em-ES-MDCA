// Turmas e matrículas (T-53 · US-04): lista por programa, cadastro, lista de espera em
// ordem, desligamento com data e motivo obrigatórios e aviso de conflito de horário (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { horario, mostrarCadastroDeTurma, mostrarTurma, mostrarTurmas, textoDoConflito, validarTurma } = await import("../telas/turmas.js");

const TURMA = {
  id: "t-1",
  programa_id: "p-1",
  nome: "Oficina de arte",
  espaco_id: "e-1",
  espaco: "Ateliê",
  responsavel_id: "jessica",
  responsavel: "Jéssica Almeida",
  capacidade: 2,
  dias_semana: [1, 3],
  hora_inicio: "14:00:00",
  hora_fim: "16:00:00",
  ativas: 2,
  em_espera: 2,
  vagas_livres: 0,
};
const matricula = (id, pessoa, situacao, extra = {}) => ({
  id,
  pessoa_id: `pe-${pessoa.toLowerCase()}`,
  pessoa,
  situacao,
  inscrito_em: "2026-03-01T10:00:00Z",
  data_entrada: situacao === "espera" ? null : "2026-03-01",
  data_saida: null,
  motivo_saida: null,
  posicao_espera: null,
  conflitos: [],
  ...extra,
});
const DETALHE = {
  turma: TURMA,
  matriculas: [
    matricula("m-1", "Davi", "ativa"),
    matricula("m-2", "Lara", "ativa", { conflitos: [{ turma_id: "t-2", turma: "Música", dias_semana: [1], hora_inicio: "15:00:00", hora_fim: "17:00:00" }] }),
  ],
  lista_de_espera: [matricula("m-3", "Maria", "espera", { posicao_espera: 1 }), matricula("m-4", "Joana", "espera", { posicao_espera: 2 })],
  desligadas: [matricula("m-5", "Pedro", "desligada", { data_saida: "2026-04-10", motivo_saida: "Mudou de cidade" })],
};

let container;
// Espaçamento e caixas (T-00m): depois de cada teste, o que a tela montou passa pelo
// verificador de layout (nada de caixa dentro de caixa nem blocos sem espaço entre eles).
const { problemasDeLayout } = await import("./ajuda-layout.js");
afterEach(() => {
  if (container) assert.deepEqual(problemasDeLayout(container), []);
});
let registro;
let avisos;
const dialogo = () => document.getElementById("dialog");
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = async () => {
  for (let i = 0; i < 4; i += 1) await new Promise((r) => setTimeout(r, 0));
};
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button, a")].find((b) => texto(b) === rotulo);
const enviar = async (form) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
};
// Uma linha da tabela como texto, célula por célula.
const linha = (tr) => [...tr.cells].map((td) => texto(td)).join(" ").trim();
const chamadas = (nome) => registro.filter(([n]) => n === nome).map(([, ...args]) => args);

function api(extra = {}) {
  const anotar = (nome, resposta) => async (...args) => {
    registro.push([nome, ...args]);
    return typeof resposta === "function" ? resposta(...args) : resposta;
  };
  return {
    listarProgramas: anotar("listarProgramas", [
      { id: "p-1", nome: "Semear" },
      { id: "p-2", nome: "Oficina" },
    ]),
    listarTurmas: anotar("listarTurmas", (id) => (id === "p-1" ? [TURMA] : [])),
    obterTurma: anotar("obterTurma", DETALHE),
    listarEspacos: anotar("listarEspacos", [{ id: "e-1", nome: "Ateliê", capacidade: 20 }]),
    listarEquipe: anotar("listarEquipe", [
      { id: "v1", usuario_id: "jessica", nome: "Jéssica Almeida", papel: "Educador(a) social", ativo: true },
      { id: "v2", usuario_id: "rafael", nome: "Rafael Nunes", papel: "Psicólogo(a)", ativo: false },
    ]),
    listarPessoas: anotar("listarPessoas", [
      { id: "pe-lara", nome: "Lara" },
      { id: "pe-bia", nome: "Bia" },
    ]),
    cadastrarTurma: anotar("cadastrarTurma", (_p, dados) => ({ ...TURMA, ...dados, id: "t-novo" })),
    editarTurma: anotar("editarTurma", (_p, id, dados) => ({ ...TURMA, ...dados, id })),
    inscreverNaTurma: anotar("inscreverNaTurma", { matricula: matricula("m-9", "Bia", "espera", { posicao_espera: 3 }), conflitos: [] }),
    chamarListaDeEspera: anotar("chamarListaDeEspera", { matricula: matricula("m-3", "Maria", "ativa"), conflitos: [] }),
    desligarMatricula: anotar("desligarMatricula", {}),
    ...extra,
  };
}

beforeEach(() => {
  document.body.replaceChildren(document.createElement("dialog"));
  document.querySelector("dialog").id = "dialog";
  container = document.createElement("div");
  document.body.append(container);
  registro = [];
  avisos = [];
});

// --- Apoio -----------------------------------------------------------------------

test("descreve o horário e valida o cadastro", () => {
  assert.equal(horario(TURMA), "seg e qua · 14:00–16:00");
  assert.equal(horario({ ...TURMA, dias_semana: [2, 4, 6] }), "ter, qui e sáb · 14:00–16:00");
  const dados = { nome: "X", espaco_id: "e-1", responsavel_id: "jessica", capacidade: 10, dias_semana: [1], hora_inicio: "08:00", hora_fim: "09:00" };
  assert.equal(validarTurma(dados), "");
  assert.equal(validarTurma({ ...dados, dias_semana: [], nome: "" }), "Informe o nome, os dias da semana.");
  assert.equal(validarTurma({ ...dados, hora_fim: "07:00" }), "O horário de término precisa ser depois do início.");
  assert.equal(textoDoConflito("Lara", DETALHE.matriculas[1].conflitos), "Conflito de horário: Lara já está ativa(o) em Música (seg · 15:00–17:00).");
});

// --- Lista ---------------------------------------------------------------------

test("lista as turmas do programa com vagas e espera, e troca de programa", async () => {
  await mostrarTurmas(container, { podeGerenciar: true, ...api() });
  await esperar();

  assert.match(texto(container.querySelector("tbody")), /Oficina de arte.*seg e qua · 14:00–16:00.*Ateliê.*Jéssica Almeida.*2 de 2.*Turma lotada.*2 na espera/);
  assert.equal(container.querySelector("tbody a").getAttribute("href"), "#/turmas/p-1/t-1");
  assert.equal(botao("+ Criar turma").getAttribute("href"), "#/turmas/p-1/nova");

  const programa = container.querySelector('[name="programa"]');
  programa.value = "p-2";
  programa.dispatchEvent(new window.Event("change"));
  await esperar();
  assert.deepEqual(chamadas("listarTurmas").at(-1), ["p-2"]);
  assert.match(texto(), /Nenhuma turma neste programa/);
});

test("sem gerenciar, a lista não oferece criar turma", async () => {
  await mostrarTurmas(container, { programaInicial: "p-1", ...api() });
  await esperar();

  assert.equal(botao("+ Criar turma").hidden, true);
});

// --- Cadastro --------------------------------------------------------------------

test("cadastro envia local, responsável ativo, vagas, dias e horário", async () => {
  const caminhos = [];
  await mostrarCadastroDeTurma(container, "p-1", { ir: (c) => caminhos.push(c), avisar: (m) => avisos.push(m), ...api() });

  const responsaveis = [...container.querySelectorAll('[name="responsavel_id"] option')].map((o) => o.value);
  assert.deepEqual(responsaveis, ["", "jessica"]);
  container.querySelector('[name="nome"]').value = "Teatro";
  container.querySelector('[name="espaco_id"]').value = "e-1";
  container.querySelector('[name="responsavel_id"]').value = "jessica";
  container.querySelector('[name="capacidade"]').value = "15";
  container.querySelector('[name="hora_inicio"]').value = "09:00";
  container.querySelector('[name="hora_fim"]').value = "10:30";
  await enviar(container.querySelector("form"));
  assert.match(texto(container.querySelector('[role="alert"]:not([hidden])')), /Informe os dias da semana/);
  assert.equal(chamadas("cadastrarTurma").length, 0);

  container.querySelector('[name="dias_semana"][value="2"]').checked = true;
  container.querySelector('[name="dias_semana"][value="4"]').checked = true;
  await enviar(container.querySelector("form"));

  assert.deepEqual(chamadas("cadastrarTurma"), [
    ["p-1", { nome: "Teatro", espaco_id: "e-1", responsavel_id: "jessica", capacidade: 15, dias_semana: [2, 4], hora_inicio: "09:00", hora_fim: "10:30" }],
  ]);
  assert.deepEqual(caminhos, ["/turmas/p-1/t-novo"]);
});

test("recusa da API no cadastro aparece no formulário", async () => {
  const recusa = new ErroApi(ERROS.FALHA, 400, "O responsável precisa ter vínculo ativo na equipe do programa.");
  await mostrarCadastroDeTurma(container, "p-1", { ...api({ cadastrarTurma: async () => Promise.reject(recusa) }) });
  container.querySelector('[name="nome"]').value = "Teatro";
  container.querySelector('[name="espaco_id"]').value = "e-1";
  container.querySelector('[name="responsavel_id"]').value = "jessica";
  container.querySelector('[name="capacidade"]').value = "15";
  container.querySelector('[name="dias_semana"][value="1"]').checked = true;
  container.querySelector('[name="hora_inicio"]').value = "09:00";
  container.querySelector('[name="hora_fim"]').value = "10:00";

  await enviar(container.querySelector("form"));

  assert.match(texto(container.querySelector('[role="alert"]:not([hidden])')), /vínculo ativo/);
});

test("edição abre com os dados atuais da turma", async () => {
  await mostrarCadastroDeTurma(container, "p-1", { turmaId: "t-1", ...api() });

  assert.equal(container.querySelector('[name="nome"]').value, "Oficina de arte");
  assert.equal(container.querySelector('[name="hora_inicio"]').value, "14:00");
  assert.deepEqual([...container.querySelectorAll('[name="dias_semana"]:checked')].map((c) => c.value), ["1", "3"]);
});

// --- Detalhe -----------------------------------------------------------------------

test("participantes mostram o conflito de horário de cada matrícula", async () => {
  await mostrarTurma(container, "p-1", "t-1", { ...api() });

  assert.match(texto(container.querySelector(".turma-resumo")), /Oficina de arte.*seg e qua · 14:00–16:00.*Ateliê.*Jéssica Almeida.*2 de 2 vagas ocupadas.*Turma lotada.*2 na lista de espera/);
  const linhas = [...container.querySelectorAll("tbody tr")].map(linha);
  assert.deepEqual(linhas, ["Davi 01/03/2026 Sem conflito", "Lara 01/03/2026 Conflito com Música"]);
});

test("turma lotada mostra a lista de espera em ordem, e chamar o próximo fica bloqueado", async () => {
  await mostrarTurma(container, "p-1", "t-1", { aba: "espera", podeGerenciar: true, ...api() });

  const linhas = [...container.querySelectorAll("tbody tr")].map(linha);
  assert.deepEqual(linhas, ["1º Maria 01/03/2026 Tirar da fila", "2º Joana 01/03/2026 Tirar da fila"]);
  assert.equal(botao("Chamar próximo da fila").disabled, true);
  assert.equal(container.querySelector(".tab.active").textContent, "Lista de espera (2)");
});

test("com vaga, chamar o próximo passa o primeiro da fila para a turma", async () => {
  const comVaga = { ...DETALHE, turma: { ...TURMA, ativas: 1, vagas_livres: 1 } };
  await mostrarTurma(container, "p-1", "t-1", { aba: "espera", podeGerenciar: true, avisar: (m) => avisos.push(m), ...api({ obterTurma: async () => comVaga }) });

  botao("Chamar próximo da fila").click();
  await esperar();

  assert.deepEqual(chamadas("chamarListaDeEspera"), [["p-1", "t-1"]]);
  assert.deepEqual(avisos, ["Maria saiu da lista de espera e entrou na turma."]);
});

test("desligamento exige data e motivo no formulário", async () => {
  await mostrarTurma(container, "p-1", "t-1", { podeGerenciar: true, avisar: (m) => avisos.push(m), hoje: "2026-11-09", ...api() });
  botao("Desligar", container).click();
  const form = dialogo().querySelector("form");

  form.querySelector('[name="data_saida"]').value = "";
  await enviar(form);
  assert.match(texto(dialogo().querySelector('[role="alert"]')), /Informe a data e o motivo do desligamento/);
  assert.equal(chamadas("desligarMatricula").length, 0);

  form.querySelector('[name="data_saida"]').value = "2026-11-09";
  form.querySelector('[name="motivo"]').value = "Mudou de turno";
  await enviar(form);

  assert.deepEqual(chamadas("desligarMatricula"), [["p-1", "t-1", "m-1", { data_saida: "2026-11-09", motivo: "Mudou de turno" }]]);
  assert.deepEqual(avisos, ["Desligamento registrado."]);
});

test("histórico mostra data e motivo dos desligamentos", async () => {
  await mostrarTurma(container, "p-1", "t-1", { aba: "historico", ...api() });

  assert.deepEqual([...container.querySelectorAll("tbody tr")].map(linha), ["Pedro 01/03/2026 10/04/2026 Mudou de cidade"]);
});

test("inscrição em turma lotada avisa que vai para a lista de espera e informa a posição", async () => {
  await mostrarTurma(container, "p-1", "t-1", { podeGerenciar: true, avisar: (m) => avisos.push(m), ...api() });

  botao("Inscrever pessoa").click();
  await esperar();
  assert.match(texto(dialogo()), /A turma está lotada: a pessoa entra na lista de espera/);
  // Quem já está na turma ou na fila não aparece para inscrever.
  assert.deepEqual([...dialogo().querySelectorAll('[name="pessoa_id"] option')].map((o) => o.value), ["", "pe-bia"]);
  dialogo().querySelector('[name="pessoa_id"]').value = "pe-bia";
  await enviar(dialogo().querySelector("form"));

  assert.deepEqual(chamadas("inscreverNaTurma"), [["p-1", "t-1", "pe-bia"]]);
  assert.deepEqual(avisos, ["Turma lotada: Bia entrou na lista de espera (posição 3)."]);
});

test("conflito de horário na inscrição aparece para a coordenação na tela", async () => {
  const conflito = { turma_id: "t-2", turma: "Música", dias_semana: [1], hora_inicio: "15:00:00", hora_fim: "17:00:00" };
  const comVaga = { ...DETALHE, turma: { ...TURMA, ativas: 1, vagas_livres: 1 } };
  await mostrarTurma(container, "p-1", "t-1", {
    podeGerenciar: true,
    avisar: (m) => avisos.push(m),
    ...api({
      obterTurma: async () => comVaga,
      inscreverNaTurma: async () => ({ matricula: matricula("m-9", "Bia", "ativa"), conflitos: [conflito] }),
    }),
  });

  botao("Inscrever pessoa").click();
  await esperar();
  dialogo().querySelector('[name="pessoa_id"]').value = "pe-bia";
  await enviar(dialogo().querySelector("form"));
  await esperar();

  assert.deepEqual(avisos, ["Bia matriculada(o) na turma."]);
  assert.match(texto(container.querySelector('.info-box[role="alert"]')), /Conflito de horário: Bia já está ativa\(o\) em Música \(seg · 15:00–17:00\)/);
});

test("sem gerenciar, o detalhe não mostra ações", async () => {
  await mostrarTurma(container, "p-1", "t-1", { ...api() });

  assert.equal(botao("Inscrever pessoa"), undefined);
  assert.equal(botao("Desligar"), undefined);
});
