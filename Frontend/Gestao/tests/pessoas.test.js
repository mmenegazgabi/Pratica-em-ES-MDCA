// Pessoas e famílias (T-49 · US-03): lista pela API, cadastro em etapas com revisão de
// duplicidade e bloqueio do menor sem responsável legal, e trajetória vinda da API (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!DOCTYPE html><body><dialog id="dialog"></dialog></body>', { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi, listarPessoas, requisitar } = await import("../base/api.js");
const { idade, mostrarCadastroDePessoa, mostrarPessoa, mostrarPessoas, precisaDeResponsavelLegal } = await import("../telas/pessoas.js");

const HOJE = "2026-11-09";
const PROGRAMAS = [
  { id: "p-1", nome: "Semear" },
  { id: "p-2", nome: "Oficina" },
];
const NUCLEOS = [{ id: "f-oliveira", nome: "Oliveira" }];
const LARA = {
  id: "pe-lara",
  nome: "Lara Oliveira",
  data_nascimento: "2013-05-12",
  idade: 13,
  programa_id: "p-1",
  programa: "Semear",
  nucleo_familiar: { id: "f-oliveira", nome: "Oliveira" },
  telefone: "51 99999-0000",
  observacao: null,
  situacao: "ativo",
  responsaveis: [{ id: "r-marina", nome: "Marina Oliveira", telefone: null, parentesco: "Mãe", responsavel_legal: true }],
  documentos: [
    { id: "d-1", tipo: "Certidão de nascimento", nome_arquivo: "certidao.pdf", tamanho: 1200, criado_em: "2026-03-02T10:00:00Z", tem_arquivo: true },
    { id: "d-0", tipo: "RG", nome_arquivo: "rg.pdf", tamanho: null, criado_em: "2026-01-02T10:00:00Z", tem_arquivo: false },
  ],
  autorizacoes: [{ id: "au-1", tipo: "uso_de_imagem", valida_de: "2026-01-01", valida_ate: "2026-12-31", documento_id: null, revogada_em: null, situacao: "vigente" }],
  autorizacao_imagem: "vigente",
};
const TRAJETORIA = [
  { data: "2026-03-02T10:00:00Z", tipo: "documento", titulo: "Documento registrado: Certidão de nascimento", descricao: "certidao.pdf" },
  { data: "2026-03-01T09:00:00Z", tipo: "cadastro", titulo: "Cadastro no programa Semear", descricao: "Núcleo familiar Oliveira." },
];
const DUPLICADO = { id: "pe-lara", nome: "Lara Oliveira", data_nascimento: "2013-05-12", programa_id: "p-1", programa: "Semear", responsaveis: ["Marina Oliveira"], motivos: ["nascimento", "responsavel"] };

let container;
let registro;
const dialogo = () => document.getElementById("dialog");
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
const esperar = async () => {
  for (let i = 0; i < 4; i += 1) await new Promise((r) => setTimeout(r, 0));
};
const botao = (rotulo, raiz = document) => [...raiz.querySelectorAll("button")].find((b) => texto(b) === rotulo);
const campo = (nome, raiz = container) => raiz.querySelector(`[name="${nome}"]`);
const preencher = (valores, raiz = container) => {
  for (const [nome, valor] of Object.entries(valores)) {
    const no = campo(nome, raiz);
    if (no.type === "checkbox") no.checked = valor;
    else no.value = valor;
    no.dispatchEvent(new window.Event("change", { bubbles: true }));
  }
};
const enviar = async (form = container.querySelector("form.pessoa-cadastro")) => {
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await esperar();
};
const escolherArquivo = (entrada, nome, tamanho, type = "application/pdf") => {
  const arquivo = { name: nome, size: tamanho, type };
  Object.defineProperty(entrada, "files", { value: [arquivo], configurable: true });
  return arquivo;
};
const erroNaTela = () => container.querySelector(".error-message:not([hidden])")?.textContent || "";

function api(extra = {}) {
  const anotar = (nome, resposta) => async (...args) => {
    registro.push([nome, ...args]);
    return typeof resposta === "function" ? resposta(...args) : resposta;
  };
  return {
    listarPessoas: anotar("listarPessoas", []),
    listarProgramas: anotar("listarProgramas", PROGRAMAS),
    buscarNucleos: anotar("buscarNucleos", NUCLEOS),
    verificarDuplicidade: anotar("verificarDuplicidade", []),
    cadastrarPessoa: anotar("cadastrarPessoa", (dados) => ({ ...LARA, id: "pe-nova", nome: dados.nome })),
    registrarDocumento: anotar("registrarDocumento", {}),
    baixarDocumento: anotar("baixarDocumento", new dom.window.Blob(["%PDF-1.4"], { type: "application/pdf" })),
    registrarAutorizacao: anotar("registrarAutorizacao", {}),
    obterPessoa: anotar("obterPessoa", LARA),
    obterTrajetoria: anotar("obterTrajetoria", TRAJETORIA),
    revogarAutorizacao: anotar("revogarAutorizacao", {}),
    incluirResponsavel: anotar("incluirResponsavel", LARA),
    ...extra,
  };
}

beforeEach(() => {
  document.body.replaceChildren(document.createElement("dialog"));
  document.querySelector("dialog").id = "dialog";
  container = document.createElement("div");
  document.body.append(container);
  registro = [];
});

const chamadas = (nome) => registro.filter(([n]) => n === nome).map(([, ...args]) => args);

// --- Cliente da API -------------------------------------------------------------

test("o cliente manda programa e busca só quando informados", async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(url);
    return new Response("[]", { status: 200 });
  };
  await listarPessoas();
  await listarPessoas({ programaId: "p 1", busca: " lara " });

  assert.match(urls[0], /\/gestao\/pessoas$/);
  assert.match(urls[1], /\/gestao\/pessoas\?programa_id=p\+1&busca=lara$/);
});

test("erro com detail em objeto guarda a mensagem e os dados (ex.: duplicidade)", async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: { codigo: "possivel_duplicidade", mensagem: "Possível duplicidade.", candidatos: [DUPLICADO] } }), { status: 409 });

  const erro = await requisitar("/gestao/pessoas", { metodo: "POST", dados: {} }).catch((e) => e);

  assert.equal(erro.status, 409);
  assert.equal(erro.detalhe, "Possível duplicidade.");
  assert.equal(erro.dados.candidatos[0].id, "pe-lara");
});

// --- Regras de apoio -------------------------------------------------------------

test("idade em anos completos e regra do responsável legal", () => {
  assert.equal(idade("2008-11-10", HOJE), 17);
  assert.equal(idade("2008-11-09", HOJE), 18);
  assert.equal(precisaDeResponsavelLegal("2013-05-12", [], HOJE), true);
  assert.equal(precisaDeResponsavelLegal("2013-05-12", [{ responsavel_legal: false }], HOJE), true);
  assert.equal(precisaDeResponsavelLegal("2013-05-12", [{ responsavel_legal: true }], HOJE), false);
  assert.equal(precisaDeResponsavelLegal("1990-01-01", [], HOJE), false);
});

// --- Lista -----------------------------------------------------------------------

test("lista as pessoas da API com programa, núcleo e situação da imagem", async () => {
  const resumo = { ...LARA, responsaveis: ["Marina Oliveira"] };
  await mostrarPessoas(container, api({ listarPessoas: async () => [resumo] }));
  await esperar();

  const linha = container.querySelector("tbody tr");
  assert.match(texto(linha), /Lara Oliveira.*Nascimento: 12\/05\/2013.*Semear.*Oliveira.*Marina Oliveira.*Autorização vigente/);
  assert.equal(linha.querySelector("a").getAttribute("href"), "#/pessoas/pe-lara");
  assert.deepEqual([...campo("programa").options].map((o) => o.textContent), ["Todos os programas", "Semear", "Oficina"]);
});

test("busca e filtro de programa consultam a API de novo", async () => {
  await mostrarPessoas(container, api());
  await esperar();
  assert.match(texto(), /Nenhuma pessoa cadastrada/);

  preencher({ busca: "lara" });
  await enviar(container.querySelector("form"));
  preencher({ programa: "p-2" });
  await esperar();

  assert.deepEqual(chamadas("listarPessoas").at(-2), [{ programaId: "", busca: "lara" }]);
  assert.deepEqual(chamadas("listarPessoas").at(-1), [{ programaId: "p-2", busca: "lara" }]);
  assert.match(texto(), /Nenhuma pessoa encontrada/);
});

// --- Cadastro --------------------------------------------------------------------

async function abrirCadastro(extra = {}, opcoes = {}) {
  const concluidos = [];
  await mostrarCadastroDePessoa(container, { hoje: HOJE, aoConcluir: (...args) => concluidos.push(args), ...opcoes, ...api(extra) });
  await esperar();
  return concluidos;
}

async function dadosPessoais(valores = {}) {
  preencher({ nome: "Pedro Souza", data_nascimento: "1990-04-02", programa_id: "p-1", ...valores });
  await enviar();
}

test("cadastro de adulto em quatro etapas grava a pessoa, os documentos e a autorização", async () => {
  const concluidos = await abrirCadastro();

  await dadosPessoais({ telefone: "51 98888-1111" });
  assert.match(texto(container.querySelector(".step.active")), /Família/);

  preencher({ nucleo_nome: "Souza" });
  await enviar();
  assert.match(texto(container.querySelector(".step.active")), /Documentos/);

  preencher({ documento_tipo: "CPF" });
  const cpf = escolherArquivo(campo("documento_arquivo"), "cpf.pdf", 2048);
  botao("Adicionar documento").click();
  preencher({ autorizacao_registrar: true, autorizacao_de: "2026-11-09", autorizacao_ate: "2027-11-08" });
  await enviar();

  assert.match(texto(), /Revisão/);
  assert.deepEqual(chamadas("verificarDuplicidade"), [[{ programa_id: "p-1", nome: "Pedro Souza", data_nascimento: "1990-04-02", responsaveis: [] }]]);
  assert.match(texto(), /Pedro Souza.*02\/04\/1990 \(36 anos\).*Semear.*Souza \(novo\).*Nenhum.*CPF.*Autorizado de 09\/11\/2026 a 08\/11\/2027/);
  assert.doesNotMatch(texto(), /Possível duplicidade/);

  await enviar();

  assert.deepEqual(chamadas("cadastrarPessoa"), [
    [
      {
        programa_id: "p-1",
        nome: "Pedro Souza",
        data_nascimento: "1990-04-02",
        responsaveis: [],
        nucleo_familiar_id: null,
        nucleo_familiar_nome: "Souza",
        telefone: "51 98888-1111",
        observacao: null,
        confirmar_duplicidade: false,
      },
    ],
  ]);
  // O arquivo escolhido vai junto, para o armazenamento (T-88).
  assert.deepEqual(chamadas("registrarDocumento"), [["pe-nova", { tipo: "CPF", arquivo: cpf }]]);
  assert.deepEqual(chamadas("registrarAutorizacao"), [["pe-nova", { tipo: "uso_de_imagem", valida_de: "2026-11-09", valida_ate: "2027-11-08" }]]);
  assert.equal(concluidos[0][0].id, "pe-nova");
  assert.deepEqual(concluidos[0][1], []);
});

test("menor sem responsável legal não passa da etapa Família", async () => {
  const concluidos = await abrirCadastro();
  await dadosPessoais({ nome: "Lara Oliveira", data_nascimento: "2013-05-12" });

  assert.match(texto(), /Menor de 18 anos: marque ao menos um responsável legal/);
  preencher({ nucleo_id: "f-oliveira", responsavel_nome: "Marina Oliveira", responsavel_legal: false });
  await enviar();

  assert.match(erroNaTela(), /menos de 18 anos precisa de ao menos um responsável legal/);
  assert.match(texto(container.querySelector(".step.active")), /Família/);

  preencher({ responsavel_legal: true });
  await enviar();
  assert.match(texto(container.querySelector(".step.active")), /Documentos/);
  assert.equal(concluidos.length, 0);
});

test("se a API recusar a conclusão por falta de responsável legal, o cadastro não é concluído", async () => {
  const recusa = new ErroApi(ERROS.FALHA, 400, "Informe ao menos um responsável legal para uma pessoa menor de idade.");
  const concluidos = await abrirCadastro({ cadastrarPessoa: async () => Promise.reject(recusa) });
  await dadosPessoais();
  preencher({ nucleo_nome: "Souza" });
  await enviar();
  await enviar();
  await enviar();

  assert.match(erroNaTela(), /Informe ao menos um responsável legal/);
  assert.equal(concluidos.length, 0);
  assert.equal(botao("Concluir cadastro").disabled, false);
});

test("possível duplicidade na revisão mostra o alerta e pede confirmação", async () => {
  const concluidos = await abrirCadastro({ verificarDuplicidade: async () => [DUPLICADO] });
  await dadosPessoais({ nome: "Lara Oliveira", data_nascimento: "2013-05-12" });
  preencher({ nucleo_id: "f-oliveira", responsavel_nome: "Marina Oliveira" });
  await enviar();
  await enviar();

  assert.match(texto(), /Possível duplicidade/);
  assert.match(texto(), /Lara Oliveira · nascimento 12\/05\/2013 · Semear · responsáveis: Marina Oliveira \(mesma data de nascimento e mesmo responsável\)/);

  await enviar();
  assert.match(erroNaTela(), /Confirme que conferiu os cadastros semelhantes/);
  assert.equal(chamadas("cadastrarPessoa").length, 0);

  preencher({ confirmar_duplicidade: true });
  await enviar();

  assert.equal(chamadas("cadastrarPessoa")[0][0].confirmar_duplicidade, true);
  assert.equal(chamadas("cadastrarPessoa")[0][0].nucleo_familiar_id, "f-oliveira");
  assert.equal(concluidos.length, 1);
});

test("semelhante cadastrado entre a revisão e a conclusão (409) volta a pedir confirmação", async () => {
  let tentativas = 0;
  const conflito = new ErroApi(ERROS.FALHA, 409, "Possível duplicidade: confira os cadastros semelhantes antes de concluir.", {
    codigo: "possivel_duplicidade",
    candidatos: [DUPLICADO],
  });
  const concluidos = await abrirCadastro({
    cadastrarPessoa: async (dados) => {
      tentativas += 1;
      if (tentativas === 1) throw conflito;
      return { ...LARA, id: "pe-nova", confirmou: dados.confirmar_duplicidade };
    },
  });
  await dadosPessoais();
  preencher({ nucleo_nome: "Souza" });
  await enviar();
  await enviar();
  await enviar();

  assert.match(erroNaTela(), /Possível duplicidade: confira/);
  assert.match(texto(), /Conferi os cadastros semelhantes/);
  assert.equal(concluidos.length, 0);

  preencher({ confirmar_duplicidade: true });
  await enviar();
  assert.equal(concluidos[0][0].confirmou, true);
});

test("o que falhar depois de criar a pessoa vai como pendência", async () => {
  const concluidos = await abrirCadastro({ registrarAutorizacao: async () => Promise.reject(new ErroApi(ERROS.FALHA, 400, "Data inválida.")) });
  await dadosPessoais();
  preencher({ nucleo_nome: "Souza" });
  await enviar();
  preencher({ autorizacao_registrar: true, autorizacao_ate: "2027-01-01" });
  await enviar();
  await enviar();

  assert.deepEqual(concluidos[0][1], ["autorização de imagem (Data inválida.)"]);
});

// --- Perfil e trajetória ---------------------------------------------------------

test("a trajetória mostra a linha do tempo vinda da API", async () => {
  await mostrarPessoa(container, "pe-lara", { hoje: HOJE, ...api() });

  assert.deepEqual(chamadas("obterTrajetoria"), [["pe-lara"]]);
  assert.match(texto(container.querySelector(".pessoa-cabecalho")), /Lara Oliveira.*13 anos.*Semear.*núcleo Oliveira.*Ativa.*Autorização vigente/);
  const itens = [...container.querySelectorAll(".timeline-item")].map((i) => texto(i));
  assert.deepEqual(itens, ["02/03/2026Documento registrado: Certidão de nascimentocertidao.pdf", "01/03/2026Cadastro no programa SemearNúcleo familiar Oliveira."]);
  assert.equal(container.querySelector(".tab.active").textContent, "Trajetória");
});

test("trajetória vazia mostra o estado vazio", async () => {
  await mostrarPessoa(container, "pe-lara", { ...api({ obterTrajetoria: async () => [] }) });

  assert.match(texto(), /A trajetória começa aqui/);
});

test("aba Família mostra núcleo e responsáveis; incluir só para quem cadastra", async () => {
  await mostrarPessoa(container, "pe-lara", { aba: "familia", ...api() });
  assert.match(texto(), /Núcleo familiar Oliveira.*51 99999-0000.*Marina Oliveira.*Mãe.*Responsável legal/);
  assert.equal(botao("Incluir responsável"), undefined);

  await mostrarPessoa(container, "pe-lara", { aba: "familia", podeCadastrar: true, ...api() });
  botao("Incluir responsável").click();
  preencher({ nome: "José Oliveira", parentesco: "Avô" }, dialogo());
  await enviar(dialogo().querySelector("form"));

  assert.deepEqual(chamadas("incluirResponsavel"), [["pe-lara", { nome: "José Oliveira", parentesco: "Avô", telefone: null, responsavel_legal: false }]]);
});

test("aba Documentos mostra autorizações e documentos, e revoga a vigente", async () => {
  const avisos = [];
  await mostrarPessoa(container, "pe-lara", { aba: "documentos", podeCadastrar: true, avisar: (m) => avisos.push(m), ...api() });

  assert.match(texto(), /Uso externo de imagem permitido.*01\/01\/2026 a 31\/12\/2026.*Autorização vigente/);
  assert.match(texto(), /Certidão de nascimento · certidao\.pdf.*Registrado em 02\/03\/2026/);

  botao("Revogar").click();
  await enviar(dialogo().querySelector("form"));

  assert.deepEqual(chamadas("revogarAutorizacao"), [["pe-lara", "au-1"]]);
  assert.deepEqual(avisos, ["Autorização revogada."]);
});

test("documento com arquivo tem Baixar, que busca o arquivo pela API; o antigo, sem arquivo, não", async () => {
  const criados = [];
  globalThis.URL.createObjectURL = (blob) => (criados.push(blob), "blob:teste");
  globalThis.URL.revokeObjectURL = () => {};
  await mostrarPessoa(container, "pe-lara", { aba: "documentos", podeCadastrar: true, ...api() });

  assert.match(texto(), /RG · rg\.pdf.*Sem arquivo \(registro antigo\)/);
  assert.equal([...container.querySelectorAll("button")].filter((b) => texto(b) === "Baixar").length, 1);

  botao("Baixar").click();
  await esperar();

  assert.deepEqual(chamadas("baixarDocumento"), [["pe-lara", "d-1"]]);
  assert.equal(criados.length, 1);
});

test("registrar documento envia o arquivo e recusa tipo ou tamanho fora do permitido", async () => {
  await mostrarPessoa(container, "pe-lara", { aba: "documentos", podeCadastrar: true, ...api() });
  botao("Registrar documento").click();
  const form = dialogo().querySelector("form");
  form.querySelector('[name="tipo"]').value = "CPF";

  escolherArquivo(form.querySelector('[name="arquivo"]'), "programa.exe", 100, "application/x-msdownload");
  await enviar(form);
  assert.match(texto(dialogo()), /programa\.exe: envie foto \(JPG, PNG, WEBP, HEIC\) ou PDF\./);

  escolherArquivo(form.querySelector('[name="arquivo"]'), "grande.pdf", 6 * 1024 * 1024);
  await enviar(form);
  assert.match(texto(dialogo()), /grande\.pdf: maior que 5 MB\./);
  assert.deepEqual(chamadas("registrarDocumento"), []);

  const cpf = escolherArquivo(form.querySelector('[name="arquivo"]'), "cpf.pdf", 2048);
  await enviar(form);
  assert.deepEqual(chamadas("registrarDocumento"), [["pe-lara", { tipo: "CPF", arquivo: cpf }]]);
});

test("sem autorização vigente, o uso externo aparece bloqueado", async () => {
  const vencida = { ...LARA, autorizacao_imagem: "vencida", autorizacoes: [{ ...LARA.autorizacoes[0], valida_ate: "2026-01-31", situacao: "vencida" }] };
  await mostrarPessoa(container, "pe-lara", { aba: "documentos", podeCadastrar: true, ...api({ obterPessoa: async () => vencida }) });

  assert.match(texto(), /Uso externo de imagem bloqueado/);
  assert.equal(botao("Revogar"), undefined);
});


test("na trajetória, a falta leva ao encontro com a chamada (T-89)", async () => {
  const { linhaDoTempo } = await import("../telas/pessoas.js");
  const linha = linhaDoTempo([
    { data: "2026-10-05T03:00:00Z", tipo: "frequencia", titulo: "Falta na turma Oficina de arte", descricao: "Ausente no encontro.", programa_id: "p-1", atividade_id: "a-1" },
    { data: "2026-03-01T10:00:00Z", tipo: "cadastro", titulo: "Cadastro no programa Semear", descricao: "Núcleo familiar Oliveira.", programa_id: null, atividade_id: null },
  ]);

  const [falta, cadastro] = linha.querySelectorAll(".timeline-item");
  assert.equal(falta.querySelector("h3 a").getAttribute("href"), "#/atividades/p-1/encontro/a-1");
  assert.equal(cadastro.querySelector("h3 a"), null);
});
