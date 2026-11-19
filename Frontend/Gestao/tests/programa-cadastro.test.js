// Cadastro, edição e detalhe de programa pela API da T-44 (T-45 · US-02), no jsdom.
import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { mostrarCadastroDePrograma, mostrarEdicaoDePrograma, mostrarPrograma, nomesParaSugestao, validarPrograma } = await import(
  "../telas/programas.js"
);

const PROGRAMA = {
  id: "p-1",
  nome: "Semear",
  identificador: "SEMEAR",
  publico: "Crianças de 6 a 11 anos",
  responsavel: "Ana Martins",
  vigencia_inicio: "2026-02-02",
  vigencia_fim: "2026-12-18",
  descricao: "Convivência e cultura.",
  status: "ativo",
};

let container;
// Espaçamento e caixas (T-00m): depois de cada teste, o que a tela montou passa pelo
// verificador de layout (nada de caixa dentro de caixa nem blocos sem espaço entre eles).
const { problemasDeLayout } = await import("./ajuda-layout.js");
afterEach(() => {
  if (container) assert.deepEqual(problemasDeLayout(container), []);
});
let registro;
let caminhos;
let avisos;
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = () => new Promise((r) => setTimeout(r, 0));
const dialogo = () => document.getElementById("dialog");
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button, a")].find((b) => texto(b) === rotulo);
const enviar = async (form) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  await esperar();
};
const preencher = (valores) => {
  for (const [nome, valor] of Object.entries(valores)) {
    const campo = container.querySelector(`[name="${nome}"]`);
    if (campo) campo.value = valor; // id e status não são campos do formulário
  }
};
const aviso = () => container.querySelector('[role="alert"]');

beforeEach(() => {
  document.body.replaceChildren(document.createElement("dialog"));
  document.querySelector("dialog").id = "dialog";
  container = document.createElement("div");
  document.body.append(container);
  registro = [];
  caminhos = [];
  avisos = [];
});

// --- Validação ------------------------------------------------------------------

test("campo obrigatório faltando bloqueia o envio com a lista do que falta", () => {
  assert.equal(validarPrograma({ ...PROGRAMA, publico: " ", responsavel: "" }), "Preencha público e responsável.");
  assert.equal(validarPrograma({ ...PROGRAMA, vigencia_fim: "2026-01-01" }), "O fim da vigência não pode ser anterior ao início.");
  assert.equal(validarPrograma(PROGRAMA), "");
});

// --- Cadastro -------------------------------------------------------------------

test("formulário incompleto não chama a API e mostra a mensagem", async () => {
  mostrarCadastroDePrograma(container, {
    cadastrar: async (dados) => registro.push(dados),
    ir: (c) => caminhos.push(c),
  });
  preencher({ nome: "Semear", identificador: "SEMEAR" });

  await enviar(container.querySelector("form"));

  assert.equal(registro.length, 0);
  assert.equal(texto(aviso()), "Preencha público, responsável, início da vigência e fim da vigência.");
});

// --- Responsável com sugestões (T-87) ----------------------------------------------

const USUARIOS = [
  { id: "jessica", nome: "Jéssica Almeida", ativo: true },
  { id: "ana", nome: "Ana Martins", ativo: true },
  { id: "antiga", nome: "Conta Antiga", ativo: false },
  { id: "ana-2", nome: "Ana Martins", ativo: true },
];

test("sugestões do Responsável: usuários ativos, em ordem e sem repetir nomes", () => {
  assert.deepEqual(nomesParaSugestao(USUARIOS), ["Ana Martins", "Jéssica Almeida"]);
  assert.deepEqual(nomesParaSugestao(undefined), []);
});

test("o campo Responsável sugere os usuários e continua aceitando outro nome", async () => {
  const enviados = [];
  mostrarCadastroDePrograma(container, {
    listarUsuarios: async () => USUARIOS,
    cadastrar: async (dados) => (enviados.push(dados), { ...PROGRAMA, ...dados }),
    ir: () => {},
  });
  await esperar();

  const campo = container.querySelector('[name="responsavel"]');
  const lista = container.querySelector(`datalist#${campo.getAttribute("list")}`);
  assert.deepEqual([...lista.options].map((o) => o.value), ["Ana Martins", "Jéssica Almeida"]);

  preencher({ ...PROGRAMA, responsavel: "Maria do Convênio" });
  await enviar(container.querySelector("form"));
  assert.equal(enviados[0].responsavel, "Maria do Convênio");
});

test("sem a lista de usuários (403), o Responsável funciona sem sugestões", async () => {
  const enviados = [];
  mostrarCadastroDePrograma(container, {
    listarUsuarios: async () => Promise.reject(new ErroApi(ERROS.SEM_PERMISSAO, 403)),
    cadastrar: async (dados) => (enviados.push(dados), { ...PROGRAMA, ...dados }),
    ir: () => {},
  });
  await esperar();

  assert.equal(container.querySelector("datalist").options.length, 0);
  assert.equal(aviso().hidden, true);
  preencher(PROGRAMA);
  await enviar(container.querySelector("form"));
  assert.equal(enviados.length, 1);
});

test("cadastro completo envia os dados e abre o programa salvo", async () => {
  mostrarCadastroDePrograma(container, {
    cadastrar: async (dados) => {
      registro.push(dados);
      return { ...PROGRAMA, ...dados };
    },
    ir: (c) => caminhos.push(c),
    avisar: (t) => avisos.push(t),
  });
  preencher({ ...PROGRAMA, descricao: "" });

  await enviar(container.querySelector("form"));

  assert.deepEqual(registro, [
    {
      nome: "Semear",
      identificador: "SEMEAR",
      publico: "Crianças de 6 a 11 anos",
      responsavel: "Ana Martins",
      vigencia_inicio: "2026-02-02",
      vigencia_fim: "2026-12-18",
      descricao: null,
    },
  ]);
  assert.deepEqual(caminhos, ["/programas/p-1"]);
  assert.deepEqual(avisos, ["Programa Semear cadastrado."]);
});

test("recusa da API (409) aparece no formulário, que continua aberto", async () => {
  mostrarCadastroDePrograma(container, {
    cadastrar: async () => {
      throw new ErroApi(ERROS.FALHA, 409, "Já existe um programa com esse identificador.");
    },
    ir: (c) => caminhos.push(c),
  });
  preencher(PROGRAMA);

  await enviar(container.querySelector("form"));

  assert.equal(texto(aviso()), "Já existe um programa com esse identificador.");
  assert.deepEqual(caminhos, []);
  assert.equal(container.querySelector('button[type="submit"]').disabled, false);
});

// --- Edição ---------------------------------------------------------------------

test("edição abre com os dados atuais e envia as alterações", async () => {
  await mostrarEdicaoDePrograma(container, "p-1", {
    obter: async () => PROGRAMA,
    editar: async (id, dados) => {
      registro.push([id, dados]);
      return { ...PROGRAMA, ...dados };
    },
    ir: (c) => caminhos.push(c),
  });
  assert.equal(container.querySelector('[name="identificador"]').value, "SEMEAR");

  preencher({ responsavel: "Patrícia Souza" });
  await enviar(container.querySelector("form"));

  assert.equal(registro[0][0], "p-1");
  assert.equal(registro[0][1].responsavel, "Patrícia Souza");
  assert.deepEqual(caminhos, ["/programas/p-1"]);
});

// --- Detalhe --------------------------------------------------------------------

function detalhe(extra = {}) {
  return {
    obterPrograma: async (...args) => {
      registro.push(["obterPrograma", ...args]);
      return PROGRAMA;
    },
    ...extra,
  };
}

test("detalhe mostra os dados do programa, sem vagas ofertadas nem convênios", async () => {
  await mostrarPrograma(container, "p-1", detalhe({ podeGerenciar: true }));

  assert.match(texto(), /SEMEAR/);
  assert.match(texto(), /02\/02\/2026 a 18\/12\/2026/);
  assert.doesNotMatch(texto(), /Convênios|Vagas ofertadas/);
  assert.equal(botao("+ Adicionar convênio", container), undefined);
  assert.equal(botao("+ Adicionar vagas", container), undefined);
  assert.deepEqual(registro.map(([nome]) => nome), ["obterPrograma"]);
});
