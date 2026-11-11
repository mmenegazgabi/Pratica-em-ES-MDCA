// Turmas e matrículas ligadas à API da T-52 (T-53 · US-04): lista por programa, cadastro
// e edição da turma, matrículas, lista de espera em ordem e desligamento.
//
// Regras que aparecem na tela (a API confere de novo):
// - turma lotada: a inscrição entra na lista de espera, mostrada em ordem; quando abre
//   vaga, a coordenação chama o próximo da fila;
// - desligamento: data e motivo obrigatórios no formulário;
// - conflito de horário: a inscrição é salva, e o aviso aparece para a coordenação na
//   própria tela e em cada matrícula em conflito.
//
// Os botões de alteração só aparecem para quem gerencia o programa; quem decide é a API.

import * as api from "../base/api.js";
import { ErroApi } from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { abrirFormulario, campo, hojeIso, selecao } from "../base/formulario.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  listarTurmas: api.listarTurmas,
  obterTurma: api.obterTurma,
  cadastrarTurma: api.cadastrarTurma,
  editarTurma: api.editarTurma,
  listarEspacos: api.listarEspacos,
  listarEquipe: api.listarEquipe,
  listarPessoas: api.listarPessoas,
  inscreverNaTurma: api.inscreverNaTurma,
  chamarListaDeEspera: api.chamarListaDeEspera,
  desligarMatricula: api.desligarMatricula,
};

export const DIAS = [
  [1, "seg"],
  [2, "ter"],
  [3, "qua"],
  [4, "qui"],
  [5, "sex"],
  [6, "sáb"],
  [7, "dom"],
];

// --- Apoio ---------------------------------------------------------------------------

export const dataBr = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
const hora = (h) => String(h || "").slice(0, 5);

/** "seg e qua · 14:00–16:00" */
export function horario(t) {
  const nomes = DIAS.filter(([n]) => t.dias_semana.includes(n)).map(([, nome]) => nome);
  const dias = nomes.length > 1 ? `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}` : nomes[0] || "";
  return `${dias} · ${hora(t.hora_inicio)}–${hora(t.hora_fim)}`;
}

const rotaDaTurma = (programaId, turmaId, sufixo = "") =>
  `#/turmas/${encodeURIComponent(programaId)}/${encodeURIComponent(turmaId)}${sufixo}`;
const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const aviso = (texto, tom = "") => el("div", { class: `info-box ${tom}`.trim(), role: tom === "amber" ? "alert" : null }, el("span", {}, texto));
const motivoDoErro = (erro) => (erro instanceof ErroApi ? erro.detalhe || erro.message : "Não foi possível salvar. Tente de novo.");

function cartao(titulo, subtitulo, corpo, acao = null) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), acao),
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

const entrada = (nome, tipo = "text", valor = "", extras = {}) => {
  const no = el("input", { name: nome, type: tipo, ...extras });
  no.value = valor ?? "";
  return no;
};

/** Texto do aviso de conflito de horário para a coordenação. */
export function textoDoConflito(pessoa, conflitos) {
  const turmas = conflitos.map((c) => `${c.turma} (${horario(c)})`).join("; ");
  return `Conflito de horário: ${pessoa} já está ativa(o) em ${turmas}.`;
}

// --- Lista ---------------------------------------------------------------------------

function linhaDaTurma(programaId, t) {
  return el(
    "tr",
    {},
    el("td", {}, el("a", { class: "activity-title", href: rotaDaTurma(programaId, t.id) }, t.nome), el("small", {}, horario(t))),
    el("td", {}, t.espaco),
    el("td", {}, t.responsavel),
    el("td", {}, `${t.ativas} de ${t.capacidade}`, el("small", {}, t.vagas_livres ? `${t.vagas_livres} vaga(s) livre(s)` : "Turma lotada")),
    el("td", {}, t.em_espera ? badge(`${t.em_espera} na espera`, "amber") : badge("Sem espera", "gray")),
  );
}

/** Turmas do programa escolhido; o filtro de programa decide qual lista carregar. */
export function mostrarTurmas(container, { programaInicial = "", podeGerenciar = false, ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const lista = el("div", {});
  const programa = el("select", { name: "programa", class: "filter-control", "aria-label": "Programa" });
  const novo = el("a", { class: "btn primary", hidden: true }, "+ Criar turma");

  function carregar() {
    const id = programa.value;
    novo.hidden = !podeGerenciar || !id;
    novo.setAttribute("href", `#/turmas/${encodeURIComponent(id)}/nova`);
    if (!id) return lista.replaceChildren(cartao("Turmas", "", vazio("Nenhum programa", "Cadastre um programa para organizar as turmas.")));
    return carregarNaTela(lista, () => chamadas.listarTurmas(id), (turmas) =>
      cartao(
        "Turmas",
        "Vagas, horários, local e responsável",
        turmas.length
          ? tabela(["Turma", "Local", "Responsável", "Matrículas", "Lista de espera"], turmas.map((t) => linhaDaTurma(id, t)))
          : vazio("Nenhuma turma neste programa", podeGerenciar ? "Crie a primeira turma." : "As turmas do programa aparecem aqui."),
      ),
    );
  }

  programa.addEventListener("change", carregar);
  return carregarNaTela(container, () => chamadas.listarProgramas(), (programas) => {
    programa.replaceChildren(...programas.map((p) => el("option", { value: p.id }, p.nome)));
    programa.value = programas.some((p) => p.id === programaInicial) ? programaInicial : programas[0]?.id || "";
    queueMicrotask(carregar);
    return el("div", { class: "stack" }, el("div", { class: "toolbar" }, el("div", { class: "filters" }, programa), novo), lista);
  });
}

// --- Cadastro e edição ---------------------------------------------------------------

/** Problema que impede salvar (ou vazio). */
export function validarTurma(d) {
  const faltando = [
    ["nome", "o nome"],
    ["espaco_id", "o local"],
    ["responsavel_id", "o responsável"],
    ["capacidade", "as vagas"],
    ["hora_inicio", "o início"],
    ["hora_fim", "o término"],
  ]
    .filter(([chave]) => !d[chave])
    .map(([, rotulo]) => rotulo);
  if (!d.dias_semana.length) faltando.push("os dias da semana");
  if (faltando.length) return `Informe ${faltando.join(", ")}.`;
  if (!(d.capacidade > 0)) return "A turma precisa de ao menos uma vaga.";
  if (d.hora_fim <= d.hora_inicio) return "O horário de término precisa ser depois do início.";
  return "";
}

function responsaveisPossiveis(equipe) {
  const vistos = new Map();
  for (const v of equipe.filter((v) => v.ativo)) if (!vistos.has(v.usuario_id)) vistos.set(v.usuario_id, `${v.nome} · ${v.papel}`);
  return [...vistos.entries()];
}

/** Cadastro (sem `turmaId`) ou edição de uma turma do programa. */
export function mostrarCadastroDeTurma(container, programaId, { turmaId = "", ir = () => {}, avisar = () => {}, ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const voltar = turmaId ? rotaDaTurma(programaId, turmaId) : `#/turmas/${encodeURIComponent(programaId)}`;

  function formulario([espacos, equipe, atual]) {
    const t = atual?.turma || {};
    const nome = entrada("nome", "text", t.nome, { maxlength: 200, autocomplete: "off" });
    const espaco = selecao("espaco_id", espacos.map((e) => [e.id, e.capacidade ? `${e.nome} (${e.capacidade} lugares)` : e.nome]));
    espaco.value = t.espaco_id || "";
    const responsavel = selecao("responsavel_id", responsaveisPossiveis(equipe));
    responsavel.value = t.responsavel_id || "";
    const capacidade = entrada("capacidade", "number", t.capacidade, { min: 1 });
    const inicio = entrada("hora_inicio", "time", hora(t.hora_inicio));
    const fim = entrada("hora_fim", "time", hora(t.hora_fim));
    const dias = DIAS.map(([n, rotulo]) => {
      const caixa = el("input", { type: "checkbox", name: "dias_semana", value: String(n) });
      caixa.checked = (t.dias_semana || []).includes(n);
      return el("label", { class: "check-row turma-dia" }, caixa, ` ${rotulo}`);
    });
    const erro = el("div", { class: "error-message", role: "alert", hidden: true });
    const salvar = el("button", { type: "submit", class: "btn primary" }, turmaId ? "Salvar alterações" : "Salvar turma");

    async function enviar(evento) {
      evento.preventDefault();
      // O app tem um tratador global de submit para os formulários do protótipo.
      evento.stopPropagation();
      const dados = {
        nome: nome.value.trim(),
        espaco_id: espaco.value,
        responsavel_id: responsavel.value,
        capacidade: Number(capacidade.value) || 0,
        dias_semana: dias.map((d) => d.querySelector("input")).filter((c) => c.checked).map((c) => Number(c.value)),
        hora_inicio: inicio.value,
        hora_fim: fim.value,
      };
      const problema = validarTurma(dados);
      if (problema) {
        erro.textContent = problema;
        erro.hidden = false;
        return;
      }
      erro.hidden = true;
      salvar.disabled = true;
      try {
        const salva = turmaId ? await chamadas.editarTurma(programaId, turmaId, dados) : await chamadas.cadastrarTurma(programaId, dados);
        avisar(turmaId ? "Alterações salvas." : `Turma ${salva.nome} criada.`);
        ir(`/turmas/${encodeURIComponent(programaId)}/${encodeURIComponent(salva.id)}`);
      } catch (e) {
        salvar.disabled = false;
        erro.textContent = motivoDoErro(e);
        erro.hidden = false;
      }
    }

    const semEquipe = !responsaveisPossiveis(equipe).length;
    const semLocal = !espacos.length;
    return el(
      "section",
      { class: "card form-card" },
      el(
        "form",
        { class: "turma-cadastro", novalidate: true, onsubmit: enviar },
        el(
          "div",
          { class: "form-body" },
          semLocal ? aviso("Este programa ainda não tem espaços. Cadastre um local na aba Equipe e espaços do programa.", "amber") : null,
          semEquipe ? aviso("Este programa ainda não tem equipe ativa para ser responsável. Vincule alguém na aba Equipe e espaços.", "amber") : null,
          erro,
          el(
            "div",
            { class: "form-grid" },
            campo("turma-nome", "Nome da turma", nome, { largo: true }),
            campo("turma-local", "Local", espaco),
            campo("turma-responsavel", "Responsável", responsavel, { dica: "Só quem tem vínculo ativo na equipe do programa." }),
            campo("turma-vagas", "Vagas", capacidade),
            el("fieldset", { class: "field wide turma-dias" }, el("legend", {}, "Dias da semana"), el("div", { class: "turma-dias__lista" }, dias)),
            campo("turma-inicio", "Início", inicio),
            campo("turma-fim", "Término", fim),
          ),
        ),
        el("div", { class: "form-actions" }, el("a", { class: "btn", href: voltar }, "Cancelar"), salvar),
      ),
    );
  }

  return carregarNaTela(
    container,
    () =>
      Promise.all([
        chamadas.listarEspacos(programaId),
        chamadas.listarEquipe(programaId),
        turmaId ? chamadas.obterTurma(programaId, turmaId) : Promise.resolve(null),
      ]),
    formulario,
  );
}

// --- Detalhe da turma ----------------------------------------------------------------

const ABAS = [
  ["participantes", "Participantes", ""],
  ["espera", "Lista de espera", "/espera"],
  ["historico", "Desligamentos", "/historico"],
];

function abas(programaId, turmaId, ativa, detalhe) {
  const contagem = { participantes: detalhe.matriculas.length, espera: detalhe.lista_de_espera.length, historico: detalhe.desligadas.length };
  return el(
    "nav",
    { class: "tabs", "aria-label": "Seções da turma" },
    ABAS.map(([chave, nome, sufixo]) =>
      el(
        "a",
        { class: chave === ativa ? "tab active" : "tab", href: rotaDaTurma(programaId, turmaId, sufixo), "aria-current": chave === ativa ? "page" : null },
        `${nome} (${contagem[chave]})`,
      ),
    ),
  );
}

function resumo(t) {
  return el(
    "section",
    { class: "turma-resumo resumo-linha" },
    el(
      "div",
      {},
      el("h2", {}, t.nome),
      el("p", { class: "muted" }, `${horario(t)} · ${t.espaco} · responsável ${t.responsavel}`),
      el(
        "div",
        { class: "badges" },
        badge(`${t.ativas} de ${t.capacidade} vagas ocupadas`, t.vagas_livres ? "green" : "amber"),
        " ",
        t.vagas_livres ? badge(`${t.vagas_livres} vaga(s) livre(s)`, "gray") : badge("Turma lotada", "amber"),
        " ",
        t.em_espera ? badge(`${t.em_espera} na lista de espera`, "amber") : null,
      ),
    ),
  );
}

/** Detalhe da turma com as abas Participantes, Lista de espera e Desligamentos. */
export function mostrarTurma(
  container,
  programaId,
  turmaId,
  { aba = "participantes", podeGerenciar = false, avisar = () => {}, avisoInicial = null, hoje = hojeIso(), ...substitutos } = {},
) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const ativa = ABAS.some(([chave]) => chave === aba) ? aba : "participantes";
  const recarregar = (avisoNovo = null, abaNova = ativa) =>
    mostrarTurma(container, programaId, turmaId, { aba: abaNova, podeGerenciar, avisar, avisoInicial: avisoNovo, hoje, ...substitutos });

  function concluirInscricao(inscricao) {
    const m = inscricao.matricula;
    const texto =
      m.situacao === "espera"
        ? `Turma lotada: ${m.pessoa} entrou na lista de espera (posição ${m.posicao_espera}).`
        : `${m.pessoa} matriculada(o) na turma.`;
    avisar(texto);
    const conflito = inscricao.conflitos.length ? textoDoConflito(m.pessoa, inscricao.conflitos) : null;
    return recarregar(conflito, m.situacao === "espera" ? "espera" : "participantes");
  }

  async function inscrever(botao, detalhe) {
    botao.disabled = true;
    let pessoas;
    try {
      pessoas = await chamadas.listarPessoas({ programaId });
    } catch (e) {
      avisar(motivoDoErro(e));
      return;
    } finally {
      botao.disabled = false;
    }
    const emAberto = new Set([...detalhe.matriculas, ...detalhe.lista_de_espera].map((m) => m.pessoa_id));
    const disponiveis = pessoas.filter((p) => !emAberto.has(p.id));
    const pessoa = selecao("pessoa_id", disponiveis.map((p) => [p.id, p.nome]));
    const lotada = detalhe.turma.vagas_livres <= 0;
    abrirFormulario({
      titulo: `Inscrever em ${detalhe.turma.nome}`,
      aviso: lotada
        ? aviso("A turma está lotada: a pessoa entra na lista de espera, na ordem de inscrição.", "amber")
        : disponiveis.length
          ? null
          : aviso("Todas as pessoas do programa já estão nesta turma ou na lista de espera."),
      campos: [campo("matricula-pessoa", "Pessoa do programa", pessoa, { largo: true })],
      botao: lotada ? "Colocar na lista de espera" : "Matricular",
      validar: () => (pessoa.value ? "" : "Escolha a pessoa."),
      enviar: () => chamadas.inscreverNaTurma(programaId, turmaId, pessoa.value),
      aoConcluir: concluirInscricao,
    });
  }

  function desligar(m) {
    const data = entrada("data_saida", "date", hoje, { required: true });
    const motivo = el("textarea", { name: "motivo", rows: 3, required: true, maxlength: 1000 });
    const naEspera = m.situacao === "espera";
    abrirFormulario({
      titulo: naEspera ? `Tirar ${m.pessoa} da lista de espera` : `Desligar ${m.pessoa}`,
      aviso: aviso("O registro continua no histórico da turma e na trajetória da pessoa."),
      campos: [campo("desligamento-data", "Data", data), campo("desligamento-motivo", "Motivo", motivo, { largo: true })],
      botao: naEspera ? "Tirar da fila" : "Registrar desligamento",
      validar: () => {
        const faltando = [!data.value && "a data", !motivo.value.trim() && "o motivo"].filter(Boolean);
        return faltando.length ? `Informe ${faltando.join(" e ")} do desligamento.` : "";
      },
      enviar: () => chamadas.desligarMatricula(programaId, turmaId, m.id, { data_saida: data.value, motivo: motivo.value.trim() }),
      aoConcluir: () => {
        avisar(naEspera ? "Retirada(o) da lista de espera." : "Desligamento registrado.");
        return recarregar(null);
      },
    });
  }

  async function chamarProximo(botao) {
    botao.disabled = true;
    try {
      const inscricao = await chamadas.chamarListaDeEspera(programaId, turmaId);
      avisar(`${inscricao.matricula.pessoa} saiu da lista de espera e entrou na turma.`);
      const conflito = inscricao.conflitos.length ? textoDoConflito(inscricao.matricula.pessoa, inscricao.conflitos) : null;
      return recarregar(conflito, "participantes");
    } catch (e) {
      botao.disabled = false;
      avisar(motivoDoErro(e));
    }
  }

  const botao = (texto, acao, extra = {}) =>
    podeGerenciar ? el("button", { type: "button", class: "btn small", onclick: (ev) => acao(ev.currentTarget), ...extra }, texto) : null;

  function participantes(d) {
    if (!d.matriculas.length) return vazio("Nenhuma matrícula ativa", "Inscreva as pessoas do programa nesta turma.");
    return tabela(
      ["Pessoa", "Entrada", "Horário", ""],
      d.matriculas.map((m) =>
        el(
          "tr",
          {},
          el("td", {}, el("strong", {}, m.pessoa)),
          el("td", {}, dataBr(m.data_entrada)),
          el("td", {}, m.conflitos.length ? badge(`Conflito com ${m.conflitos.map((c) => c.turma).join(", ")}`, "amber") : badge("Sem conflito", "gray")),
          el("td", {}, botao("Desligar", () => desligar(m))),
        ),
      ),
    );
  }

  function espera(d) {
    if (!d.lista_de_espera.length) return vazio("Ninguém na lista de espera", "Quando a turma lotar, as próximas inscrições entram aqui, em ordem.");
    return tabela(
      ["Posição", "Pessoa", "Inscrição", ""],
      d.lista_de_espera.map((m) =>
        el(
          "tr",
          {},
          el("td", {}, el("strong", {}, `${m.posicao_espera}º`)),
          el("td", {}, m.pessoa),
          el("td", {}, dataBr(m.inscrito_em)),
          el("td", {}, botao("Tirar da fila", () => desligar(m))),
        ),
      ),
    );
  }

  function historico(d) {
    if (!d.desligadas.length) return vazio("Nenhum desligamento", "Desligamentos registrados aparecem aqui, com data e motivo.");
    return tabela(
      ["Pessoa", "Entrada", "Saída", "Motivo"],
      d.desligadas.map((m) => el("tr", {}, el("td", {}, m.pessoa), el("td", {}, dataBr(m.data_entrada)), el("td", {}, dataBr(m.data_saida)), el("td", {}, m.motivo_saida))),
    );
  }

  function conteudo(d) {
    const t = d.turma;
    const acoes = podeGerenciar
      ? el(
          "div",
          { class: "actions" },
          botao("Inscrever pessoa", (b) => inscrever(b, d)),
          ativa === "espera" && d.lista_de_espera.length
            ? botao("Chamar próximo da fila", chamarProximo, { disabled: t.vagas_livres <= 0, title: t.vagas_livres <= 0 ? "A turma está lotada" : null })
            : null,
          el("a", { class: "btn small", href: rotaDaTurma(programaId, turmaId, "/editar") }, "Editar turma"),
        )
      : null;
    const corpo = { participantes, espera, historico }[ativa](d);
    const titulos = { participantes: "Participantes", espera: "Lista de espera (em ordem de inscrição)", historico: "Desligamentos" };
    return el(
      "div",
      { class: "stack" },
      avisoInicial ? aviso(avisoInicial, "amber") : null,
      resumo(t),
      abas(programaId, turmaId, ativa, d),
      cartao(titulos[ativa], "", corpo, acoes),
    );
  }

  return carregarNaTela(container, () => chamadas.obterTurma(programaId, turmaId), conteudo);
}
