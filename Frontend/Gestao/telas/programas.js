// Programas do cadastro canônico (ARQ-02), ligados à API da T-44 (T-45 · US-02):
// lista, cadastro, edição e detalhe com convênios e vagas.
//
// O programa é o mesmo registro que o Financeiro usa em orçamentos e lançamentos; o
// identificador é o código compartilhado entre os dois módulos. Os botões de cadastro e
// edição só aparecem para quem gerencia, mas quem decide é a API: uma recusa (400, 403,
// 409…) aparece no próprio formulário. Programa novo: coordenação e administração
// (T-87).
//
// O Responsável é texto livre, mas sugere os nomes dos usuários ativos enquanto se digita
// (T-87): quem não tem conta continua podendo ser escrito, e se a lista não carregar (403
// para quem não pode ver os usuários, ou falha de rede) o campo funciona sem sugestões.

import * as api from "../base/api.js";
import { ErroApi } from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el, secao } from "../base/dom.js";
import { abrirFormulario, campo } from "../base/formulario.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  obterPrograma: api.obterPrograma,
  cadastrarPrograma: api.cadastrarPrograma,
  editarPrograma: api.editarPrograma,
  listarConvenios: api.listarConvenios,
  cadastrarConvenio: api.cadastrarConvenio,
  listarVagas: api.listarVagas,
  cadastrarVagas: api.cadastrarVagas,
  listarUsuarios: api.listarUsuarios,
};

export const dataBr = (iso) => (iso ? String(iso).split("-").reverse().join("/") : "—");
export const vigencia = (inicio, fim) => (inicio || fim ? `${dataBr(inicio)} a ${dataBr(fim)}` : "—");
const linkPrograma = (id, sufixo = "") => `#/programas/${encodeURIComponent(id)}${sufixo}`;

function tabela(cabecalhos, linhas) {
  return el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      {},
      el("thead", {}, el("tr", {}, cabecalhos.map((c) => el("th", { scope: "col" }, c)))),
      el("tbody", {}, linhas),
    ),
  );
}

function cartao(titulo, subtitulo, corpo, acao = null) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), acao),
    el("div", { class: "card-body" }, corpo),
  );
}

const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const botao = (texto, onclick) => el("button", { type: "button", class: "btn", onclick }, texto);

// --- Lista ----------------------------------------------------------------------

export function listaDeProgramas(programas, { podeCadastrar = false } = {}) {
  const novo = podeCadastrar ? el("a", { class: "btn primary", href: "#/programas/novo" }, "+ Novo programa") : null;
  if (!programas?.length) {
    return cartao(
      "Programas",
      null,
      vazio("Nenhum programa cadastrado", "Os programas cadastrados na plataforma aparecem aqui."),
      novo,
    );
  }
  const linhas = programas.map((p) =>
    el(
      "tr",
      {},
      el("td", {}, el("a", { class: "activity-title", href: linkPrograma(p.id) }, p.nome)),
      el("td", {}, p.identificador ? el("code", {}, p.identificador) : "—"),
      el("td", {}, vigencia(p.vigencia_inicio, p.vigencia_fim)),
      el("td", {}, el("a", { class: "text-link", href: linkPrograma(p.id, "/equipe") }, "Equipe e espaços")),
    ),
  );
  return cartao(
    "Programas",
    "Cadastro canônico compartilhado com o Financeiro",
    tabela(["Programa", "Identificador", "Vigência", "Equipe"], linhas),
    novo,
  );
}

export function mostrarProgramas(container, { podeCadastrar = false, buscar = API_PADRAO.listarProgramas } = {}) {
  return carregarNaTela(container, buscar, (programas) => listaDeProgramas(programas, { podeCadastrar }));
}

// --- Cadastro e edição ----------------------------------------------------------

const OBRIGATORIOS = [
  ["nome", "nome"],
  ["identificador", "identificador"],
  ["publico", "público"],
  ["responsavel", "responsável"],
  ["vigencia_inicio", "início da vigência"],
  ["vigencia_fim", "fim da vigência"],
];

const juntar = (itens) => (itens.length === 1 ? itens[0] : `${itens.slice(0, -1).join(", ")} e ${itens.at(-1)}`);

/** Mensagem que bloqueia o envio, ou "" quando os dados podem ir para a API. */
export function validarPrograma(dados) {
  const faltam = OBRIGATORIOS.filter(([chave]) => !String(dados[chave] ?? "").trim()).map(([, rotulo]) => rotulo);
  if (faltam.length) return `Preencha ${juntar(faltam)}.`;
  if (dados.vigencia_fim < dados.vigencia_inicio) return "O fim da vigência não pode ser anterior ao início.";
  return "";
}

function entrada(tipo, nome, valor, extra = {}) {
  const no = el(tipo === "textarea" ? "textarea" : "input", { name: nome, ...(tipo === "textarea" ? {} : { type: tipo }), ...extra });
  no.value = valor ?? "";
  return no;
}

/** Formulário de página para cadastrar (sem `programa`) ou editar um programa. */
/** Sugestões do Responsável: nomes dos usuários ativos, em ordem, sem repetição. */
export function nomesParaSugestao(usuarios) {
  const nomes = (usuarios || []).filter((u) => u.ativo !== false && u.nome).map((u) => u.nome.trim());
  return [...new Set(nomes)].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

function sugerirResponsaveis(lista, listarUsuarios) {
  // Sem esperar: o formulário já aparece e as sugestões chegam quando a API responder.
  Promise.resolve()
    .then(() => listarUsuarios())
    .then((usuarios) => lista.replaceChildren(...nomesParaSugestao(usuarios).map((nome) => el("option", { value: nome }))))
    .catch(() => {});
}

export function formularioDePrograma({
  programa = null,
  salvar,
  aoSalvar,
  cancelarPara = "#/programas",
  listarUsuarios = API_PADRAO.listarUsuarios,
}) {
  const p = programa || {};
  const sugestoes = el("datalist", { id: "f-programa-responsaveis" });
  const campos = {
    nome: entrada("text", "nome", p.nome, { maxlength: 200, autocomplete: "off" }),
    identificador: entrada("text", "identificador", p.identificador, { maxlength: 50, autocomplete: "off", autocapitalize: "characters" }),
    publico: entrada("text", "publico", p.publico, { maxlength: 500 }),
    responsavel: entrada("text", "responsavel", p.responsavel, { maxlength: 200, list: "f-programa-responsaveis", autocomplete: "off" }),
    vigencia_inicio: entrada("date", "vigencia_inicio", p.vigencia_inicio),
    vigencia_fim: entrada("date", "vigencia_fim", p.vigencia_fim),
    descricao: entrada("textarea", "descricao", p.descricao, { maxlength: 2000, rows: 3 }),
  };
  const aviso = el("div", { class: "error-message", role: "alert", hidden: true });
  const enviarBotao = el("button", { type: "submit", class: "btn primary" }, programa ? "Salvar alterações" : "Salvar programa");

  function mostrarAviso(texto) {
    aviso.textContent = texto;
    aviso.hidden = false;
    aviso.scrollIntoView?.({ block: "nearest" });
  }

  async function enviar(evento) {
    evento.preventDefault();
    // O app tem um tratador global de submit para os formulários do protótipo.
    evento.stopPropagation();
    const dados = Object.fromEntries(Object.entries(campos).map(([chave, no]) => [chave, no.value.trim()]));
    const problema = validarPrograma(dados);
    if (problema) return mostrarAviso(problema);
    if (!dados.descricao) dados.descricao = null;
    aviso.hidden = true;
    enviarBotao.disabled = true;
    try {
      aoSalvar(await salvar(dados));
    } catch (erro) {
      enviarBotao.disabled = false;
      mostrarAviso(erro instanceof ErroApi ? erro.detalhe || erro.message : "Não foi possível salvar. Tente de novo.");
    }
  }

  const formulario = el(
    "section",
    { class: "card form-card" },
    el(
      "form",
      { novalidate: true, onsubmit: enviar },
      el(
        "div",
        { class: "form-body" },
        aviso,
        el(
          "div",
          { class: "form-grid" },
          campo("f-programa-nome", "Nome do programa", campos.nome),
          campo("f-programa-identificador", "Identificador", campos.identificador, {
            dica: "Código único compartilhado com o Financeiro (ex.: SCFV).",
          }),
          campo("f-programa-publico", "Público atendido", campos.publico, { largo: true }),
          campo("f-programa-responsavel", "Responsável", campos.responsavel, {
            dica: "Escolha um usuário da lista ou escreva o nome de quem não tem conta.",
          }),
          el("div", { class: "field" }),
          campo("f-programa-inicio", "Início da vigência", campos.vigencia_inicio),
          campo("f-programa-fim", "Fim da vigência", campos.vigencia_fim),
          campo("f-programa-descricao", "Descrição (opcional)", campos.descricao, { largo: true }),
        ),
      ),
      el(
        "div",
        { class: "form-actions" },
        el("a", { class: "btn", href: cancelarPara }, "Cancelar"),
        enviarBotao,
      ),
      sugestoes,
    ),
  );
  sugerirResponsaveis(sugestoes, listarUsuarios);
  return formulario;
}

export function mostrarCadastroDePrograma(
  container,
  { cadastrar = API_PADRAO.cadastrarPrograma, listarUsuarios = API_PADRAO.listarUsuarios, ir, avisar = () => {} } = {},
) {
  container.replaceChildren(
    formularioDePrograma({
      salvar: cadastrar,
      listarUsuarios,
      aoSalvar: (programa) => {
        avisar(`Programa ${programa.nome} cadastrado.`);
        ir(`/programas/${programa.id}`);
      },
    }),
  );
}

export function mostrarEdicaoDePrograma(
  container,
  programaId,
  {
    obter = API_PADRAO.obterPrograma,
    editar = API_PADRAO.editarPrograma,
    listarUsuarios = API_PADRAO.listarUsuarios,
    ir,
    avisar = () => {},
  } = {},
) {
  return carregarNaTela(
    container,
    () => obter(programaId),
    (programa) =>
      formularioDePrograma({
        programa,
        salvar: (dados) => editar(programaId, dados),
        listarUsuarios,
        cancelarPara: linkPrograma(programaId),
        aoSalvar: (salvo) => {
          avisar("Alterações salvas.");
          ir(`/programas/${salvo.id}`);
        },
      }),
  );
}

// --- Detalhe: dados, convênios e vagas --------------------------------------------

function sobre(p) {
  const itens = [
    ["Identificador", p.identificador ? el("code", {}, p.identificador) : "—"],
    ["Público", p.publico || "—"],
    ["Responsável", p.responsavel || "—"],
    ["Vigência", vigencia(p.vigencia_inicio, p.vigencia_fim)],
    ["Situação", p.status === "encerrado" ? "Encerrado" : "Ativo"],
  ];
  return el(
    "div",
    {},
    p.descricao ? el("p", {}, p.descricao) : null,
    el("dl", { class: "details" }, itens.map(([rotulo, valor]) => el("div", {}, el("dt", {}, rotulo), el("dd", {}, valor)))),
  );
}

function convenios(lista, adicionar) {
  const corpo = lista.length
    ? tabela(
        ["Convênio ou parceria", "Concedente", "Vigência"],
        lista.map((c) => el("tr", {}, el("td", {}, c.nome), el("td", {}, c.concedente || "—"), el("td", {}, vigencia(c.vigencia_inicio, c.vigencia_fim)))),
      )
    : vazio("Nenhum convênio cadastrado", "Convênios e parcerias que financiam ou apoiam o programa aparecem aqui.");
  return cartao("Convênios e parcerias", null, corpo, adicionar ? botao("+ Adicionar convênio", adicionar) : null);
}

function vagas(lista, adicionar) {
  const total = lista.reduce((soma, v) => soma + v.quantidade, 0);
  const corpo = lista.length
    ? tabela(["Vagas", "Quantidade"], lista.map((v) => el("tr", {}, el("td", {}, v.descricao), el("td", {}, String(v.quantidade)))))
    : vazio("Nenhuma vaga cadastrada", "As vagas ofertadas pelo programa aparecem aqui.");
  return cartao("Vagas ofertadas", lista.length ? `${total} no total` : null, corpo, adicionar ? botao("+ Adicionar vagas", adicionar) : null);
}

export function mostrarPrograma(container, programaId, { podeGerenciar = false, avisar = () => {}, ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };

  const recarregar = () =>
    carregarNaTela(
      container,
      () =>
        Promise.all([
          chamadas.obterPrograma(programaId),
          chamadas.listarConvenios(programaId),
          chamadas.listarVagas(programaId),
        ]),
      ([programa, listaDeConvenios, listaDeVagas]) =>
        el(
          "div",
          { class: "stack" },
          secao("Sobre o programa", programa.nome, sobre(programa)),
          el(
            "div",
            { class: "detail-grid" },
            convenios(listaDeConvenios, podeGerenciar ? adicionarConvenio : null),
            vagas(listaDeVagas, podeGerenciar ? adicionarVagas : null),
          ),
        ),
    );

  function adicionarConvenio() {
    const nome = el("input", { type: "text", maxlength: 300, required: true });
    const concedente = el("input", { type: "text", maxlength: 300 });
    const inicio = el("input", { type: "date" });
    const fim = el("input", { type: "date" });
    abrirFormulario({
      titulo: "Adicionar convênio ou parceria",
      campos: [
        campo("f-convenio-nome", "Nome", nome, { largo: true }),
        campo("f-convenio-concedente", "Concedente (opcional)", concedente, { largo: true }),
        campo("f-convenio-inicio", "Início da vigência (opcional)", inicio),
        campo("f-convenio-fim", "Fim da vigência (opcional)", fim),
      ],
      validar: () => {
        if (!nome.value.trim()) return "Informe o nome do convênio.";
        if (inicio.value && fim.value && fim.value < inicio.value) return "O fim da vigência não pode ser anterior ao início.";
        return "";
      },
      enviar: () =>
        chamadas.cadastrarConvenio(programaId, {
          nome: nome.value.trim(),
          concedente: concedente.value.trim() || null,
          vigencia_inicio: inicio.value || null,
          vigencia_fim: fim.value || null,
        }),
      aoConcluir: (c) => {
        avisar(`Convênio ${c.nome} cadastrado.`);
        recarregar();
      },
    });
  }

  function adicionarVagas() {
    const descricao = el("input", { type: "text", maxlength: 300, required: true });
    const quantidade = el("input", { type: "number", min: 1, step: 1, required: true });
    abrirFormulario({
      titulo: "Adicionar vagas",
      campos: [
        campo("f-vagas-descricao", "Descrição", descricao, { largo: true, dica: "Ex.: Turma da manhã, 6 a 11 anos." }),
        campo("f-vagas-quantidade", "Quantidade", quantidade),
      ],
      validar: () => {
        if (!descricao.value.trim()) return "Informe a descrição das vagas.";
        if (!(Number(quantidade.value) > 0)) return "Informe uma quantidade maior que zero.";
        return "";
      },
      enviar: () =>
        chamadas.cadastrarVagas(programaId, { descricao: descricao.value.trim(), quantidade: Number(quantidade.value) }),
      aoConcluir: () => {
        avisar("Vagas cadastradas.");
        recarregar();
      },
    });
  }

  return recarregar();
}
