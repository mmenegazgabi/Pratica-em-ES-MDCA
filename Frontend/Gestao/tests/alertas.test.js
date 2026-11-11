// Alertas e busca ativa (T-60 · US-06): lista com pessoa, programa e faltas, linha do tempo
// do acompanhamento, registro de ação e encerramento só com justificativa (jsdom).
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { filtrarAlertas, mostrarAlerta, mostrarAlertas, textoDasFaltas, validarAcao, validarEncerramento } = await import("../telas/alertas.js");

const HOJE = "2026-11-10";
const ALERTA = {
  id: "al-1",
  tipo: "infrequencia",
  titulo: "Lara Oliveira precisa de um contato",
  descricao: "3 faltas seguidas na turma Oficina de arte.",
  programa_id: "p-1",
  pessoa_id: "pe-lara",
  pessoa: "Lara Oliveira",
  turma_id: "t-1",
  turma: "Oficina de arte",
  responsavel_id: "patricia",
  responsavel: "Patrícia Souza",
  situacao: "aberto",
  faltas_consecutivas: 3,
  limite: 3,
  primeira_falta: "2026-11-03",
  ultima_falta: "2026-11-05",
  criado_em: "2026-11-05T18:00:00Z",
  encerrado_em: null,
  encerrado_por: null,
  justificativa_encerramento: null,
  faltas: [
    { atividade_id: "a-3", data: "2026-11-03" },
    { atividade_id: "a-4", data: "2026-11-04" },
    { atividade_id: "a-5", data: "2026-11-05" },
  ],
  acoes: [
    { id: "ac-2", tipo: "busca_ativa", tipo_nome: "Busca ativa", data: "2026-11-08", resultado: "Visita: família localizada.", responsavel_id: "patricia", responsavel: "Patrícia Souza", criado_em: "2026-11-08T12:00:00Z" },
    { id: "ac-1", tipo: "contato_familia", tipo_nome: "Contato com a família", data: "2026-11-06", resultado: "Telefone sem resposta.", responsavel_id: "ana", responsavel: "Ana Martins", criado_em: "2026-11-06T12:00:00Z" },
  ],
};
const ENCERRADO = {
  ...ALERTA,
  id: "al-2",
  titulo: "Davi Oliveira precisa de um contato",
  pessoa: "Davi Oliveira",
  pessoa_id: "pe-davi",
  programa_id: "p-2",
  situacao: "encerrado",
  encerrado_em: "2026-11-09T15:00:00Z",
  encerrado_por: "patricia",
  justificativa_encerramento: "Voltou a frequentar.",
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
// Texto visível, com um espaço entre os textos de elementos diferentes.
const texto = (no = container) => {
  const partes = [];
  const andar = document.createTreeWalker(no, window.NodeFilter.SHOW_TEXT);
  while (andar.nextNode()) partes.push(andar.currentNode.nodeValue);
  return partes.join(" ").replace(/\s+/g, " ").trim();
};
const esperar = async () => {
  for (let i = 0; i < 4; i += 1) await new Promise((r) => setTimeout(r, 0));
};
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button, a")].find((b) => texto(b) === rotulo);
const enviar = async (form) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
};
const linha = (tr) => [...tr.cells].map((td) => texto(td)).join(" | ");
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
    listarAlertas: anotar("listarAlertas", [ALERTA, ENCERRADO]),
    obterAlerta: anotar("obterAlerta", ALERTA),
    registrarAcaoDeAlerta: anotar("registrarAcaoDeAlerta", ALERTA),
    encerrarAlerta: anotar("encerrarAlerta", ENCERRADO),
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

test("valida a ação e o encerramento", () => {
  assert.equal(textoDasFaltas(ALERTA), "3 faltas seguidas (limite 3)");
  const acao = { tipo: "busca_ativa", data: HOJE, resultado: "Visita." };
  assert.equal(validarAcao(acao, HOJE), "");
  assert.equal(validarAcao({ ...acao, resultado: "  ", data: "" }, HOJE), "Informe a data, o resultado da ação.");
  assert.equal(validarAcao({ ...acao, data: "2026-11-11" }, HOJE), "A data da ação não pode estar no futuro.");
  assert.equal(validarEncerramento("   "), "Escreva a justificativa do encerramento.");
  assert.equal(validarEncerramento("Voltou."), "");
});

// --- Lista ---------------------------------------------------------------------

test("o alerta aberto mostra pessoa, programa e quantidade de faltas", async () => {
  await mostrarAlertas(container, api());
  await esperar();

  const [aberto, encerrado] = container.querySelectorAll("tbody tr");
  assert.equal(
    linha(aberto),
    "Lara Oliveira precisa de um contato desde 05/11/2026 | Lara Oliveira | Semear Oficina de arte | 3 faltas seguidas (limite 3) 03/11/2026 a 05/11/2026 | Patrícia Souza | Em aberto",
  );
  assert.match(linha(encerrado), /Davi Oliveira.*Oficina.*Encerrado/);
  assert.equal(aberto.querySelector("a").getAttribute("href"), "#/alertas/al-1");
  assert.equal(aberto.querySelectorAll("a")[1].getAttribute("href"), "#/pessoas/pe-lara");
});

test("filtra por programa e situação", async () => {
  await mostrarAlertas(container, { programaInicial: "p-1", ...api() });
  await esperar();
  assert.deepEqual(chamadas("listarAlertas").at(-1), [{ programaId: "p-1", situacao: "" }]);

  const situacao = container.querySelector('[name="situacao"]');
  situacao.value = "aberto";
  situacao.dispatchEvent(new window.Event("change"));
  await esperar();
  assert.deepEqual(chamadas("listarAlertas").at(-1), [{ programaId: "p-1", situacao: "aberto" }]);
});

test("a busca filtra por pessoa ou turma, sem acento e sem diferenciar maiúsculas", async () => {
  assert.deepEqual(filtrarAlertas([ALERTA, ENCERRADO], "DAVI").map((a) => a.id), ["al-2"]);
  assert.deepEqual(filtrarAlertas([ALERTA, ENCERRADO], "oficina de arte").map((a) => a.id), ["al-1", "al-2"]);
  assert.deepEqual(filtrarAlertas([{ ...ALERTA, pessoa: "Tainá Lopes" }], "taina").length, 1);
  assert.deepEqual(filtrarAlertas([ALERTA, ENCERRADO], "  ").length, 2);

  await mostrarAlertas(container, api());
  await esperar();
  const busca = container.querySelector('[name="busca"]');
  busca.value = "lara";
  busca.dispatchEvent(new window.Event("input"));

  assert.equal(container.querySelectorAll("tbody tr").length, 1);
  assert.match(texto(container.querySelector("tbody")), /Lara Oliveira/);
  // A busca não consulta a API de novo.
  assert.equal(chamadas("listarAlertas").length, 1);

  busca.value = "ninguém";
  busca.dispatchEvent(new window.Event("input"));
  assert.match(texto(), /Nenhum alerta encontrado/);
});

test("sem alertas, explica quando eles aparecem", async () => {
  await mostrarAlertas(container, api({ listarAlertas: async () => [] }));
  await esperar();
  assert.match(texto(), /Nenhum alerta.*limite de faltas do programa/);
});

test("perfil que não acompanha alertas vê acesso restrito", async () => {
  const negar = async () => {
    throw new ErroApi(ERROS.SEM_PERMISSAO, 403, "Seu perfil não acompanha os alertas deste programa.");
  };
  await mostrarAlertas(container, api({ listarAlertas: negar }));
  await esperar();
  assert.match(texto(), /Acesso restrito/);
  assert.equal(container.querySelector("tbody"), null);
});

// --- Detalhe -------------------------------------------------------------------

test("o detalhe mostra a linha do tempo do acompanhamento, da mais recente para a mais antiga", async () => {
  await mostrarAlerta(container, "al-1", api());
  await esperar();

  assert.match(texto(), /3 faltas seguidas na turma Oficina de arte/);
  const itens = [...container.querySelectorAll(".timeline-item")].map((i) => texto(i));
  assert.deepEqual(itens, [
    "08/11/2026 · Patrícia Souza Busca ativa Visita: família localizada.",
    "06/11/2026 · Ana Martins Contato com a família Telefone sem resposta.",
  ]);
  assert.ok(botao("Registrar ação"));
  assert.ok(botao("Encerrar alerta"));
});

test("registrar ação envia tipo, data e resultado e recarrega a linha do tempo", async () => {
  await mostrarAlerta(container, "al-1", { hoje: HOJE, avisar: (t) => avisos.push(t), ...api() });
  await esperar();
  botao("Registrar ação").click();

  const form = dialogo().querySelector("form");
  assert.match(texto(dialogo()), /trajetória da pessoa/);
  form.querySelector('[name="tipo"]').value = "busca_ativa";
  form.querySelector('[name="resultado"]').value = "  Visita à família.  ";
  await enviar(form);

  assert.deepEqual(chamadas("registrarAcaoDeAlerta"), [["al-1", { tipo: "busca_ativa", data: HOJE, resultado: "Visita à família." }]]);
  assert.deepEqual(avisos, ["Ação registrada no acompanhamento."]);
  assert.equal(chamadas("obterAlerta").length, 2);
});

test("ação sem resultado não é enviada", async () => {
  await mostrarAlerta(container, "al-1", { hoje: HOJE, ...api() });
  await esperar();
  botao("Registrar ação").click();

  await enviar(dialogo().querySelector("form"));

  assert.match(texto(dialogo().querySelector('[role="alert"]')), /Informe o resultado da ação/);
  assert.deepEqual(chamadas("registrarAcaoDeAlerta"), []);
});

test("encerramento sem justificativa é bloqueado", async () => {
  await mostrarAlerta(container, "al-1", api());
  await esperar();
  botao("Encerrar alerta").click();

  const form = dialogo().querySelector("form");
  form.querySelector('[name="justificativa"]').value = "   ";
  await enviar(form);

  assert.match(texto(dialogo().querySelector('[role="alert"]')), /Escreva a justificativa do encerramento/);
  assert.deepEqual(chamadas("encerrarAlerta"), []);
});

test("encerramento com justificativa envia e mostra o alerta encerrado", async () => {
  let atual = ALERTA;
  await mostrarAlerta(container, "al-1", {
    avisar: (t) => avisos.push(t),
    ...api({ obterAlerta: async () => atual, encerrarAlerta: async (...args) => (registro.push(["encerrarAlerta", ...args]), (atual = ENCERRADO)) }),
  });
  await esperar();
  botao("Encerrar alerta").click();

  const form = dialogo().querySelector("form");
  form.querySelector('[name="justificativa"]').value = " Voltou a frequentar. ";
  await enviar(form);

  assert.deepEqual(chamadas("encerrarAlerta"), [["al-1", "Voltou a frequentar."]]);
  assert.deepEqual(avisos, ["Alerta encerrado."]);
  assert.match(texto(), /Acompanhamento encerrado.*09\/11\/2026.*Justificativa Voltou a frequentar\./);
  assert.equal(botao("Encerrar alerta"), undefined);
  assert.equal(botao("Registrar ação"), undefined);
});

test("erro da API aparece no formulário e não fecha o diálogo", async () => {
  const recusar = async () => {
    throw new ErroApi(ERROS.FALHA, 409, "O alerta já foi encerrado.");
  };
  await mostrarAlerta(container, "al-1", api({ encerrarAlerta: recusar }));
  await esperar();
  botao("Encerrar alerta").click();

  const form = dialogo().querySelector("form");
  form.querySelector('[name="justificativa"]').value = "Voltou.";
  await enviar(form);

  assert.match(texto(dialogo()), /O alerta já foi encerrado/);
});


test("o detalhe do alerta lista os encontros com falta, cada um levando à chamada (T-89)", async () => {
  await mostrarAlerta(container, "al-1", api());
  await esperar();

  const encontros = [...container.querySelectorAll(".alerta-faltas a")];
  assert.deepEqual(
    encontros.map((a) => [texto(a), a.getAttribute("href")]),
    [
      ["03/11/2026 · Oficina de arte", "#/atividades/p-1/encontro/a-3"],
      ["04/11/2026 · Oficina de arte", "#/atividades/p-1/encontro/a-4"],
      ["05/11/2026 · Oficina de arte", "#/atividades/p-1/encontro/a-5"],
    ],
  );
});
