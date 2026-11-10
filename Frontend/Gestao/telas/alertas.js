// Alertas de infrequência e busca ativa ligados à API da T-59 (T-60 · US-06).
//
// - Lista: os alertas dos programas que a pessoa acompanha (coordenação, assistência
//   social e administração), com pessoa, programa, turma e quantidade de faltas.
// - Detalhe: a linha do tempo do acompanhamento, o registro de uma ação (tipo, data e
//   resultado) e o encerramento, que só sai com justificativa.
//
// As ações também entram na trajetória da pessoa (GET /gestao/pessoas/{id}/trajetoria).
// Quem decide o acesso é a API; a tela só mostra o 403 como acesso restrito.

import * as api from "../base/api.js";
import { ErroApi } from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { abrirFormulario, campo, hojeIso, selecao } from "../base/formulario.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  listarAlertas: api.listarAlertas,
  obterAlerta: api.obterAlerta,
  registrarAcaoDeAlerta: api.registrarAcaoDeAlerta,
  encerrarAlerta: api.encerrarAlerta,
};

export const TIPOS_DE_ACAO = [
  ["contato_familia", "Contato com a família"],
  ["busca_ativa", "Busca ativa"],
  ["articulacao_rede", "Articulação com a rede"],
  ["revisao_contrato", "Revisão de contrato"],
];

// --- Apoio ---------------------------------------------------------------------------

export const dataBr = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
const rotaDoAlerta = (id) => `#/alertas/${encodeURIComponent(id)}`;
const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const aviso = (texto, tom = "") => el("div", { class: `info-box ${tom}`.trim(), role: tom === "amber" ? "alert" : null }, el("span", {}, texto));

function cartao(titulo, subtitulo, corpo) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null)),
    el("div", { class: "card-body" }, corpo),
  );
}

function tabela(cabecalhos, linhas) {
  return el(
    "div",
    { class: "table-wrap" },
    el("table", {}, el("thead", {}, el("tr", {}, cabecalhos.map((c) => el("th", { scope: "col" }, c)))), el("tbody", {}, linhas)),
  );
}

/** "3 faltas seguidas (limite 3)" */
export const textoDasFaltas = (a) => `${a.faltas_consecutivas} ${a.faltas_consecutivas === 1 ? "falta seguida" : "faltas seguidas"} (limite ${a.limite})`;

const situacao = (a) => (a.situacao === "aberto" ? badge("Em aberto", "amber") : badge("Encerrado", "green"));

/** Problema que impede encerrar (ou vazio): a justificativa é obrigatória. */
export const validarEncerramento = (justificativa) =>
  String(justificativa || "").trim() ? "" : "Escreva a justificativa do encerramento.";

/** Problema que impede registrar a ação (ou vazio). */
export function validarAcao({ tipo, data, resultado }, hoje = hojeIso()) {
  const faltando = [!tipo && "o tipo", !data && "a data", !String(resultado || "").trim() && "o resultado"].filter(Boolean);
  if (faltando.length) return `Informe ${faltando.join(", ")} da ação.`;
  if (data > hoje) return "A data da ação não pode estar no futuro.";
  return "";
}

const motivoDoErro = (erro) => (erro instanceof ErroApi ? erro.detalhe || erro.message : "Não foi possível salvar. Tente de novo.");

// --- Lista ---------------------------------------------------------------------------

function linhaDoAlerta(a, nomeDoPrograma) {
  return el(
    "tr",
    {},
    el("td", {}, el("a", { class: "activity-title", href: rotaDoAlerta(a.id) }, a.titulo), el("small", {}, `desde ${dataBr(a.criado_em)}`)),
    el("td", {}, el("a", { href: `#/pessoas/${encodeURIComponent(a.pessoa_id)}` }, a.pessoa)),
    el("td", {}, nomeDoPrograma(a.programa_id), el("small", {}, a.turma)),
    el("td", {}, textoDasFaltas(a), el("small", {}, `${dataBr(a.primeira_falta)} a ${dataBr(a.ultima_falta)}`)),
    el("td", {}, a.responsavel || "—"),
    el("td", {}, situacao(a)),
  );
}

const semAcento = (texto) =>
  String(texto || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

/** Alertas cuja pessoa, título ou turma contém o texto buscado (sem acento e sem diferenciar maiúsculas). */
export function filtrarAlertas(alertas, busca) {
  const termo = semAcento(busca).trim();
  if (!termo) return alertas;
  return alertas.filter((a) => [a.pessoa, a.titulo, a.turma].some((campo) => semAcento(campo).includes(termo)));
}

/** Alertas que a pessoa acompanha, com filtros de programa e situação e busca por nome. */
export function mostrarAlertas(container, { programaInicial = "", ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const lista = el("div", {});
  // A API devolve todos os alertas do recorte; a busca filtra a lista já carregada.
  const busca = el("input", {
    name: "busca",
    type: "search",
    class: "filter-control",
    placeholder: "Buscar pessoa ou turma",
    "aria-label": "Buscar alerta pelo nome da pessoa ou da turma",
  });
  let carregados = [];
  const programa = el("select", { name: "programa", class: "filter-control", "aria-label": "Programa" });
  const filtroSituacao = el(
    "select",
    { name: "situacao", class: "filter-control", "aria-label": "Situação do acompanhamento" },
    el("option", { value: "" }, "Todas as situações"),
    el("option", { value: "aberto" }, "Em aberto"),
    el("option", { value: "encerrado" }, "Encerrados"),
  );
  let nomes = new Map();
  const nomeDoPrograma = (id) => nomes.get(id) || id;

  function mostrarLista() {
    const visiveis = filtrarAlertas(carregados, busca.value);
    let corpo;
    if (visiveis.length) {
      corpo = tabela(["Acompanhamento", "Pessoa", "Programa", "Faltas", "Responsável", "Situação"], visiveis.map((a) => linhaDoAlerta(a, nomeDoPrograma)));
    } else if (carregados.length) {
      corpo = vazio("Nenhum alerta encontrado", "Nenhuma pessoa ou turma com esse nome nos alertas filtrados.");
    } else {
      corpo = vazio("Nenhum alerta", "Quando alguém atingir o limite de faltas do programa, o alerta aparece aqui.");
    }
    return cartao("Alertas de infrequência", "Abertos primeiro; cada um leva ao acompanhamento", corpo);
  }

  function carregar() {
    return carregarNaTela(
      lista,
      () => chamadas.listarAlertas({ programaId: programa.value, situacao: filtroSituacao.value }),
      (alertas) => {
        carregados = alertas;
        return mostrarLista();
      },
    );
  }

  programa.addEventListener("change", carregar);
  filtroSituacao.addEventListener("change", carregar);
  busca.addEventListener("input", () => lista.replaceChildren(mostrarLista()));
  return carregarNaTela(container, () => chamadas.listarProgramas(), (programas) => {
    nomes = new Map(programas.map((p) => [p.id, p.nome]));
    programa.replaceChildren(el("option", { value: "" }, "Todos os programas"), ...programas.map((p) => el("option", { value: p.id }, p.nome)));
    programa.value = programas.some((p) => p.id === programaInicial) ? programaInicial : "";
    queueMicrotask(carregar);
    return el("div", { class: "stack" }, el("div", { class: "toolbar" }, el("div", { class: "filters" }, programa, filtroSituacao, busca)), lista);
  });
}

// --- Detalhe -------------------------------------------------------------------------

function linhaDoTempo(acoes) {
  if (!acoes.length) return vazio("Ainda não houve contato", "Registre uma ação para iniciar o acompanhamento.");
  return el(
    "div",
    { class: "timeline" },
    acoes.map((a) =>
      el("div", { class: "timeline-item" }, el("small", {}, `${dataBr(a.data)} · ${a.responsavel}`), el("h3", {}, a.tipo_nome), el("p", {}, a.resultado)),
    ),
  );
}

function detalhes(a) {
  const itens = [
    ["Pessoa", a.pessoa],
    ["Turma", a.turma],
    ["Faltas", textoDasFaltas(a)],
    ["Período", `${dataBr(a.primeira_falta)} a ${dataBr(a.ultima_falta)}`],
    ["Responsável", a.responsavel || "—"],
    ["Aberto em", dataBr(a.criado_em)],
  ];
  return el("dl", { class: "details" }, itens.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))));
}

/** Detalhe do alerta: linha do tempo, registro de ação e encerramento com justificativa. */
export function mostrarAlerta(container, alertaId, { avisar = () => {}, hoje = hojeIso(), ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const recarregar = () => mostrarAlerta(container, alertaId, { avisar, hoje, ...substitutos });

  function registrarAcao(a) {
    const tipo = selecao("tipo", TIPOS_DE_ACAO);
    tipo.value = "contato_familia";
    const data = el("input", { name: "data", type: "date", max: hoje, required: true });
    data.value = hoje;
    const resultado = el("textarea", { name: "resultado", rows: 4, required: true, maxlength: 5000 });
    const ler = () => ({ tipo: tipo.value, data: data.value, resultado: resultado.value.trim() });
    abrirFormulario({
      titulo: `Registrar ação · ${a.pessoa}`,
      aviso: aviso("A ação entra na linha do tempo do alerta e na trajetória da pessoa, com o seu nome."),
      campos: [campo("acao-tipo", "Tipo de ação", tipo), campo("acao-data", "Data", data), campo("acao-resultado", "Resultado do contato", resultado, { largo: true })],
      botao: "Registrar ação",
      validar: () => validarAcao(ler(), hoje),
      enviar: () => chamadas.registrarAcaoDeAlerta(alertaId, ler()),
      aoConcluir: () => {
        avisar("Ação registrada no acompanhamento.");
        return recarregar();
      },
    });
  }

  function encerrar(a) {
    const justificativa = el("textarea", { name: "justificativa", rows: 4, required: true, maxlength: 5000 });
    abrirFormulario({
      titulo: `Encerrar o alerta de ${a.pessoa}`,
      aviso: aviso("O encerramento não pode ser desfeito. Explique por que o acompanhamento termina, por exemplo o retorno à frequência regular."),
      campos: [campo("encerramento-justificativa", "Justificativa do encerramento", justificativa, { largo: true })],
      botao: "Encerrar alerta",
      validar: () => validarEncerramento(justificativa.value),
      enviar: () => chamadas.encerrarAlerta(alertaId, justificativa.value.trim()),
      aoConcluir: () => {
        avisar("Alerta encerrado.");
        return recarregar();
      },
    });
  }

  function proximoPasso(a) {
    if (a.situacao !== "aberto") {
      return cartao(
        "Acompanhamento encerrado",
        `Em ${dataBr(a.encerrado_em)}`,
        el("div", {}, el("h3", {}, "Justificativa"), el("p", { class: "alerta-justificativa" }, a.justificativa_encerramento || "—")),
      );
    }
    return cartao(
      "Próximo passo",
      "Situação: em aberto",
      el(
        "div",
        {},
        el("p", { class: "muted" }, "Registre a ação e o resultado obtido. O histórico permanece disponível."),
        el(
          "div",
          { class: "quick-actions" },
          el("button", { type: "button", class: "btn primary", onclick: () => registrarAcao(a) }, "Registrar ação"),
          el("button", { type: "button", class: "btn", onclick: () => encerrar(a) }, "Encerrar alerta"),
        ),
      ),
    );
  }

  return carregarNaTela(container, () => chamadas.obterAlerta(alertaId), (a) =>
    el(
      "div",
      { class: "stack" },
      aviso(a.descricao, a.situacao === "aberto" ? "amber" : ""),
      el(
        "div",
        { class: "detail-grid" },
        el("div", { class: "stack" }, cartao("Alerta", a.titulo, detalhes(a)), cartao("Histórico do acompanhamento", "Da ação mais recente para a mais antiga", linhaDoTempo(a.acoes))),
        proximoPasso(a),
      ),
    ),
  );
}
