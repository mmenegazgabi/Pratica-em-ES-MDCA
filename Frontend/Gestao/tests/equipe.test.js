// Equipe e espaços do programa (T-40): lista pela API, vínculo, desligamento com data
// obrigatória, espaços e acesso restrito (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { mostrarEquipe } = await import("../telas/equipe.js");

const HOJE = new Date();
const AMANHA = new Date(HOJE.getTime() + 86400000).toISOString().slice(0, 10);

const EQUIPE = [
  { id: "v-ana", usuario_id: "ana", nome: "Ana Martins", papel_id: "coordenacao", papel: "Coordenação", data_entrada: "2025-01-10", data_saida: null, ativo: true },
  { id: "v-bruno", usuario_id: "bruno", nome: "Bruno Lima", papel_id: "educador", papel: "Educador(a) social", data_entrada: "2025-04-01", data_saida: AMANHA, ativo: true },
  { id: "v-rafael", usuario_id: "rafael", nome: "Rafael Nunes", papel_id: "psicologo", papel: "Psicólogo(a)", data_entrada: "2025-02-01", data_saida: "2026-01-31", ativo: false },
];
const ESPACOS = [
  { id: "s-1", nome: "Ateliê", capacidade: null },
  { id: "s-2", nome: "Sala de convivência", capacidade: 25 },
];
const USUARIOS = [
  { id: "ana", nome: "Ana Martins", ativo: true },
  { id: "inativo", nome: "Conta Antiga", ativo: false },
  { id: "patricia", nome: "Patrícia Souza", ativo: true },
];
const PAPEIS = [
  { id: "administracao", nome: "Administração do sistema" },
  { id: "assistente_social", nome: "Assistente social" },
  { id: "coordenacao", nome: "Coordenação" },
  { id: "direcao", nome: "Direção" },
  { id: "educador", nome: "Educador(a) social" },
  { id: "psicologo", nome: "Psicólogo(a)" },
  { id: "voluntario_financeiro", nome: "Voluntário(a) financeiro" },
];

let container;
let registro;
let avisos;
const dialogo = () => document.getElementById("dialog");
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = () => new Promise((r) => setTimeout(r, 0));
// Nome e id ficam em elementos separados (<strong> e <small>): um espaço entre eles.
const celula = (td) => [...td.childNodes].map((n) => n.textContent).join(" ").replace(/\s+/g, " ").trim();
const linhas = (tabela) => [...tabela.querySelectorAll("tbody tr")].map((tr) => [...tr.cells].map(celula));
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button")].find((b) => texto(b) === rotulo);
const enviar = async (form) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
  await esperar();
};

function api(extra = {}) {
  const anotar = (nome, resposta) => async (...args) => {
    registro.push([nome, ...args]);
    return typeof resposta === "function" ? resposta(...args) : resposta;
  };
  return {
    listarEquipe: anotar("listarEquipe", EQUIPE),
    listarEspacos: anotar("listarEspacos", ESPACOS),
    listarUsuarios: anotar("listarUsuarios", USUARIOS),
    listarPapeis: anotar("listarPapeis", PAPEIS),
    vincularProfissional: anotar("vincularProfissional", {}),
    registrarDesligamento: anotar("registrarDesligamento", {}),
    criarEspaco: anotar("criarEspaco", {}),
    ...extra,
  };
}

const abrir = (opcoes = {}) => mostrarEquipe(container, "p-1", { avisar: (m) => avisos.push(m), ...api(), ...opcoes });
const gerente = (extra = {}) => abrir({ podeGerenciar: true, ...extra });

beforeEach(() => {
  registro = [];
  avisos = [];
  dialogo().removeAttribute("open");
  dialogo().replaceChildren();
  container?.remove();
  container = document.createElement("div");
  document.body.append(container);
});

// --- Consulta ----------------------------------------------------------------

test("lista a equipe com histórico e os espaços vindos da API", async () => {
  await abrir();

  assert.deepEqual(registro, [
    ["listarEquipe", "p-1", { incluirDesligados: true }],
    ["listarEspacos", "p-1"],
  ]);
  const [equipe, espacos] = container.querySelectorAll("table");
  assert.deepEqual(linhas(equipe), [
    ["Ana Martins ana", "Coordenação", "10/01/2025", "—", "Ativo", "—"],
    ["Bruno Lima bruno", "Educador(a) social", "01/04/2025", AMANHA.split("-").reverse().join("/"), `Ativo até ${AMANHA.split("-").reverse().join("/")}`, "—"],
    ["Rafael Nunes rafael", "Psicólogo(a)", "01/02/2025", "31/01/2026", "Desligado", "—"],
  ]);
  assert.deepEqual(linhas(espacos), [
    ["Ateliê", "—"],
    ["Sala de convivência", "25 pessoas"],
  ]);
});

test("nomes vindos da API entram como texto, nunca como HTML", async () => {
  const perigo = '<img src=x onerror="alert(1)">';
  await abrir({ ...api({ listarEquipe: async () => [{ ...EQUIPE[0], nome: perigo }], listarEspacos: async () => [{ id: "s", nome: perigo, capacidade: 1 }] }) });

  assert.equal(container.querySelector("img"), null);
  assert.match(texto(), /<img src=x/);
});

test("sem equipe e sem espaços mostra os estados vazios", async () => {
  await abrir({ ...api({ listarEquipe: async () => [], listarEspacos: async () => [] }) });

  assert.match(texto(), /Nenhum profissional vinculado/);
  assert.match(texto(), /Nenhum espaço cadastrado/);
});

test("quem só consulta não vê os botões de gestão", async () => {
  await abrir();

  for (const rotulo of ["+ Vincular profissional", "+ Adicionar espaço", "Desligar"]) assert.equal(botao(rotulo, container), undefined);
});

test("quem gerencia pode desligar só quem está ativo e sem saída registrada", async () => {
  await gerente();

  const comBotao = [...container.querySelectorAll("tbody tr")].filter((tr) => botao("Desligar", tr)).map((tr) => tr.cells[0].querySelector("strong").textContent);
  assert.deepEqual(comBotao, ["Ana Martins"]);
  assert.ok(botao("+ Vincular profissional", container));
  assert.ok(botao("+ Adicionar espaço", container));
});

test("perfil sem permissão (403) vê a tela de acesso restrito", async () => {
  await abrir({ ...api({ listarEquipe: async () => Promise.reject(new ErroApi(ERROS.SEM_PERMISSAO, 403, "Seu perfil não tem acesso a este programa.")) }) });

  assert.match(texto(), /Acesso restrito/);
  assert.equal(container.querySelector("table"), null);
});

// --- Desligamento --------------------------------------------------------------

test("desligar exige a data de saída: sem ela a API não é chamada", async () => {
  await gerente();
  botao("Desligar", container).click();

  assert.equal(dialogo().hasAttribute("open"), true);
  assert.match(texto(dialogo()), /Encerrar vínculo · Ana Martins/);
  assert.equal(dialogo().querySelector('input[name="data_saida"]').value, "");

  await enviar(dialogo().querySelector("form"));

  assert.equal(registro.some(([nome]) => nome === "registrarDesligamento"), false);
  assert.match(texto(dialogo().querySelector('[role="alert"]')), /Informe a data de saída/);
  assert.equal(dialogo().hasAttribute("open"), true);
});

test("data de saída antes da entrada é recusada antes de chamar a API", async () => {
  await gerente();
  botao("Desligar", container).click();
  dialogo().querySelector('input[name="data_saida"]').value = "2024-12-31";

  await enviar(dialogo().querySelector("form"));

  assert.equal(registro.some(([nome]) => nome === "registrarDesligamento"), false);
  assert.match(texto(dialogo()), /não pode ser anterior à data de entrada/);
});

test("desligar com a data registra pela API, fecha o diálogo e recarrega a equipe", async () => {
  await gerente();
  botao("Desligar", container).click();
  dialogo().querySelector('input[name="data_saida"]').value = "2026-06-30";

  await enviar(dialogo().querySelector("form"));
  await esperar();

  assert.deepEqual(registro.find(([nome]) => nome === "registrarDesligamento"), ["registrarDesligamento", "p-1", "v-ana", "2026-06-30"]);
  assert.equal(dialogo().hasAttribute("open"), false);
  assert.equal(registro.filter(([nome]) => nome === "listarEquipe").length, 2);
  assert.deepEqual(avisos, ["Vínculo encerrado. O histórico foi preservado."]);
});

test("recusa da API (409) aparece no diálogo, que continua aberto", async () => {
  await gerente({
    ...api({
      registrarDesligamento: async () => Promise.reject(new ErroApi(ERROS.FALHA, 409, "O desligamento deste vínculo já foi registrado.")),
    }),
  });
  botao("Desligar", container).click();
  dialogo().querySelector('input[name="data_saida"]').value = "2026-06-30";

  await enviar(dialogo().querySelector("form"));

  assert.equal(dialogo().hasAttribute("open"), true);
  assert.match(texto(dialogo()), /O desligamento deste vínculo já foi registrado/);
  assert.equal(botao("Confirmar desligamento", dialogo()).disabled, false);
});

// --- Vínculo -------------------------------------------------------------------

test("vincular oferece só contas ativas e papéis de programa, e envia a escolha", async () => {
  await gerente();
  botao("+ Vincular profissional", container).click();
  await esperar();

  const pessoa = dialogo().querySelector('select[name="usuario_id"]');
  const papel = dialogo().querySelector('select[name="papel_id"]');
  assert.deepEqual([...pessoa.options].slice(1).map((o) => o.value), ["ana", "patricia"]);
  assert.deepEqual([...papel.options].slice(1).map((o) => o.value), ["assistente_social", "coordenacao", "educador", "psicologo"]);

  pessoa.value = "patricia";
  papel.value = "assistente_social";
  dialogo().querySelector('input[name="data_entrada"]').value = "2026-03-01";
  await enviar(dialogo().querySelector("form"));
  await esperar();

  assert.deepEqual(registro.find(([nome]) => nome === "vincularProfissional"), [
    "vincularProfissional",
    "p-1",
    { usuario_id: "patricia", papel_id: "assistente_social", data_entrada: "2026-03-01" },
  ]);
  assert.deepEqual(avisos, ["Profissional vinculado ao programa."]);
});

test("vincular sem escolher a pessoa não chama a API", async () => {
  await gerente();
  botao("+ Vincular profissional", container).click();
  await esperar();

  await enviar(dialogo().querySelector("form"));

  assert.equal(registro.some(([nome]) => nome === "vincularProfissional"), false);
  assert.match(texto(dialogo()), /Selecione a pessoa/);
});

test("sem acesso à lista de usuários, avisa e não abre o formulário", async () => {
  await gerente({
    ...api({ listarUsuarios: async () => Promise.reject(new ErroApi(ERROS.SEM_PERMISSAO, 403, "Seu perfil não tem acesso à lista de usuários.")) }),
  });
  botao("+ Vincular profissional", container).click();
  await esperar();

  assert.equal(dialogo().hasAttribute("open"), false);
  assert.deepEqual(avisos, ["Seu perfil não tem acesso à lista de usuários."]);
});

// --- Espaços -------------------------------------------------------------------

test("cadastrar espaço valida a capacidade e envia sem capacidade quando em branco", async () => {
  await gerente();
  botao("+ Adicionar espaço", container).click();
  const form = dialogo().querySelector("form");
  form.querySelector('input[name="nome"]').value = "  Quadra  ";
  form.querySelector('input[name="capacidade"]').value = "2.5";

  await enviar(form);
  assert.match(texto(dialogo()), /número inteiro maior que zero/);
  assert.equal(registro.some(([nome]) => nome === "criarEspaco"), false);

  form.querySelector('input[name="capacidade"]').value = "";
  await enviar(form);
  await esperar();

  assert.deepEqual(registro.find(([nome]) => nome === "criarEspaco"), ["criarEspaco", "p-1", { nome: "Quadra", capacidade: null }]);
  assert.deepEqual(avisos, ["Espaço cadastrado."]);
});
